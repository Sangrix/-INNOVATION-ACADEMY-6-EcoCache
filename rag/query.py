"""
EcoCache RAG 쿼리 인터페이스

--mode pure_rag        : Baseline 1 — documents만 검색
--mode semantic_cache  : Baseline 2 — qa_pairs 우선, 미달 시 documents fallback (기본값)

사용법:
  python query.py "질문 텍스트" [--mode pure_rag|semantic_cache] [옵션]
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from retriever_base import BaseRetriever
from baseline_pure_rag import PureRAGRetriever
from baseline_semantic_cache import SemanticCacheRetriever

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

MODES = {
    "pure_rag":       PureRAGRetriever,
    "semantic_cache": SemanticCacheRetriever,
}


def get_retriever(mode: str = "semantic_cache") -> BaseRetriever:
    cls = MODES.get(mode)
    if cls is None:
        raise ValueError(f"알 수 없는 mode: {mode!r}. 선택 가능: {list(MODES)}")
    return cls()


# ── 평가 로깅 ─────────────────────────────────────────────────────────────────

def _config_snapshot(mode: str) -> dict:
    return {
        "mode":                   mode,
        "embed_model":            config.EMBED_MODEL_ID,
        "vector_size":            config.VECTOR_SIZE,
        "chunk_threshold":        config.CHUNK_THRESHOLD,
        "chunk_size":             config.CHUNK_SIZE,
        "chunk_overlap":          config.CHUNK_OVERLAP,
        "qa_similarity_threshold": config.QA_SIMILARITY_THRESHOLD,
        "top_k":                  config.TOP_K,
        "qdrant_url":             config.QDRANT_URL,
        "collection_docs":        config.COLLECTION_DOCS,
        "collection_qa":          config.COLLECTION_QA,
    }


def log_result(result: dict, log_file: str | Path = "eval_log.jsonl",
               filters: dict | None = None, mode: str = "semantic_cache") -> None:
    entry = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "config":        _config_snapshot(mode),
        "query":         result["query"],
        "filters":       filters,
        "source":        result["source"],
        "qa_top1_score": result.get("qa_top1_score"),
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


# ── LLM 답변 생성 ─────────────────────────────────────────────────────────────

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
            ".env 파일에 LM_STUDIO_MODEL=<모델명>을 추가하세요."
        )
    from openai import OpenAI
    context = _build_context(rag_result)
    lm_client = OpenAI(base_url=config.LM_STUDIO_URL, api_key="lm-studio")
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


# ── 결과 출력 ─────────────────────────────────────────────────────────────────

def print_results(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"쿼리   : {result['query']}")
    print(f"출처   : {result['source']}")
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


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python query.py \"질문 텍스트\" [옵션]")
        print("옵션:")
        print("  --mode <모드>        pure_rag | semantic_cache (기본: semantic_cache)")
        print("  --log                결과를 eval_log.jsonl에 기록")
        print("  --log-file <경로>    로그 파일 경로 지정")
        print("  --generate           LM Studio로 자연어 답변 생성")
        print("  --board_type <값>    필터: notice | pr")
        sys.exit(1)

    query_text = sys.argv[1]

    do_log      = False
    do_generate = False
    mode        = "semantic_cache"
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

    retriever = get_retriever(mode)
    result    = retriever.retrieve(query_text, filters=filters if filters else None)
    print_results(result)

    if do_generate:
        try:
            answer = generate_answer(query_text, result)
            print(f"\n{'='*60}")
            print(f" 생성된 답변")
            print(f"{'='*60}")
            print(answer)
            print()
        except Exception as e:
            print(f"\n[오류] LLM 답변 생성 실패: {e}")

    if do_log:
        log_result(result, log_file=log_file,
                   filters=filters if filters else None, mode=mode)
        print(f"\n[로그] {log_file} 에 기록됨")
