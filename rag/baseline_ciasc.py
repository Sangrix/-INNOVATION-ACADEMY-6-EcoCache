"""
Baseline 3 — CIASC (Carbon Intensity Adaptive Semantic Cache)

Electricity Maps API로 현재 탄소 집약도(CI)를 조회해 동적으로
QA 캐시 임계값 θ(t)를 결정한다.

θ(t) = CIASC_BASE_THRESHOLD − α × (ci_norm − 0.5)
ci_norm = clamp((CI − CIASC_CI_MIN) / (CIASC_CI_MAX − CIASC_CI_MIN), 0, 1)
범위: [CIASC_THETA_MIN, CIASC_THETA_MAX]

CI가 높을수록(탄소 배출 多) θ가 낮아져 캐시 히트가 쉬워지고,
CI가 낮을수록 θ가 높아져 더 정확한 문서를 검색한다.
"""

import sys
import time
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import config
from retriever_base import BaseRetriever, search


class CIASCRetriever(BaseRetriever):
    def __init__(self, alpha: float = 0.15):
        self.alpha = alpha

    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K,
                 timings: list[dict] | None = None) -> dict:
        threshold_start = time.perf_counter()
        threshold = self._get_threshold()
        if timings is not None:
            timings.append({
                "stage": "ciasc.threshold",
                "duration_ms": round((time.perf_counter() - threshold_start) * 1000, 2),
                "threshold": threshold,
            })

        qa_results = search(
            query,
            config.COLLECTION_QA,
            top_k=top_k,
            filters=filters,
            timings=timings,
            stage_prefix="qa_search",
        )
        qa_top1    = qa_results[0]["score"] if qa_results else None

        if qa_results and qa_top1 >= threshold:
            return {
                "source":        "qa_pairs",
                "results":       qa_results,
                "query":         query,
                "qa_top1_score": qa_top1,
                "timings":       timings or [],
            }

        doc_results = search(
            query,
            config.COLLECTION_DOCS,
            top_k=top_k,
            filters=filters,
            timings=timings,
            stage_prefix="document_search",
        )
        return {
            "source":        "documents",
            "results":       doc_results,
            "query":         query,
            "qa_top1_score": qa_top1,
            "timings":       timings or [],
        }

    def _get_threshold(self) -> float:
        try:
            from carbon_optimizer import get_optimizer
            opt = get_optimizer()
            ci  = opt.get_current_ci()
            return opt.get_adaptive_threshold(ci=ci, alpha=self.alpha)
        except Exception:
            return config.QA_SIMILARITY_THRESHOLD
