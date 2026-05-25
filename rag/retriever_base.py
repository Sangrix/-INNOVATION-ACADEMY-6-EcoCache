"""
공통 Retriever 기반 모듈

- 모델·클라이언트 싱글턴
- 단일 컬렉션 벡터 검색
- 두 Baseline이 상속할 BaseRetriever 추상 클래스
"""

from abc import ABC, abstractmethod
import logging
import time
from threading import Lock

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from sentence_transformers import SentenceTransformer

import config

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_client: QdrantClient | None = None
_model_lock = Lock()
_client_lock = Lock()


def _record_timing(timings: list[dict] | None, stage: str,
                   duration_sec: float, **extra) -> None:
    duration_ms = round(duration_sec * 1000, 2)
    if timings is not None:
        entry = {"stage": stage, "duration_ms": duration_ms}
        entry.update({k: v for k, v in extra.items() if v is not None})
        timings.append(entry)
    detail = " ".join(
        f"{key}={value}" for key, value in extra.items() if value is not None
    )
    logger.info("query_stage stage=%s duration_ms=%.2f %s", stage, duration_ms, detail)


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
                _model = SentenceTransformer(
                    config.EMBED_MODEL_ID,
                    device=device,
                    model_kwargs=kwargs,
                )
    return _model


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
    return _client


def build_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None
    conditions = []
    for key, value in filters.items():
        if isinstance(value, dict):
            conditions.append(FieldCondition(key=key, range=Range(**value)))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


def search(query: str, collection: str, top_k: int = config.TOP_K,
           filters: dict | None = None,
           timings: list[dict] | None = None,
           stage_prefix: str | None = None) -> list[dict]:
    """단일 컬렉션 Dense 검색. 결과를 dict 리스트로 반환."""
    prefix = stage_prefix or collection
    total_start = time.perf_counter()

    stage_start = time.perf_counter()
    model = get_model()
    _record_timing(
        timings,
        f"{prefix}.model_ready",
        time.perf_counter() - stage_start,
        collection=collection,
    )

    stage_start = time.perf_counter()
    client = get_client()
    _record_timing(
        timings,
        f"{prefix}.client_ready",
        time.perf_counter() - stage_start,
        collection=collection,
    )

    stage_start = time.perf_counter()
    query_vector = model.encode([query], normalize_embeddings=True).tolist()[0]
    _record_timing(
        timings,
        f"{prefix}.query_embedding",
        time.perf_counter() - stage_start,
        collection=collection,
    )

    stage_start = time.perf_counter()
    query_filter = build_filter(filters)
    _record_timing(
        timings,
        f"{prefix}.build_filter",
        time.perf_counter() - stage_start,
        collection=collection,
        has_filters=bool(filters),
    )

    stage_start = time.perf_counter()
    response = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )
    _record_timing(
        timings,
        f"{prefix}.qdrant_query",
        time.perf_counter() - stage_start,
        collection=collection,
        top_k=top_k,
    )

    stage_start = time.perf_counter()
    results = [{"score": h.score, "payload": h.payload} for h in response.points]
    _record_timing(
        timings,
        f"{prefix}.format_results",
        time.perf_counter() - stage_start,
        collection=collection,
        result_count=len(results),
    )

    _record_timing(
        timings,
        f"{prefix}.total",
        time.perf_counter() - total_start,
        collection=collection,
        result_count=len(results),
    )
    return results


class BaseRetriever(ABC):
    """
    두 Baseline이 구현해야 하는 공통 인터페이스.

    반환 dict 형식 (eval_dashboard 호환):
    {
        "source": "documents" | "qa_pairs",
        "results": [{"score": float, "payload": dict}, ...],
        "query": str,
        "qa_top1_score": float | None,
    }
    """

    @abstractmethod
    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K,
                 timings: list[dict] | None = None) -> dict:
        ...
