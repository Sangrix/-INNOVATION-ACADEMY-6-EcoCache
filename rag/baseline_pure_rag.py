"""
Baseline 1 — Pure RAG

documents 컬렉션만 사용하는 순수 벡터 검색 베이스라인.
qa_pairs를 일절 참조하지 않으며, 항상 "documents"를 source로 반환한다.
"""

import config
from retriever_base import BaseRetriever, search


class PureRAGRetriever(BaseRetriever):
    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K) -> dict:
        results = search(query, config.COLLECTION_DOCS, top_k=top_k, filters=filters)
        return {
            "source":        "documents",
            "results":       results,
            "query":         query,
            "qa_top1_score": None,
        }
