"""
EcoCache RAG API

POST /chat  {"query": "..."}
  → SemanticCacheRetriever.retrieve()  (qa_pairs → documents fallback)
  → generate_answer() via LM Studio    (없으면 response=null)
  → ChatResponse JSON

실행:
  cd api/
  uvicorn main:app --reload --port 8000
"""

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# rag/ 패키지를 Python 경로에 추가 (상대 import 대신 sys.path 사용)
_RAG_DIR  = Path(__file__).parent.parent / "rag"
_ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_RAG_DIR))
sys.path.insert(0, str(_ROOT_DIR))

from baseline_semantic_cache import SemanticCacheRetriever  # noqa: E402
from query import generate_answer                            # noqa: E402
from schemas import ChatRequest, ChatResponse, ChatResult    # noqa: E402


# ── 싱글턴 Retriever (앱 시작 시 모델 로드) ───────────────────────────────────

_retriever: SemanticCacheRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retriever
    _retriever = SemanticCacheRetriever()
    # 모델·클라이언트 사전 로드 (첫 요청 지연 방지)
    from retriever_base import get_model, get_client
    get_model()
    get_client()
    yield


app = FastAPI(title="EcoCache RAG API", version="0.1.0", lifespan=lifespan)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _extract_source_ids(result: dict) -> list[str]:
    """검색 결과에서 doc_id / source_doc_id / qa_id를 추출해 리스트로 반환."""
    ids = []
    for r in result["results"]:
        p = r["payload"]
        doc_id = p.get("doc_id") or p.get("source_doc_id") or p.get("qa_id")
        if doc_id:
            ids.append(doc_id)
    return list(dict.fromkeys(ids))  # 순서 유지하며 중복 제거


def _get_current_ci() -> float | None:
    """carbon_optimizer가 있으면 현재 CI를 반환, 없으면 None."""
    try:
        from carbon_optimizer import get_optimizer
        return get_optimizer().get_current_ci()
    except Exception:
        return None


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.perf_counter()

    try:
        result     = _retriever.retrieve(req.query)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        top1_score = result["results"][0]["score"] if result["results"] else None
        cache_hit  = result["source"] == "qa_pairs"
        sources    = _extract_source_ids(result)

        # LLM 답변 (LM Studio가 없거나 오류 시 null)
        response_text: str | None = None
        try:
            response_text = generate_answer(req.query, result)
        except Exception:
            pass

        return ChatResponse(
            success=True,
            error=None,
            result=ChatResult(
                response=response_text,
                similarity=top1_score,
                cache_hit=cache_hit,
                latency=latency_ms,
                co2_grams=None,
                ci_g_per_kwh=_get_current_ci(),
                sources=sources,
            ),
        )

    except Exception as exc:
        return ChatResponse(success=False, error=str(exc), result=None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
