"""
EcoCache RAG 쿼리 인터페이스
- qa_pairs 검색 → 유사도 임계값 미달 시 documents 검색 fallback
- CLI: python query.py "질문 텍스트"
"""

import sys
import logging

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
    hits = client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=top_k,
        query_filter=build_filter(filters),
        with_payload=True,
    )
    return [{"score": h.score, "payload": h.payload} for h in hits]


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
    }
    """
    # 1단계: QA 검색
    qa_results = search(query, config.COLLECTION_QA, top_k=3, filters=filters)

    if qa_results and qa_results[0]["score"] >= config.QA_SIMILARITY_THRESHOLD:
        return {"source": "qa_pairs", "results": qa_results, "query": query}

    # 2단계: 문서 원문 검색
    doc_results = search(query, config.COLLECTION_DOCS, top_k=3, filters=filters)
    return {"source": "documents", "results": doc_results, "query": query}


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
        print("사용법: python query.py \"질문 텍스트\"")
        print("예시:   python query.py \"i-PAC 콘테스트 신청 기간\"")
        sys.exit(1)

    query_text = sys.argv[1]

    # 선택적 필터: --board_type notice
    filters = {}
    args = sys.argv[2:]
    for j in range(0, len(args) - 1, 2):
        if args[j].startswith("--"):
            filters[args[j][2:]] = args[j + 1]

    result = rag_search(query_text, filters=filters if filters else None)
    print_results(result)
