from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from rag.retrieval_eval import run_eval


def _parse_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def run_sweep(
    query_file: Path,
    *,
    top_ks: list[int],
    thresholds: list[float],
    limit: int | None,
    sample_mode: str,
    warmup: bool,
) -> dict:
    runs = []
    for top_k in top_ks:
        for threshold in thresholds:
            result = run_eval(
                query_file,
                top_k=top_k,
                threshold=threshold,
                limit=limit,
                sample_mode=sample_mode,
                warmup=warmup,
            )
            runs.append(
                {
                    "top_k": top_k,
                    "threshold": threshold,
                    **result["summary"],
                    "result": result,
                }
            )

    summary = [
        {
            "top_k": run["top_k"],
            "threshold": run["threshold"],
            "judged": run["judged"],
            "top1_accuracy": run["top1_accuracy"],
            "top3_accuracy": run["top3_accuracy"],
            "avg_similarity": run["avg_similarity"],
            "cache_hit_rate": run["cache_hit_rate"],
            "wrong_cache_hit_count": run["wrong_cache_hit_count"],
            "source_url_ok_rate": run["source_url_ok_rate"],
            "avg_latency_ms": run["avg_latency_ms"],
        }
        for run in runs
    ]
    return {
        "config": {
            "query_file": str(query_file),
            "top_ks": top_ks,
            "thresholds": thresholds,
            "limit": limit,
            "sample_mode": sample_mode,
            "warmup": warmup,
        },
        "summary": summary,
        "runs": runs,
    }


def write_outputs(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "retrieval_sweep_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    csv_path = output_dir / "retrieval_sweep_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "top_k",
                "threshold",
                "judged",
                "top1_accuracy",
                "top3_accuracy",
                "avg_similarity",
                "cache_hit_rate",
                "wrong_cache_hit_count",
                "source_url_ok_rate",
                "avg_latency_ms",
            ],
        )
        writer.writeheader()
        writer.writerows(result["summary"])

    md_lines = [
        "# Retrieval Sweep Summary",
        "",
        "| top_k | threshold | judged | top1_accuracy | top3_accuracy | avg_similarity | cache_hit_rate | wrong_cache_hit_count | source_url_ok_rate | avg_latency_ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result["summary"]:
        md_lines.append(
            "| {top_k} | {threshold} | {judged} | {top1_accuracy} | {top3_accuracy} | {avg_similarity} | {cache_hit_rate} | {wrong_cache_hit_count} | {source_url_ok_rate} | {avg_latency_ms} |".format(
                **row
            )
        )
    (output_dir / "retrieval_sweep_summary.md").write_text(
        "\n".join(md_lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multiple top-k/threshold retrieval evaluations.")
    parser.add_argument("--query-file", type=Path, default=Path("test_queries.json"))
    parser.add_argument("--top-ks", default="3,5", help="Comma-separated top-k values")
    parser.add_argument("--thresholds", default="0.75,0.8,0.85", help="Comma-separated threshold values")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--sample-mode", choices=["first", "even"], default="even")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/retrieval_sweep"))
    args = parser.parse_args()

    result = run_sweep(
        args.query_file,
        top_ks=_parse_ints(args.top_ks),
        thresholds=_parse_floats(args.thresholds),
        limit=args.limit,
        sample_mode=args.sample_mode,
        warmup=not args.no_warmup,
    )
    write_outputs(result, args.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nSaved: {args.output_dir}")


if __name__ == "__main__":
    main()
