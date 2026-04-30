"""
Baseline 2 — Semantic Cache RAG

qa_pairs 컬렉션을 먼저 검색하여 시맨틱 캐시로 활용한다.
top-1 유사도가 QA_SIMILARITY_THRESHOLD 이상이면 qa_pairs 결과를 반환(캐시 히트).
미달 시 documents 컬렉션으로 fallback(캐시 미스).
"""

import config
from retriever_base import BaseRetriever, search


class SemanticCacheRetriever(BaseRetriever):
    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K) -> dict:
        qa_results = search(query, config.COLLECTION_QA, top_k=top_k, filters=filters)
        qa_top1 = qa_results[0]["score"] if qa_results else None

        if qa_results and qa_top1 >= config.QA_SIMILARITY_THRESHOLD:
            return {
                "source":        "qa_pairs",
                "results":       qa_results,
                "query":         query,
                "qa_top1_score": qa_top1,
            }

        doc_results = search(query, config.COLLECTION_DOCS, top_k=top_k, filters=filters)
        return {
            "source":        "documents",
            "results":       doc_results,
            "query":         query,
            "qa_top1_score": qa_top1,
        }
