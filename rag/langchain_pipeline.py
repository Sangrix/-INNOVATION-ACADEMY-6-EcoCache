from __future__ import annotations

import argparse
import json
import time
from functools import lru_cache
from typing import Any

from rag.answer_generator import RagAnswerGenerator
from rag.langchain_config import build_settings
from rag.response_adapter import to_chat_response
from rag.semantic_cache_retriever import SemanticCacheRetriever


class LangChainRagPipeline:
    """Retrieval-first RAG pipeline prepared for the web demo."""

    def __init__(
        self,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self.settings = build_settings(top_k=top_k, qa_threshold=threshold)
        self.retriever = SemanticCacheRetriever(self.settings)
        self.answer_generator = RagAnswerGenerator()

    def warmup(self) -> None:
        """Load shared runtime resources once for a long-running service."""

        self.retriever.warmup()

    def close(self) -> None:
        """Close resources when this pipeline is used from a one-shot CLI."""

        self.retriever.close()

    def run(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        qa_top_k: int | None = None,
        doc_top_k: int | None = None,
        generate: bool = True,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.retriever.retrieve(query, filters=filters, qa_top_k=qa_top_k, doc_top_k=doc_top_k)
        generated = self.answer_generator.generate(query, result, use_llm=use_llm) if generate else None
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return to_chat_response(result, latency_ms=latency_ms, generated=generated)


@lru_cache(maxsize=16)
def get_cached_pipeline(top_k: int | None = None, threshold: float | None = None) -> LangChainRagPipeline:
    """Reuse the embedding model and Qdrant client across repeated questions."""

    pipeline = LangChainRagPipeline(top_k=top_k, threshold=threshold)
    pipeline.warmup()
    return pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LangChain-style EcoCache RAG pipeline.")
    parser.add_argument("query", help="User query")
    parser.add_argument("--top-k", type=int, default=None, help="Number of retrieved candidates")
    parser.add_argument("--qa-top-k", type=int, default=None, help="Number of QA cache candidates")
    parser.add_argument("--doc-top-k", type=int, default=None, help="Number of document candidates")
    parser.add_argument("--threshold", type=float, default=None, help="QA semantic-cache threshold")
    parser.add_argument("--board-type", default=None, help="Optional board_type metadata filter")
    parser.add_argument("--no-generate", action="store_true", help="Return retrieval result without final answer")
    parser.add_argument("--no-llm", action="store_true", help="Use retrieval fallback even if LM Studio is configured")
    args = parser.parse_args()

    filters = {"board_type": args.board_type} if args.board_type else None
    pipeline = LangChainRagPipeline(top_k=args.top_k, threshold=args.threshold)
    try:
        response = pipeline.run(
            args.query,
            filters=filters,
            qa_top_k=args.qa_top_k,
            doc_top_k=args.doc_top_k,
            generate=not args.no_generate,
            use_llm=not args.no_llm,
        )
        print(json.dumps(response, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
