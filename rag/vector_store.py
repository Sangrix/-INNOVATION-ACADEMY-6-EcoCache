from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from rag.langchain_config import RagSettings, build_settings


@dataclass(frozen=True)
class SearchHit:
    score: float
    payload: dict[str, Any]

    def to_document(self) -> Document:
        return Document(
            page_content=self.payload.get("text", ""),
            metadata=self.payload,
        )

    def source(self, rank: int) -> dict[str, Any]:
        doc_id = self.payload.get("doc_id") or self.payload.get("source_doc_id") or self.payload.get("qa_id")
        title = self.payload.get("title") or self.payload.get("question") or doc_id
        url = self.payload.get("url") or self.payload.get("reference_url") or ""
        return {
            "rank": rank,
            "score": self.score,
            "doc_id": doc_id,
            "title": title,
            "url": url,
        }


def build_filter(filters: dict[str, Any] | None) -> Any:
    if not filters:
        return None

    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    conditions = []
    for key, value in filters.items():
        if isinstance(value, dict):
            conditions.append(FieldCondition(key=key, range=Range(**value)))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


class QdrantVectorSearcher:
    """Qdrant-backed searcher used by the LangChain-style retriever."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or build_settings()
        self._model: Any | None = None
        self._client: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
            self._model = SentenceTransformer(
                self.settings.embed_model_id,
                device=device,
                model_kwargs=kwargs,
            )
        return self._model

    @property
    def client(self) -> Any:
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
            )
        return self._client

    def search(
        self,
        query: str,
        collection: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        query_vector = self.model.encode([query], normalize_embeddings=True).tolist()[0]
        response = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=top_k or self.settings.top_k,
            query_filter=build_filter(filters),
            with_payload=True,
        )
        return [SearchHit(score=hit.score, payload=hit.payload) for hit in response.points]
