from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from rag.retrieval_eval import run_eval


def _parse_pairs(value: str) -> list[tuple[int, int]]:
    pairs = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        qa, doc = item.split(":")
        pairs.append((int(qa), int(doc)))
    return pairs


def run_split_topk_sweep(
    query_file: Path,
    *,
    pairs: list[tuple[int, int]],
    threshold: float,
    limit: int | None,
) -> dict:
    rows = []
    for qa_top_k, doc_top_k in pairs:
        result = run_eval(
            query_file,
            top_k=doc_top_k,
            threshold=threshold,
            limit=limit,
            sample_mode="even",
            warmup=True,
            qa_top_k=qa_top_k,
            doc_top_k=doc_top_k,
        )
        rows.append(
            {
                "qa_top_k": qa_top_k,
                "doc_top_k": doc_top_k,
                "threshold": threshold,
                **result["summary"],
                "result": result,
            }
        )

    summary = [
        {
            "qa_top_k": row["qa_top_k"],
            "doc_top_k": row["doc_top_k"],
            "threshold": row["threshold"],
            "judged": row["judged"],
            "top1_accuracy": row["top1_accuracy"],
            "top3_accuracy": row["top3_accuracy"],
            "avg_similarity": row["avg_similarity"],
            "cache_hit_rate": row["cache_hit_rate"],
            "wrong_cache_hit_count": row["wrong_cache_hit_count"],
            "source_url_ok_rate": row["source_url_ok_rate"],
            "avg_latency_ms": row["avg_latency_ms"],
        }
        for row in rows
    ]
    return {
        "config": {
            "query_file": str(query_file),
            "pairs": [{"qa_top_k": qa, "doc_top_k": doc} for qa, doc in pairs],
            "threshold": threshold,
            "limit": limit,
        },
        "summary": summary,
        "runs": rows,
    }


def write_outputs(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "split_topk_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "qa_top_k",
        "doc_top_k",
        "threshold",
        "judged",
        "top1_accuracy",
        "top3_accuracy",
        "avg_similarity",
        "cache_hit_rate",
        "wrong_cache_hit_count",
        "source_url_ok_rate",
        "avg_latency_ms",
    ]
    with (output_dir / "split_topk_summary.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result["summary"])

    lines = [
        "# Split Top-k Sweep Summary",
        "",
        "| qa_top_k | doc_top_k | threshold | Top-1 | Top-3 | cache hit | wrong cache | source URL OK | avg latency |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result["summary"]:
        lines.append(
            "| {qa_top_k} | {doc_top_k} | {threshold} | {top1_accuracy} | {top3_accuracy} | {cache_hit_rate} | {wrong_cache_hit_count} | {source_url_ok_rate} | {avg_latency_ms}ms |".format(
                **row
            )
        )
    (output_dir / "split_topk_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run split QA/document top-k retrieval tuning.")
    parser.add_argument("--query-file", type=Path, default=Path("test_queries.json"))
    parser.add_argument("--pairs", default="3:5,5:5,3:7", help="Comma-separated qa:doc top-k pairs")
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/split_topk_sweep"))
    args = parser.parse_args()

    result = run_split_topk_sweep(
        args.query_file,
        pairs=_parse_pairs(args.pairs),
        threshold=args.threshold,
        limit=args.limit,
    )
    write_outputs(result, args.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nSaved: {args.output_dir}")


if __name__ == "__main__":
    main()

