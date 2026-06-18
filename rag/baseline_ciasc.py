"""
Baseline 3 — CIASC (Carbon Intensity Adaptive Semantic Cache)

Electricity Maps API로 현재 탄소 집약도(CI)를 조회해 동적으로
QA 캐시 임계값 θ(t)를 결정한다.

θ(t) = CIASC_BASE_THRESHOLD − α × (ci_norm − 0.5)
ci_norm = clamp((CI − CIASC_CI_MIN) / (CIASC_CI_MAX − CIASC_CI_MIN), 0, 1)
범위: [CIASC_THETA_MIN, CIASC_THETA_MAX]

CI가 높을수록(탄소 배출 多) θ가 낮아져 캐시 히트가 쉬워지고,
CI가 낮을수록 θ가 높아져 더 정확한 문서를 검색한다.

α는 CI 편차에 따라 동적으로 계산된다 (SPEC-CIASC-001):
α(CI) = α_base × (1 + k × |CI_norm − 0.5|)
CI가 중립(~425 g/kWh)에서 멀수록 α 민감도가 증폭된다.
"""

import sys
import time
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import config
from retriever_base import BaseRetriever, search


class CIASCRetriever(BaseRetriever):
    def __init__(self, alpha: float = 0.15, k: float | None = None):
        self.alpha = alpha
        self.k = k if k is not None else config.CIASC_ALPHA_K

    def _calculate_dynamic_alpha(self, ci: float) -> float:
        # @MX:NOTE: α(CI) = α_base × (1 + k × |CI_norm − 0.5|)
        # CI extremes (350 or 500 g/kWh) amplify sensitivity; neutral ~425 g/kWh = no amplification
        ci_norm = max(0.0, min(1.0,
            (ci - config.CIASC_CI_MIN) / (config.CIASC_CI_MAX - config.CIASC_CI_MIN)
        ))
        return round(self.alpha * (1.0 + self.k * abs(ci_norm - 0.5)), 6)

    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K,
                 timings: list[dict] | None = None) -> dict:
        threshold_start = time.perf_counter()
        threshold, alpha_used = self._get_threshold()
        if timings is not None:
            timings.append({
                "stage":      "ciasc.threshold",
                "duration_ms": round((time.perf_counter() - threshold_start) * 1000, 2),
                "threshold":  threshold,
                "alpha_used": alpha_used,
            })

        qa_results = search(
            query,
            config.COLLECTION_QA,
            top_k=top_k,
            filters=filters,
            timings=timings,
            stage_prefix="qa_search",
        )
        qa_top1 = qa_results[0]["score"] if qa_results else None

        if qa_results and qa_top1 >= threshold:
            return {
                "source":        "qa_pairs",
                "results":       qa_results,
                "query":         query,
                "qa_top1_score": qa_top1,
                "alpha_used":    alpha_used,
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
            "alpha_used":    alpha_used,
            "timings":       timings or [],
        }

    def _get_threshold(self) -> tuple[float, float]:
        try:
            from carbon_optimizer import get_optimizer
            opt = get_optimizer()
            ci = opt.get_current_ci()
            alpha_used = self._calculate_dynamic_alpha(ci) if ci is not None else self.alpha
            return opt.get_adaptive_threshold(ci=ci, alpha=alpha_used), alpha_used
        except Exception:
            return config.QA_SIMILARITY_THRESHOLD, self.alpha
