from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document

import config


def load_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _doc_text(item: dict) -> str:
    title = item.get("meta", {}).get("title", "")
    published_at = item.get("meta", {}).get("published_at", "")
    raw_text = item.get("content", {}).get("raw_text", "").strip()
    if raw_text:
        return f"[title] {title}\n[date] {published_at}\n\n{raw_text}"
    return f"[title] {title}\n[date] {published_at}"


def load_notice_documents(paths: Iterable[Path] | None = None) -> list[Document]:
    """Load collected notice JSON files as LangChain Document objects."""

    documents: list[Document] = []
    for path in paths or config.DOC_PATHS:
        for item in load_json(path):
            source = item.get("source", {})
            meta = item.get("meta", {})
            documents.append(
                Document(
                    page_content=_doc_text(item),
                    metadata={
                        "type": "document",
                        "doc_id": item.get("doc_id", ""),
                        "title": meta.get("title", ""),
                        "published_at": meta.get("published_at", ""),
                        "board_type": source.get("board_type", ""),
                        "board_name": source.get("board_name", ""),
                        "url": source.get("url", ""),
                    },
                )
            )
    return documents


def load_qa_documents(paths: Iterable[Path] | None = None) -> list[Document]:
    """Load QA JSON files as LangChain Document objects for semantic cache."""

    documents: list[Document] = []
    for path in paths or config.QA_PATHS:
        for item in load_json(path):
            question = item.get("question", {}).get("text", "")
            answer = item.get("answer", {}).get("text", "")
            reference_url = item.get("answer", {}).get("reference_url", "")
            documents.append(
                Document(
                    page_content=f"Q: {question}\nA: {answer}",
                    metadata={
                        "type": "qa_pair",
                        "qa_id": item.get("qa_id", ""),
                        "source_doc_id": item.get("source_doc_id", ""),
                        "question": question,
                        "answer": answer,
                        "reference_url": reference_url,
                    },
                )
            )
    return documents

