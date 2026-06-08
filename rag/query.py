"""
EcoCache RAG 쿼리 인터페이스

--mode b1 / pure_rag       : Baseline 1 — documents만 검색
--mode b2 / semantic_cache : Baseline 2 — QA 캐시 → documents fallback (기본값)
--mode ciasc               : Baseline 3 — CI 연동 동적 threshold

사용법:
  python query.py "질문" [--mode b1|b2|ciasc] [옵션]
  python query.py "질문" --generate
  python query.py "질문" --log --log-file logs/my.jsonl
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

from openai import OpenAI

import config
from retriever_base import BaseRetriever
from baseline_pure_rag import PureRAGRetriever
from baseline_semantic_cache import SemanticCacheRetriever
from baseline_ciasc import CIASCRetriever
from carbon_monitor import CarbonMonitor

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

carbon_monitor = CarbonMonitor.from_config(config)

MODES: dict[str, type[BaseRetriever]] = {
    "b1":             PureRAGRetriever,
    "pure_rag":       PureRAGRetriever,
    "b2":             SemanticCacheRetriever,
    "semantic_cache": SemanticCacheRetriever,
    "ciasc":          CIASCRetriever,
}


def get_retriever(mode: str = "b2") -> BaseRetriever:
    cls = MODES.get(mode)
    if cls is None:
        raise ValueError(f"알 수 없는 mode: {mode!r}. 선택 가능: {list(MODES)}")
    return cls()


def rag_search(query: str, mode: str = "b2",
               filters: dict | None = None) -> dict:
    retriever = get_retriever(mode)
    timings: list[dict] = []
    result, metrics = carbon_monitor.run(
        f"{mode}_retrieval",
        retriever.retrieve,
        query,
        filters=filters,
        timings=timings,
        extra={"mode": mode},
    )
    result.setdefault("metrics", {})["retrieval"] = metrics
    result["timings"] = timings
    if metrics:
        result["timings"].append({
            "stage": f"carbon.{mode}_retrieval",
            "duration_ms": round(metrics.get("duration_sec", 0.0) * 1000, 2),
            "co2_g": metrics.get("co2_g"),
            "energy_kwh": metrics.get("energy_kwh"),
            "avg_power_W": metrics.get("avg_power_W"),
            "peak_power_W": metrics.get("peak_power_W"),
        })
    return result


def _config_snapshot(mode: str) -> dict:
    return {
        "mode":                    mode,
        "embed_model":             config.EMBED_MODEL_ID,
        "vector_size":             config.VECTOR_SIZE,
        "chunk_threshold":         config.CHUNK_THRESHOLD,
        "chunk_size":              config.CHUNK_SIZE,
        "chunk_overlap":           config.CHUNK_OVERLAP,
        "qa_similarity_threshold": config.QA_SIMILARITY_THRESHOLD,
        "top_k":                   config.TOP_K,
        "qdrant_url":              config.QDRANT_URL,
        "collection_docs":         config.COLLECTION_DOCS,
        "collection_qa":           config.COLLECTION_QA,
        "carbon_monitor_enabled":  config.CARBON_MONITOR_ENABLED,
        "carbon_intensity_g_per_kwh": config.CARBON_INTENSITY_G_PER_KWH,
    }


def log_result(result: dict, log_file: str | Path = "eval_log.jsonl",
               filters: dict | None = None, mode: str = "b2") -> None:
    entry = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "config":         _config_snapshot(mode),
        "query":          result["query"],
        "filters":        filters,
        "source":         result["source"],
        "qa_top1_score":  result.get("qa_top1_score"),
        "carbon_metrics": result.get("metrics", {}),
        "timings":        result.get("timings", []),
        "results": [
            {
                "rank":  i + 1,
                "score": r["score"],
                **(_qa_summary(r["payload"]) if result["source"] == "qa_pairs"
                   else _doc_summary(r["payload"])),
            }
            for i, r in enumerate(result["results"])
        ],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _qa_summary(payload: dict) -> dict:
    return {
        "qa_id":    payload.get("qa_id", ""),
        "question": payload.get("question", ""),
        "answer":   payload.get("answer", "")[:120],
    }


def _doc_summary(payload: dict) -> dict:
    return {
        "doc_id":       payload.get("doc_id", ""),
        "chunk_index":  payload.get("chunk_index", 0),
        "title":        payload.get("title", ""),
        "published_at": payload.get("published_at", ""),
        "text_preview": payload.get("text", "")[:120],
    }


def _build_context(result: dict) -> str:
    per_doc = max(1, config.LM_CONTEXT_LIMIT // max(len(result["results"]), 1))
    parts = []
    for r in result["results"]:
        p = r["payload"]
        if result["source"] == "qa_pairs":
            parts.append(f"Q: {p.get('question', '')}\nA: {p.get('answer', '')}")
        else:
            text = p.get("text", "")[:per_doc]
            parts.append(f"[{p.get('title', '')} / {p.get('published_at', '')}]\n{text}")
    return "\n\n---\n\n".join(parts)


def generate_answer(query: str, rag_result: dict) -> str:
    if not config.LM_STUDIO_MODEL:
        raise ValueError(
            "LM_STUDIO_MODEL 환경변수가 설정되지 않았습니다. "
            ".env에 LM_STUDIO_MODEL=<모델명>을 추가하세요."
        )
    from openai import OpenAI

    context   = _build_context(rag_result)
    lm_client = OpenAI(base_url=config.LM_STUDIO_URL, api_key="lm-studio")

    def request_completion():
        resp = lm_client.chat.completions.create(
            model=config.LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": config.LM_SYSTEM_PROMPT},
                {"role": "user",   "content": f"참고 문서:\n{context}\n\n질문: {query}"},
            ],
            temperature=config.LM_TEMPERATURE,
            max_tokens=config.LM_MAX_TOKENS,
        )
        return resp.choices[0].message.content

    answer, metrics = carbon_monitor.run(
        "llm_generation",
        request_completion,
        extra={"source": rag_result["source"], "context_docs": len(rag_result["results"])},
    )
    rag_result.setdefault("metrics", {})["llm_generation"] = metrics
    return answer


def generate_answer_stream(query: str, rag_result: dict):
    """Yield text chunks from LM Studio. Carbon tracking is done by the caller."""
    if not config.LM_STUDIO_MODEL:
        raise ValueError(
            "LM_STUDIO_MODEL 환경변수가 설정되지 않았습니다. "
            ".env에 LM_STUDIO_MODEL=<모델명>을 추가하세요."
        )

    context   = _build_context(rag_result)
    lm_client = OpenAI(base_url=config.LM_STUDIO_URL, api_key="lm-studio")

    stream = lm_client.chat.completions.create(
        model=config.LM_STUDIO_MODEL,
        messages=[
            {"role": "system", "content": config.LM_SYSTEM_PROMPT},
            {"role": "user",   "content": f"참고 문서:\n{context}\n\n질문: {query}"},
        ],
        temperature=config.LM_TEMPERATURE,
        max_tokens=config.LM_MAX_TOKENS,
        stream=True,
    )

    for chunk in stream:
        text = chunk.choices[0].delta.content or ""
        if text:
            yield text


def cached_answer(result: dict) -> str | None:
    if result["source"] != "qa_pairs" or not result["results"]:
        return None
    answer = result["results"][0]["payload"].get("answer")
    if isinstance(answer, dict):
        return answer.get("text")
    return answer


def print_results(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"쿼리   : {result['query']}")
    print(f"출처   : {result['source']}")
    if result.get("metrics", {}).get("retrieval"):
        m = result["metrics"]["retrieval"]
        print(f"탄소   : {m.get('co2_g', 0)*1000:.4f} mg  ({m.get('duration_sec', 0):.2f}s)")
    print(f"{'='*60}")
    for i, r in enumerate(result["results"], 1):
        score   = r["score"]
        payload = r["payload"]
        print(f"\n[{i}] 유사도: {score:.4f}")
        if result["source"] == "qa_pairs":
            print(f"  Q: {payload.get('question', '')}")
            print(f"  A: {payload.get('answer', '')}")
            print(f"  URL: {payload.get('reference_url', '')}")
        else:
            print(f"  제목: {payload.get('title', '')}")
            print(f"  날짜: {payload.get('published_at', '')}")
            print(f"  청크: {payload.get('chunk_index', 0)+1}/{payload.get('chunk_total', 1)}")
            print(f"  본문: {payload.get('text', '')[:200]}...")
            print(f"  URL: {payload.get('url', '')}")

    if result.get("timings"):
        print("\n[Timings]")
        for timing in result["timings"]:
            extras = " ".join(
                f"{k}={v}" for k, v in timing.items()
                if k not in {"stage", "duration_ms"}
            )
            print(f"  {timing['stage']}: {timing['duration_ms']} ms {extras}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python query.py \"질문\" [옵션]")
        print("옵션:")
        print("  --mode <모드>       b1|pure_rag / b2|semantic_cache / ciasc (기본: b2)")
        print("  --log               결과를 eval_log.jsonl에 기록")
        print("  --log-file <경로>   로그 파일 경로 지정")
        print("  --generate          LM Studio로 자연어 답변 생성")
        print("  --board_type <값>   필터: notice | pr")
        sys.exit(1)

    query_text  = sys.argv[1]
    mode        = "b2"
    do_log      = False
    do_generate = False
    log_file    = Path("eval_log.jsonl")
    filters: dict = {}

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]; i += 2
        elif args[i] == "--log":
            do_log = True; i += 1
        elif args[i] == "--log-file" and i + 1 < len(args):
            log_file = Path(args[i + 1]); do_log = True; i += 2
        elif args[i] == "--generate":
            do_generate = True; i += 1
        elif args[i].startswith("--") and i + 1 < len(args):
            filters[args[i][2:]] = args[i + 1]; i += 2
        else:
            i += 1

    result = rag_search(query_text, mode=mode, filters=filters if filters else None)
    print_results(result)

    if do_generate and result["source"] == "qa_pairs":
        print(f"\n{'='*60}")
        print(" 캐시 답변")
        print(f"{'='*60}")
        print(cached_answer(result))
        print()
        do_generate = False

    if do_generate:
        try:
            answer = generate_answer(query_text, result)
            print(f"\n{'='*60}")
            print(" 생성된 답변")
            print(f"{'='*60}")
            print(answer)
            print()
        except Exception as e:
            print(f"\n[오류] LLM 답변 생성 실패: {e}")

    if do_log:
        log_result(result, log_file=log_file,
                   filters=filters if filters else None, mode=mode)
        print(f"\n[로그] {log_file} 에 기록됨")
