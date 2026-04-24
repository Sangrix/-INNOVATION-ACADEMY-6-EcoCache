"""
EcoCache RAG 쿼리 인터페이스
- qa_pairs 검색 → 유사도 임계값 미달 시 documents 검색 fallback
- CLI: python query.py "질문 텍스트"
- 평가 로깅: python query.py "질문" --log [--log-file eval_log.jsonl]
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from sentence_transformers import SentenceTransformer

import config

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── 싱글턴 (모듈 수준 캐시) ──────────────────────────────────────────────────
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


# ── 필터 빌더 ─────────────────────────────────────────────────────────────────

def build_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None
    conditions = []
    for key, value in filters.items():
        if isinstance(value, dict):
            # 범위 필터: {"gte": "2026-01-01", "lte": "2026-04-30"}
            conditions.append(FieldCondition(key=key, range=Range(**value)))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


# ── 핵심 검색 ─────────────────────────────────────────────────────────────────

def search(query: str, collection: str, top_k: int = config.TOP_K,
           filters: dict | None = None) -> list[dict]:
    """단일 컬렉션 Dense 검색. 결과를 dict 리스트로 반환."""
    model  = get_model()
    client = get_client()

    query_vector = model.encode([query], normalize_embeddings=True).tolist()[0]
    response = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        query_filter=build_filter(filters),
        with_payload=True,
    )
    return [{"score": h.score, "payload": h.payload} for h in response.points]


# ── RAG 2단계 검색 ────────────────────────────────────────────────────────────

def rag_search(query: str, filters: dict | None = None) -> dict:
    """
    1단계: qa_pairs 검색
    2단계: top-1 유사도 < QA_SIMILARITY_THRESHOLD 이면 documents fallback

    반환:
    {
        "source": "qa_pairs" | "documents",
        "results": [...],
        "query": str,
        "qa_top1_score": float | None,   # fallback 여부 판단 근거 (평가용)
    }
    """
    # 1단계: QA 검색
    qa_results = search(query, config.COLLECTION_QA, top_k=3, filters=filters)
    qa_top1 = qa_results[0]["score"] if qa_results else None

    if qa_results and qa_top1 >= config.QA_SIMILARITY_THRESHOLD:
        return {"source": "qa_pairs", "results": qa_results,
                "query": query, "qa_top1_score": qa_top1}

    # 2단계: 문서 원문 검색
    doc_results = search(query, config.COLLECTION_DOCS, top_k=3, filters=filters)
    return {"source": "documents", "results": doc_results,
            "query": query, "qa_top1_score": qa_top1}


# ── 평가 로깅 ─────────────────────────────────────────────────────────────────

def _config_snapshot() -> dict:
    """현재 config 값을 dict로 반환 (로그 기록용)."""
    return {
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
               filters: dict | None = None) -> None:
    """
    rag_search() 결과를 JSONL 파일에 한 줄 append.

    기록 항목:
      - timestamp, config 스냅샷(모델·청킹·임계값 등)
      - query, filters, source (qa_pairs | documents)
      - qa_top1_score: QA fallback 여부 판단 근거
      - results: rank·score·핵심 payload
    """
    entry = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "config":        _config_snapshot(),
        "query":         result["query"],
        "filters":       filters,
        "source":        result["source"],
        "qa_top1_score": result.get("qa_top1_score"),
        "results": [
            {
                "rank":  i + 1,
                "score": r["score"],
                # source별로 핵심 필드만 기록 (payload 전체는 너무 길어 비교 어려움)
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
        "doc_id":      payload.get("doc_id", ""),
        "chunk_index": payload.get("chunk_index", 0),
        "title":       payload.get("title", ""),
        "published_at": payload.get("published_at", ""),
        "text_preview": payload.get("text", "")[:120],
    }


# ── LLM 답변 생성 ─────────────────────────────────────────────────────────────

def _build_context(result: dict) -> str:
    """rag_search() 결과를 LLM 프롬프트용 컨텍스트 문자열로 변환."""
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
    """컨텍스트를 LM Studio에 전달해 자연어 답변을 생성한다."""
    if not config.LM_STUDIO_MODEL:
        raise ValueError(
            "LM_STUDIO_MODEL 환경변수가 설정되지 않았습니다. "
            ".env 파일에 LM_STUDIO_MODEL=<모델명>을 추가하세요."
        )
    from openai import OpenAI  # lazy import — optional dependency
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
        print("예시:   python query.py \"i-PAC 콘테스트 신청 기간\"")
        print("옵션:")
        print("  --log                결과를 eval_log.jsonl에 기록")
        print("  --log-file <경로>    로그 파일 경로 지정 (기본: eval_log.jsonl)")
        print("  --generate           LM Studio로 자연어 답변 생성")
        print("  --board_type <값>    필터: notice | pr")
        sys.exit(1)

    query_text = sys.argv[1]

    # 플래그·필터 파싱
    do_log      = False
    do_generate = False
    log_file    = Path("eval_log.jsonl")
    filters     = {}
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--log":
            do_log = True
            i += 1
        elif args[i] == "--log-file" and i + 1 < len(args):
            log_file = Path(args[i + 1])
            do_log   = True   # --log-file 지정 시 자동으로 로깅 활성화
            i += 2
        elif args[i] == "--generate":
            do_generate = True
            i += 1
        elif args[i].startswith("--") and i + 1 < len(args):
            filters[args[i][2:]] = args[i + 1]
            i += 2
        else:
            i += 1

    result = rag_search(query_text, filters=filters if filters else None)
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
        log_result(result, log_file=log_file, filters=filters if filters else None)
        print(f"\n[로그] {log_file} 에 기록됨")
