from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.langchain_pipeline import LangChainRagPipeline


def _load_queries(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _select_queries(items: list[dict], limit: int | None, sample_mode: str) -> list[dict]:
    if limit is None or limit >= len(items):
        return items
    if sample_mode == "even":
        if limit <= 1:
            return items[:limit]
        step = (len(items) - 1) / (limit - 1)
        indexes = [round(i * step) for i in range(limit)]
        return [items[index] for index in indexes]
    return items[:limit]


def _source_ids(response: dict) -> list[str]:
    return [source.get("doc_id", "") for source in response.get("sources", [])]


def run_eval(
    query_file: Path,
    *,
    top_k: int,
    threshold: float,
    limit: int | None = None,
    sample_mode: str = "first",
    warmup: bool = True,
    qa_top_k: int | None = None,
    doc_top_k: int | None = None,
) -> dict:
    pipeline = LangChainRagPipeline(top_k=top_k, threshold=threshold)
    if warmup:
        pipeline.run("warmup query", qa_top_k=qa_top_k, doc_top_k=doc_top_k)

    query_items = _select_queries(_load_queries(query_file), limit, sample_mode)
    rows = []
    top1_hits = 0
    top3_hits = 0
    judged = 0
    source_url_ok = 0
    wrong_cache_hits = 0

    for item in query_items:
        response = pipeline.run(item["query"], qa_top_k=qa_top_k, doc_top_k=doc_top_k)
        expected = set(item.get("expected_doc_ids") or [])
        retrieved = _source_ids(response)
        top1_hit = bool(expected and retrieved[:1] and retrieved[0] in expected)
        top3_hit = bool(expected and any(doc_id in expected for doc_id in retrieved[:3]))
        has_source_url = any(source.get("url") for source in response.get("sources", []))

        if expected:
            judged += 1
            top1_hits += int(top1_hit)
            top3_hits += int(top3_hit)
            wrong_cache_hits += int(response["cache_hit"] and not top3_hit)
        source_url_ok += int(has_source_url)

        rows.append(
            {
                "id": item.get("id"),
                "query": item.get("query"),
                "expected_doc_ids": list(expected),
                "retrieved_doc_ids": retrieved,
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "cache_hit": response["cache_hit"],
                "similarity": response["similarity"],
                "latency_ms": response["latency_ms"],
                "source_url_ok": has_source_url,
                "sources": response["sources"],
            }
        )

    return {
        "config": {
            "top_k": top_k,
            "qa_top_k": qa_top_k,
            "doc_top_k": doc_top_k,
            "threshold": threshold,
            "limit": limit,
            "sample_mode": sample_mode,
            "warmup": warmup,
        },
        "summary": {
            "judged": judged,
            "top1_accuracy": round(top1_hits / judged, 4) if judged else None,
            "top3_accuracy": round(top3_hits / judged, 4) if judged else None,
            "avg_similarity": round(
                sum(row["similarity"] for row in rows if row["similarity"] is not None)
                / max(sum(1 for row in rows if row["similarity"] is not None), 1),
                4,
            )
            if rows
            else None,
            "cache_hit_rate": round(sum(1 for row in rows if row["cache_hit"]) / len(rows), 4)
            if rows
            else None,
            "wrong_cache_hit_count": wrong_cache_hits,
            "source_url_ok_rate": round(source_url_ok / len(rows), 4) if rows else None,
            "avg_latency_ms": round(sum(row["latency_ms"] for row in rows) / len(rows), 1)
            if rows
            else None,
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval settings.")
    parser.add_argument("--query-file", type=Path, default=Path("test_queries.json"))
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample-mode", choices=["first", "even"], default="first")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = run_eval(
        args.query_file,
        top_k=args.top_k,
        threshold=args.threshold,
        limit=args.limit,
        sample_mode=args.sample_mode,
        warmup=not args.no_warmup,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
