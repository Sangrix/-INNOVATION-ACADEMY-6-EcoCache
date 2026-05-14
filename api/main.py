"""
EcoCache RAG API

POST /chat  {"query": "..."}
  → SemanticCacheRetriever.retrieve()
  → CarbonMonitor로 CO2 실측
  → generate_answer() via LM Studio (없으면 null)
  → ChatResponse (cache_hit, co2_grams 포함)

실행:
  cd api/
  uvicorn main:app --reload --port 8000
"""

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

_RAG_DIR    = Path(__file__).parent.parent / "rag"
_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_RAG_DIR))
sys.path.insert(0, str(_CARBON_DIR))

from fastapi import FastAPI

import config
from baseline_semantic_cache import SemanticCacheRetriever
from query import generate_answer
from carbon_monitor import CarbonMonitor
from schemas import ChatRequest, ChatResponse, ChatResult

carbon_monitor = CarbonMonitor.from_config(config)
_retriever: SemanticCacheRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retriever
    _retriever = SemanticCacheRetriever()
    from retriever_base import get_model, get_client
    get_model()
    get_client()
    yield


app = FastAPI(title="EcoCache RAG API", version="0.2.0", lifespan=lifespan)


def _extract_source_ids(result: dict) -> list[str]:
    ids = []
    for r in result["results"]:
        p      = r["payload"]
        doc_id = p.get("doc_id") or p.get("source_doc_id") or p.get("qa_id")
        if doc_id:
            ids.append(doc_id)
    return list(dict.fromkeys(ids))


def _get_current_ci() -> float | None:
    try:
        from carbon_optimizer import get_optimizer
        return get_optimizer().get_current_ci()
    except Exception:
        return None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.perf_counter()

    try:
        with carbon_monitor.track("api_retrieval",
                                  extra={"endpoint": "/chat"}) as state:
            result = _retriever.retrieve(req.query)

        retrieval_metrics = state["metrics"] or {}
        co2_grams         = retrieval_metrics.get("co2_g")
        latency_ms        = round((time.perf_counter() - start) * 1000, 1)

        top1_score = result["results"][0]["score"] if result["results"] else None
        cache_hit  = result["source"] == "qa_pairs"
        sources    = _extract_source_ids(result)

        response_text: str | None = None
        try:
            with carbon_monitor.track("api_llm_generation") as llm_state:
                response_text = generate_answer(req.query, result)
            if llm_state["metrics"] and co2_grams is not None:
                co2_grams = round(co2_grams + llm_state["metrics"].get("co2_g", 0.0), 6)
            elif llm_state["metrics"]:
                co2_grams = llm_state["metrics"].get("co2_g")
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
                co2_grams=co2_grams,
                ci_g_per_kwh=_get_current_ci(),
                sources=sources,
            ),
        )

    except Exception as exc:
        return ChatResponse(success=False, error=str(exc), result=None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
