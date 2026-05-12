from __future__ import annotations

from typing import Any

from rag.semantic_cache_retriever import RetrievalResult


def to_chat_response(
    result: RetrievalResult,
    *,
    latency_ms: float,
    answer: str | None = None,
    co2_grams: float | None = None,
    ci_g_per_kwh: float | None = None,
) -> dict[str, Any]:
    """Convert internal RAG output to the web/API response shape."""

    final_answer = answer if answer is not None else result.answer
    return {
        "answer": final_answer,
        "cache_hit": result.cache_hit,
        "similarity": result.top1_similarity,
        "latency_ms": latency_ms,
        "co2_grams": co2_grams,
        "ci_g_per_kwh": ci_g_per_kwh,
        "sources": result.sources,
        "retrieval": {
            "source": result.source,
            "qa_top1_score": result.qa_top1_score,
            "threshold": result.threshold,
            "top_k": result.top_k,
        },
    }

