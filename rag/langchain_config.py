from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass(frozen=True)
class RagSettings:
    """Runtime settings used by the LangChain-style RAG pipeline."""

    embed_model_id: str = config.EMBED_MODEL_ID
    collection_docs: str = config.COLLECTION_DOCS
    collection_qa: str = config.COLLECTION_QA
    qdrant_url: str = config.QDRANT_URL
    qdrant_api_key: str | None = config.QDRANT_API_KEY
    vector_size: int = config.VECTOR_SIZE
    top_k: int = config.TOP_K
    qa_threshold: float = config.QA_SIMILARITY_THRESHOLD
    chunk_size: int = config.CHUNK_SIZE
    chunk_overlap: int = config.CHUNK_OVERLAP
    chunk_threshold: int = config.CHUNK_THRESHOLD


def build_settings(
    *,
    top_k: int | None = None,
    qa_threshold: float | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RagSettings:
    """Create settings while allowing tuning values to be overridden."""

    base = RagSettings()
    return RagSettings(
        embed_model_id=base.embed_model_id,
        collection_docs=base.collection_docs,
        collection_qa=base.collection_qa,
        qdrant_url=base.qdrant_url,
        qdrant_api_key=base.qdrant_api_key,
        vector_size=base.vector_size,
        top_k=top_k if top_k is not None else base.top_k,
        qa_threshold=qa_threshold if qa_threshold is not None else base.qa_threshold,
        chunk_size=chunk_size if chunk_size is not None else base.chunk_size,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else base.chunk_overlap,
        chunk_threshold=base.chunk_threshold,
    )

