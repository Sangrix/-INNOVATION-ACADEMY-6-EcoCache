from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


CHUNK_PRESETS = {
    "A": {"chunk_size": 1000, "chunk_overlap": 100},
    "B": {"chunk_size": 1500, "chunk_overlap": 150},
    "C": {"chunk_size": 2000, "chunk_overlap": 200},
}


def _parse_presets(value: str) -> list[str]:
    presets = [item.strip().upper() for item in value.split(",") if item.strip()]
    unknown = [preset for preset in presets if preset not in CHUNK_PRESETS]
    if unknown:
        raise ValueError(f"Unknown chunk preset(s): {', '.join(unknown)}")
    return presets


def _run(command: list[str], *, env: dict[str, str]) -> None:
    print("\n$", " ".join(command), flush=True)
    subprocess.run(command, check=True, env=env)


def _read_summary(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)["summary"]


def run_chunk_sweep(
    *,
    presets: list[str],
    top_k: int,
    threshold: float,
    output_dir: Path,
    keep_qdrant: bool,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for preset_name in presets:
        preset = CHUNK_PRESETS[preset_name]
        run_dir = output_dir / f"chunk_{preset_name.lower()}"
        qdrant_path = run_dir / "qdrant_local"
        sweep_dir = run_dir / "retrieval_sweep"
        run_dir.mkdir(parents=True, exist_ok=True)

        if qdrant_path.exists():
            shutil.rmtree(qdrant_path)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["QDRANT_LOCAL_PATH"] = str(qdrant_path)
        env["CHUNK_SIZE"] = str(preset["chunk_size"])
        env["CHUNK_OVERLAP"] = str(preset["chunk_overlap"])

        _run([sys.executable, "embed_pipeline.py"], env=env)
        _run(
            [
                sys.executable,
                "-m",
                "rag.retrieval_sweep",
                "--query-file",
                "test_queries.json",
                "--top-ks",
                str(top_k),
                "--thresholds",
                str(threshold),
                "--output-dir",
                str(sweep_dir),
            ],
            env=env,
        )

        summary = _read_summary(sweep_dir / "retrieval_sweep_results.json")[0]
        row = {
            "preset": preset_name,
            "chunk_size": preset["chunk_size"],
            "chunk_overlap": preset["chunk_overlap"],
            **summary,
        }
        rows.append(row)

        if not keep_qdrant and qdrant_path.exists():
            shutil.rmtree(qdrant_path)

    result = {
        "config": {
            "presets": presets,
            "top_k": top_k,
            "threshold": threshold,
        },
        "summary": rows,
    }
    write_outputs(result, output_dir)
    return result


def write_outputs(result: dict, output_dir: Path) -> None:
    (output_dir / "chunk_sweep_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "preset",
        "chunk_size",
        "chunk_overlap",
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
    ]
    with (output_dir / "chunk_sweep_summary.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result["summary"])

    lines = [
        "# Chunk Sweep Summary",
        "",
        "| preset | chunk_size | chunk_overlap | top_k | threshold | Top-1 | Top-3 | cache hit | wrong cache | source URL OK | avg latency |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result["summary"]:
        lines.append(
            "| {preset} | {chunk_size} | {chunk_overlap} | {top_k} | {threshold} | {top1_accuracy} | {top3_accuracy} | {cache_hit_rate} | {wrong_cache_hit_count} | {source_url_ok_rate} | {avg_latency_ms}ms |".format(
                **row
            )
        )
    (output_dir / "chunk_sweep_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run chunk-size retrieval tuning.")
    parser.add_argument("--presets", default="A,B,C", help="Comma-separated chunk presets: A,B,C")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/chunk_sweep"))
    parser.add_argument("--keep-qdrant", action="store_true")
    args = parser.parse_args()

    result = run_chunk_sweep(
        presets=_parse_presets(args.presets),
        top_k=args.top_k,
        threshold=args.threshold,
        output_dir=args.output_dir,
        keep_qdrant=args.keep_qdrant,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nSaved: {args.output_dir}")


if __name__ == "__main__":
    main()

