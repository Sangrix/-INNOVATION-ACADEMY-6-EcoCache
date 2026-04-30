"""
공통 Retriever 기반 모듈

- 모델·클라이언트 싱글턴
- 단일 컬렉션 벡터 검색
- 두 Baseline이 상속할 BaseRetriever 추상 클래스
"""

from abc import ABC, abstractmethod

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from sentence_transformers import SentenceTransformer

import config

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
                 top_k: int = config.TOP_K) -> dict:
        ...
