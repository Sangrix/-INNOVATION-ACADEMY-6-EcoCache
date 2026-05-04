"""
EcoCache retrieval and answer generation entrypoint.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range
from sentence_transformers import SentenceTransformer

import config
from carbon_monitor import CarbonMonitor

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

carbon_monitor = CarbonMonitor.from_config(config)
_model: SentenceTransformer | None = None
_client: QdrantClient | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
        _model = SentenceTransformer(config.EMBED_MODEL_ID, device=device, model_kwargs=kwargs)
    return _model


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
    return _client


def build_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None

    conditions = []
    for key, value in filters.items():
        if isinstance(value, dict):
            conditions.append(FieldCondition(key=key, range=Range(**value)))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


def search(query: str, collection: str, top_k: int = config.TOP_K, filters: dict | None = None) -> list[dict]:
    results, _ = search_with_metrics(query, collection, top_k=top_k, filters=filters)
    return results


def search_with_metrics(
    query: str,
    collection: str,
    top_k: int = config.TOP_K,
    filters: dict | None = None,
) -> tuple[list[dict], dict]:
    model = get_model()
    client = get_client()

    def run_search():
        query_vector = model.encode([query], normalize_embeddings=True).tolist()[0]
        response = client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=top_k,
            query_filter=build_filter(filters),
            with_payload=True,
        )
        return [{"score": hit.score, "payload": hit.payload} for hit in response.points]

    stage_name = f"{collection}_retrieval"
    extra = {"collection": collection, "top_k": top_k}
    return carbon_monitor.run(stage_name, run_search, extra=extra)


def rag_search(query: str, filters: dict | None = None) -> dict:
    qa_results, qa_metrics = search_with_metrics(query, config.COLLECTION_QA, top_k=3, filters=filters)
    qa_top1 = qa_results[0]["score"] if qa_results else None

    if qa_results and qa_top1 >= config.QA_SIMILARITY_THRESHOLD:
        return {
            "source": "qa_pairs",
            "results": qa_results,
            "query": query,
            "qa_top1_score": qa_top1,
            "metrics": {"qa_retrieval": qa_metrics},
        }

    doc_results, doc_metrics = search_with_metrics(query, config.COLLECTION_DOCS, top_k=3, filters=filters)
    return {
        "source": "documents",
        "results": doc_results,
        "query": query,
        "qa_top1_score": qa_top1,
        "metrics": {
            "qa_retrieval": qa_metrics,
            "documents_retrieval": doc_metrics,
        },
    }


def _config_snapshot() -> dict:
    return {
        "embed_model": config.EMBED_MODEL_ID,
        "vector_size": config.VECTOR_SIZE,
        "chunk_threshold": config.CHUNK_THRESHOLD,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "qa_similarity_threshold": config.QA_SIMILARITY_THRESHOLD,
        "top_k": config.TOP_K,
        "qdrant_url": config.QDRANT_URL,
        "collection_docs": config.COLLECTION_DOCS,
        "collection_qa": config.COLLECTION_QA,
        "carbon_monitor_enabled": config.CARBON_MONITOR_ENABLED,
        "carbon_intensity_g_per_kwh": config.CARBON_INTENSITY_G_PER_KWH,
    }


def _qa_summary(payload: dict) -> dict:
    return {
        "qa_id": payload.get("qa_id", ""),
        "question": payload.get("question", ""),
        "answer": payload.get("answer", "")[:120],
    }


def _doc_summary(payload: dict) -> dict:
    return {
        "doc_id": payload.get("doc_id", ""),
        "chunk_index": payload.get("chunk_index", 0),
        "title": payload.get("title", ""),
        "published_at": payload.get("published_at", ""),
        "text_preview": payload.get("text", "")[:120],
    }


def log_result(result: dict, log_file: str | Path = "eval_log.jsonl", filters: dict | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": _config_snapshot(),
        "query": result["query"],
        "filters": filters,
        "source": result["source"],
        "qa_top1_score": result.get("qa_top1_score"),
        "carbon_metrics": result.get("metrics", {}),
        "results": [
            {
                "rank": index + 1,
                "score": item["score"],
                **(
                    _qa_summary(item["payload"])
                    if result["source"] == "qa_pairs"
                    else _doc_summary(item["payload"])
                ),
            }
            for index, item in enumerate(result["results"])
        ],
    }
    with open(log_file, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _build_context(result: dict) -> str:
    per_doc = max(1, config.LM_CONTEXT_LIMIT // max(len(result["results"]), 1))
    parts = []
    for item in result["results"]:
        payload = item["payload"]
        if result["source"] == "qa_pairs":
            parts.append(f"Q: {payload.get('question', '')}\nA: {payload.get('answer', '')}")
        else:
            text = payload.get("text", "")[:per_doc]
            parts.append(f"[{payload.get('title', '')} / {payload.get('published_at', '')}]\n{text}")
    return "\n\n---\n\n".join(parts)


def generate_answer(query: str, rag_result: dict) -> str:
    if not config.LM_STUDIO_MODEL:
        raise ValueError(
            "LM_STUDIO_MODEL environment variable is not set. "
            "Add LM_STUDIO_MODEL=<model-name> to your .env file."
        )

    from openai import OpenAI

    context = _build_context(rag_result)
    lm_client = OpenAI(base_url=config.LM_STUDIO_URL, api_key="lm-studio")

    def request_completion():
        response = lm_client.chat.completions.create(
            model=config.LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": config.LM_SYSTEM_PROMPT},
                {"role": "user", "content": f"참고 문서:\n{context}\n\n질문: {query}"},
            ],
            temperature=config.LM_TEMPERATURE,
            max_tokens=config.LM_MAX_TOKENS,
        )
        return response.choices[0].message.content

    answer, metrics = carbon_monitor.run(
        "llm_generation",
        request_completion,
        extra={"source": rag_result["source"], "context_docs": len(rag_result["results"])},
    )
    rag_result.setdefault("metrics", {})["llm_generation"] = metrics
    return answer


def print_results(result: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"Query    : {result['query']}")
    print(f"Source   : {result['source']}")
    print(f"{'=' * 60}")

    for index, item in enumerate(result["results"], 1):
        score = item["score"]
        payload = item["payload"]
        print(f"\n[{index}] similarity={score:.4f}")

        if result["source"] == "qa_pairs":
            print(f"  Q: {payload.get('question', '')}")
            print(f"  A: {payload.get('answer', '')}")
            print(f"  URL: {payload.get('reference_url', '')}")
        else:
            print(f"  Title: {payload.get('title', '')}")
            print(f"  Date : {payload.get('published_at', '')}")
            print(f"  Chunk: {payload.get('chunk_index', 0) + 1}/{payload.get('chunk_total', 1)}")
            print(f"  Text : {payload.get('text', '')[:200]}...")
            print(f"  URL  : {payload.get('url', '')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python query.py "질문 텍스트" [options]')
        print('Example: python query.py "i-PAC 콘테스트 신청 기간"')
        print("Options:")
        print("  --log                 append result to eval_log.jsonl")
        print("  --log-file <path>     custom log file path")
        print("  --generate            generate natural language answer via LM Studio")
        print("  --board_type <value>  filter by notice | pr")
        sys.exit(1)

    query_text = sys.argv[1]

    do_log = False
    do_generate = False
    log_file = Path("eval_log.jsonl")
    filters = {}
    args = sys.argv[2:]
    index = 0

    while index < len(args):
        if args[index] == "--log":
            do_log = True
            index += 1
        elif args[index] == "--log-file" and index + 1 < len(args):
            log_file = Path(args[index + 1])
            do_log = True
            index += 2
        elif args[index] == "--generate":
            do_generate = True
            index += 1
        elif args[index].startswith("--") and index + 1 < len(args):
            filters[args[index][2:]] = args[index + 1]
            index += 2
        else:
            index += 1

    result = rag_search(query_text, filters=filters if filters else None)
    print_results(result)

    if do_generate:
        try:
            answer = generate_answer(query_text, result)
            print(f"\n{'=' * 60}")
            print("Generated Answer")
            print(f"{'=' * 60}")
            print(answer)
            print()
        except Exception as error:
            print(f"\n[ERROR] failed to generate answer: {error}")

    if do_log:
        log_result(result, log_file=log_file, filters=filters if filters else None)
        print(f"\n[LOG] appended to {log_file}")
