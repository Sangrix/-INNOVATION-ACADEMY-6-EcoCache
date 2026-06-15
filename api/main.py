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

import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_RAG_DIR    = Path(__file__).parent.parent / "rag"
_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_RAG_DIR))
sys.path.insert(0, str(_CARBON_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

import config
from baseline_semantic_cache import SemanticCacheRetriever
from query import generate_answer, generate_answer_stream
from carbon_monitor import CarbonMonitor
from collector import get_latest_ci_from_db, get_optimizer
from schemas import ChatRequest, ChatResponse, ChatResult

carbon_monitor = CarbonMonitor.from_config(config)
_retriever: SemanticCacheRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retriever
    _retriever = SemanticCacheRetriever()
    from retriever_base import get_client
    get_client()
    yield


app = FastAPI(title="EcoCache RAG API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_source_ids(result: dict) -> list[str]:
    ids = []
    for r in result["results"]:
        p      = r["payload"]
        doc_id = p.get("doc_id") or p.get("source_doc_id") or p.get("qa_id")
        if doc_id:
            ids.append(doc_id)
    return list(dict.fromkeys(ids))


def _extract_cached_answer(result: dict) -> str | None:
    if result["source"] != "qa_pairs" or not result["results"]:
        return None
    answer = result["results"][0]["payload"].get("answer")
    if isinstance(answer, dict):
        return answer.get("text")
    return answer


async def _get_current_ci() -> float | None:
    ci = get_latest_ci_from_db()
    if ci is not None:
        return ci
    try:
        return get_optimizer().get_current_ci()
    except Exception:
        return None


def _get_current_ci_sync() -> float | None:
    # sync counterpart of _get_current_ci() — required for sync generator
    ci = get_latest_ci_from_db()
    if ci is not None:
        return ci
    try:
        return get_optimizer().get_current_ci()
    except Exception:
        return None


def _record_timing(timings: list[dict], stage: str,
                   duration_sec: float, **extra) -> None:
    duration_ms = round(duration_sec * 1000, 2)
    entry = {"stage": stage, "duration_ms": duration_ms}
    entry.update({k: v for k, v in extra.items() if v is not None})
    timings.append(entry)
    detail = " ".join(
        f"{key}={value}" for key, value in extra.items() if value is not None
    )
    logger.info("query_stage stage=%s duration_ms=%.2f %s", stage, duration_ms, detail)


def _stream_chat_generator(query: str):
    start = time.perf_counter()

    if _retriever is None:
        yield f"data: {json.dumps({'type':'error','message':'Retriever not initialized'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    with carbon_monitor.track("api_retrieval", extra={"endpoint": "/chat/stream"}) as r_state:
        result = _retriever.retrieve(query)

    retrieval_co2 = (r_state["metrics"] or {}).get("co2_g", 0.0)
    cache_hit  = result["source"] == "qa_pairs"
    top1_score = result["results"][0]["score"] if result["results"] else None
    sources    = _extract_source_ids(result)
    llm_co2    = 0.0

    if cache_hit:
        answer = _extract_cached_answer(result) or ""
        yield f"data: {json.dumps({'type':'token','text':answer}, ensure_ascii=False)}\n\n"
    else:
        try:
            with carbon_monitor.track("llm_generation") as llm_state:
                for chunk in generate_answer_stream(query, result):
                    yield f"data: {json.dumps({'type':'token','text':chunk}, ensure_ascii=False)}\n\n"
            llm_co2 = (llm_state["metrics"] or {}).get("co2_g", 0.0)
        except Exception as exc:
            yield f"data: {json.dumps({'type':'error','message':str(exc)}, ensure_ascii=False)}\n\n"

    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    co2_total  = round(retrieval_co2 + llm_co2, 6)
    current_ci = _get_current_ci_sync()

    meta = {
        "type":         "meta",
        "cache_hit":    cache_hit,
        "similarity":   top1_score,
        "latency_ms":   latency_ms,
        "co2_grams":    co2_total,
        "ci_g_per_kwh": current_ci,
        "sources":      sources,
    }
    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_generator(req.query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    start = time.perf_counter()
    timings: list[dict] = []

    try:
        if _retriever is None:
            raise RuntimeError("Retriever is not initialized")

        retrieval_start = time.perf_counter()
        with carbon_monitor.track("api_retrieval",
                                  extra={"endpoint": "/chat"}) as state:
            result = _retriever.retrieve(req.query, timings=timings)
        _record_timing(
            timings,
            "api.retrieval_with_carbon",
            time.perf_counter() - retrieval_start,
        )

        retrieval_metrics = state["metrics"] or {}
        if retrieval_metrics:
            _record_timing(
                timings,
                "carbon.api_retrieval",
                retrieval_metrics.get("duration_sec", 0.0),
                co2_g=retrieval_metrics.get("co2_g"),
                energy_kwh=retrieval_metrics.get("energy_kwh"),
                avg_power_W=retrieval_metrics.get("avg_power_W"),
                peak_power_W=retrieval_metrics.get("peak_power_W"),
            )
        co2_grams         = retrieval_metrics.get("co2_g")
        latency_ms        = round((time.perf_counter() - start) * 1000, 1)

        top1_score = result["results"][0]["score"] if result["results"] else None
        cache_hit  = result["source"] == "qa_pairs"
        sources    = _extract_source_ids(result)

        response_text: str | None = None
        if cache_hit:
            cache_response_start = time.perf_counter()
            response_text = _extract_cached_answer(result)
            _record_timing(
                timings,
                "api.cache_hit_response",
                time.perf_counter() - cache_response_start,
            )
        else:
            try:
                llm_start = time.perf_counter()
                response_text = generate_answer(req.query, result)
                _record_timing(
                    timings,
                    "api.llm_generation",
                    time.perf_counter() - llm_start,
                )
                llm_metrics = result.get("metrics", {}).get("llm_generation")
                if llm_metrics and co2_grams is not None:
                    co2_grams = round(co2_grams + llm_metrics.get("co2_g", 0.0), 6)
                elif llm_metrics:
                    co2_grams = llm_metrics.get("co2_g")
            except Exception as e:
                _record_timing(
                    timings,
                    "api.llm_generation",
                    time.perf_counter() - llm_start if "llm_start" in locals() else 0.0,
                    error=type(e).__name__,
                )
                logger.warning("LLM generation failed: %s", e)

        ci_start = time.perf_counter()
        current_ci = await _get_current_ci()
        _record_timing(timings, "api.current_ci", time.perf_counter() - ci_start)

        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        _record_timing(timings, "api.total_request", time.perf_counter() - start)

        return ChatResponse(
            success=True,
            error=None,
            result=ChatResult(
                response=response_text,
                similarity=top1_score,
                cache_hit=cache_hit,
                latency=latency_ms,
                co2_grams=co2_grams,
                ci_g_per_kwh=current_ci,
                sources=sources,
                timings=timings,
            ),
        )

    except Exception as exc:
        return ChatResponse(success=False, error=str(exc), result=None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def serve_ui() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "index.html")
