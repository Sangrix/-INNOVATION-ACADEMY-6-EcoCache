from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.langchain_pipeline import LangChainRagPipeline


def _load_queries(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _source_ids(response: dict) -> list[str]:
    return [source.get("doc_id", "") for source in response.get("sources", [])]


def run_eval(
    query_file: Path,
    *,
    top_k: int,
    threshold: float,
    limit: int | None = None,
) -> dict:
    pipeline = LangChainRagPipeline(top_k=top_k, threshold=threshold)
    rows = []
    top1_hits = 0
    top3_hits = 0
    judged = 0

    for item in _load_queries(query_file)[:limit]:
        response = pipeline.run(item["query"])
        expected = set(item.get("expected_doc_ids") or [])
        retrieved = _source_ids(response)
        top1_hit = bool(expected and retrieved[:1] and retrieved[0] in expected)
        top3_hit = bool(expected and any(doc_id in expected for doc_id in retrieved[:3]))

        if expected:
            judged += 1
            top1_hits += int(top1_hit)
            top3_hits += int(top3_hit)

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
                "sources": response["sources"],
            }
        )

    return {
        "config": {"top_k": top_k, "threshold": threshold, "limit": limit},
        "summary": {
            "judged": judged,
            "top1_accuracy": round(top1_hits / judged, 4) if judged else None,
            "top3_accuracy": round(top3_hits / judged, 4) if judged else None,
            "cache_hit_rate": round(sum(1 for row in rows if row["cache_hit"]) / len(rows), 4)
            if rows
            else None,
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
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = run_eval(args.query_file, top_k=args.top_k, threshold=args.threshold, limit=args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

