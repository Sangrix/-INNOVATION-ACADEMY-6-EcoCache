from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.langchain_config import RagSettings, build_settings
from rag.vector_store import QdrantVectorSearcher, SearchHit


@dataclass
class RetrievalResult:
    query: str
    source: str
    cache_hit: bool
    threshold: float
    top_k: int
    qa_top_k: int
    doc_top_k: int
    qa_top1_score: float | None
    top1_similarity: float | None
    results: list[SearchHit]
    answer: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "results": [{"score": hit.score, "payload": hit.payload} for hit in self.results],
            "query": self.query,
            "qa_top1_score": self.qa_top1_score,
            "qa_top_k": self.qa_top_k,
            "doc_top_k": self.doc_top_k,
        }


class SemanticCacheRetriever:
    """Semantic-cache retriever: QA cache first, document fallback second."""

    def __init__(
        self,
        settings: RagSettings | None = None,
        searcher: QdrantVectorSearcher | None = None,
    ) -> None:
        self.settings = settings or build_settings()
        self.searcher = searcher or QdrantVectorSearcher(self.settings)

    def warmup(self) -> None:
        """Prepare the embedding model and vector store connection once."""

        self.searcher.warmup()

    def close(self) -> None:
        """Release vector store resources in short-lived processes."""

        self.searcher.close()

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        qa_top_k: int | None = None,
        doc_top_k: int | None = None,
        threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        top_k = top_k or self.settings.top_k
        qa_top_k = qa_top_k or top_k
        doc_top_k = doc_top_k or top_k
        threshold = threshold if threshold is not None else self.settings.qa_threshold
        query_vector = self.searcher.encode_query(query)

        qa_hits = self.searcher.search_by_vector(
            query_vector,
            self.settings.collection_qa,
            top_k=qa_top_k,
            filters=filters,
        )
        qa_top1 = qa_hits[0].score if qa_hits else None

        if qa_hits and qa_top1 is not None and qa_top1 >= threshold:
            answer = qa_hits[0].payload.get("answer")
            return RetrievalResult(
                query=query,
                source="qa_pairs",
                cache_hit=True,
                threshold=threshold,
                top_k=doc_top_k,
                qa_top_k=qa_top_k,
                doc_top_k=doc_top_k,
                qa_top1_score=qa_top1,
                top1_similarity=qa_top1,
                results=qa_hits,
                answer=answer,
                sources=_dedupe_sources(qa_hits),
            )

        doc_hits = self.searcher.search_by_vector(
            query_vector,
            self.settings.collection_docs,
            top_k=doc_top_k,
            filters=filters,
        )
        doc_top1 = doc_hits[0].score if doc_hits else None
        return RetrievalResult(
            query=query,
            source="documents",
            cache_hit=False,
            threshold=threshold,
            top_k=doc_top_k,
            qa_top_k=qa_top_k,
            doc_top_k=doc_top_k,
            qa_top1_score=qa_top1,
            top1_similarity=doc_top1,
            results=doc_hits,
            answer=None,
            sources=_dedupe_sources(doc_hits),
        )


def _dedupe_sources(hits: list[SearchHit]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for index, hit in enumerate(hits, start=1):
        source = hit.source(index)
        key = source.get("url") or source.get("doc_id") or str(index)
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources
