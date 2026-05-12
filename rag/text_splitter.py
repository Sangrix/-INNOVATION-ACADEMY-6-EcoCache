from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.langchain_config import RagSettings, build_settings


def build_text_splitter(settings: RagSettings | None = None) -> RecursiveCharacterTextSplitter:
    settings = settings or build_settings()
    return RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", ". ", " "],
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
    )


def split_documents(
    documents: list[Document],
    settings: RagSettings | None = None,
) -> list[Document]:
    """Split documents with the current chunk tuning values."""

    return build_text_splitter(settings).split_documents(documents)

