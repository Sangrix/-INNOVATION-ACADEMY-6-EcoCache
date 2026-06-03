#!/usr/bin/env python3.10
"""
EcoCache /chat API test report generator.

Usage:
    python3.10 tests/generate_report.py [--api-url http://localhost:8000]

Assumes the /chat API is already running.
Output: docs/reports/YYYY-MM-DD-chat-api-test-report.md
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

QA_FILES = [
    (DATA_DIR / "sw_upstage_output"   / "inha_notice_qa.json",                    "sw_upstage_output (공지사항 2026)"),
    (DATA_DIR / "sw_upstage_output_2" / "inha_sw_notice_qa_157275_to_166292.json", "sw_upstage_output_2 (공지사항 2025-11)"),
    (DATA_DIR / "sw_upstage_output_3" / "swuniv_notice_qa3.json",                  "sw_upstage_output_3 (공지사항 2025-12~2026)"),
    (DATA_DIR / "pr_data"             / "inha_pr_qa.json",                         "pr_data (외부홍보)"),
]

NOVEL_QUESTIONS = [
    "SW중심대학 사업단 소개 및 주요 목표는 무엇인가요?",
    "2026년 상반기에 진행되는 SW 관련 공모전 목록은?",
    "인하대 SW 전공 학생이 받을 수 있는 장학금 종류는 무엇인가요?",
    "SW중심대학 산학협력 프로그램에 참여하려면 어떻게 해야 하나요?",
    "오픈소스 프로젝트 참여 기회는 어떻게 찾을 수 있나요?",
    "인하대학교 SW중심대학 취업 연계 프로그램이 있나요?",
    "AI 관련 자격증 취득을 지원하는 프로그램에 대해 알려주세요.",
    "해외 인턴십이나 글로벌 프로그램을 지원하려면 무엇이 필요한가요?",
    "SW중심대학사업단이 주관하는 세미나나 특강 일정은 어디서 확인하나요?",
    "2025년 하반기 또는 2026년에 개최된 해커톤 정보가 있나요?",
]


def load_qa_batches(n_per_batch: int = 5) -> list[dict]:
    """Load n_per_batch QA pairs from each of the 4 data files."""
    results = []
    for qa_path, batch_name in QA_FILES:
        raw = json.loads(Path(qa_path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("qa_pairs", [])
        for item in items[:n_per_batch]:
            results.append({
                "query":           item["question"]["text"],
                "expected_answer": item["answer"]["text"],
                "batch":           batch_name,
                "type":            "qa_pair",
            })
    return results


def query_chat_api(query: str, api_url: str = "http://localhost:8000") -> dict:
    """POST query to /chat, return flat result dict with wall_time_ms included."""
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        f"{api_url}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            wall_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            data = json.loads(resp.read().decode())
    except Exception as exc:
        wall_time_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "query":        query,
            "success":      False,
            "error":        str(exc),
            "response":     None,
            "cache_hit":    None,
            "similarity":   None,
            "latency_ms":   None,
            "wall_time_ms": wall_time_ms,
            "co2_grams":    None,
            "ci_g_per_kwh": None,
            "sources":      [],
        }

    if not data.get("success") or data.get("result") is None:
        return {
            "query":        query,
            "success":      False,
            "error":        data.get("error", "unknown error"),
            "response":     None,
            "cache_hit":    None,
            "similarity":   None,
            "latency_ms":   None,
            "wall_time_ms": wall_time_ms,
            "co2_grams":    None,
            "ci_g_per_kwh": None,
            "sources":      [],
        }

    r = data["result"]
    return {
        "query":        query,
        "success":      True,
        "error":        None,
        "response":     r.get("response"),
        "cache_hit":    r.get("cache_hit", False),
        "similarity":   r.get("similarity"),
        "latency_ms":   r.get("latency"),
        "wall_time_ms": wall_time_ms,
        "co2_grams":    r.get("co2_grams"),
        "ci_g_per_kwh": r.get("ci_g_per_kwh"),
        "sources":      r.get("sources", []),
    }


def _fmt_float(val, decimals: int = 4) -> str:
    return f"{val:.{decimals}f}" if val is not None else "—"


def _fmt_co2(val) -> str:
    return f"{val * 1000:.4f} mg" if val is not None else "—"


def format_report(records: list[dict], generated_at: str) -> str:
    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        f"# EcoCache /chat API Test Report — {generated_at}",
        "",
        f"**Queries:** {len(records)} total  "
        f"({sum(1 for r in records if r['type'] == 'qa_pair')} QA pairs + "
        f"{sum(1 for r in records if r['type'] == 'novel')} novel)",
        "",
    ]

    # ── Summary table ─────────────────────────────────────────────────────────
    lines += [
        "## Summary",
        "",
        "| # | Query | Type | Cache Hit | Similarity | Latency (ms) | CO₂ |",
        "|---|-------|------|:---------:|:----------:|:------------:|-----|",
    ]
    for i, r in enumerate(records, 1):
        q_short = r["query"][:45] + "…" if len(r["query"]) > 45 else r["query"]
        hit = "✓" if r["cache_hit"] else "✗"
        sim = _fmt_float(r["similarity"])
        lat = f"{r['latency_ms']:.0f}" if r["latency_ms"] is not None else "—"
        co2 = _fmt_co2(r["co2_grams"])
        qtype = "QA" if r["type"] == "qa_pair" else "Novel"
        lines.append(f"| {i} | {q_short} | {qtype} | {hit} | {sim} | {lat} | {co2} |")
    lines.append("")

    # ── QA Pair Questions ─────────────────────────────────────────────────────
    lines += ["## QA Pair Questions", ""]
    qa_records = [r for r in records if r["type"] == "qa_pair"]
    current_batch = None
    qa_idx = 0
    for r in qa_records:
        qa_idx += 1
        if r["batch"] != current_batch:
            current_batch = r["batch"]
            lines += [f"### Batch — {current_batch}", ""]
        lines += [f"#### Q{qa_idx}: {r['query']}", ""]
        if not r["success"]:
            lines += [f"> **Error:** {r['error']}", ""]
        else:
            resp = r["response"] or "*(no LLM response)*"
            hit  = "✓" if r["cache_hit"] else "✗"
            lines += [
                f"**Answer:** {resp}",
                "",
                f"**Cache hit:** {hit}  |  "
                f"**Similarity:** {_fmt_float(r['similarity'])}  |  "
                f"**Latency:** {_fmt_float(r['latency_ms'], 0)} ms  |  "
                f"**Wall time:** {r['wall_time_ms']:.0f} ms",
                "",
                f"**CO₂:** {_fmt_co2(r['co2_grams'])}  |  "
                f"**CI:** {_fmt_float(r['ci_g_per_kwh'], 1)} gCO₂/kWh",
                "",
                f"**Sources:** {', '.join(f'`{s}`' for s in r['sources']) or '—'}",
                "",
            ]

    # ── Novel Questions ───────────────────────────────────────────────────────
    lines += ["## Novel Questions", ""]
    novel_records = [r for r in records if r["type"] == "novel"]
    for i, r in enumerate(novel_records, 1):
        lines += [f"#### N{i}: {r['query']}", ""]
        if not r["success"]:
            lines += [f"> **Error:** {r['error']}", ""]
        else:
            resp = r["response"] or "*(no LLM response)*"
            hit  = "✓" if r["cache_hit"] else "✗"
            lines += [
                f"**Answer:** {resp}",
                "",
                f"**Cache hit:** {hit}  |  "
                f"**Similarity:** {_fmt_float(r['similarity'])}  |  "
                f"**Latency:** {_fmt_float(r['latency_ms'], 0)} ms  |  "
                f"**Wall time:** {r['wall_time_ms']:.0f} ms",
                "",
                f"**CO₂:** {_fmt_co2(r['co2_grams'])}  |  "
                f"**CI:** {_fmt_float(r['ci_g_per_kwh'], 1)} gCO₂/kWh",
                "",
                f"**Sources:** {', '.join(f'`{s}`' for s in r['sources']) or '—'}",
                "",
            ]

    # ── Observations ──────────────────────────────────────────────────────────
    qa_hits    = sum(1 for r in qa_records    if r["cache_hit"])
    novel_hits = sum(1 for r in novel_records if r["cache_hit"])
    qa_sims    = [r["similarity"] for r in qa_records    if r["similarity"] is not None]
    novel_sims = [r["similarity"] for r in novel_records if r["similarity"] is not None]
    all_lats   = [r["latency_ms"] for r in records if r["latency_ms"] is not None]
    total_co2  = sum(r["co2_grams"] for r in records if r["co2_grams"] is not None)

    lines += ["## Observations", ""]
    if qa_records:
        lines.append(f"- **QA pair cache hit rate:** {qa_hits}/{len(qa_records)} ({qa_hits/len(qa_records)*100:.0f}%)")
    if novel_records:
        lines.append(f"- **Novel cache hit rate:** {novel_hits}/{len(novel_records)} ({novel_hits/len(novel_records)*100:.0f}%)")
    if qa_sims:
        lines.append(f"- **Avg similarity (QA):** {sum(qa_sims)/len(qa_sims):.4f}")
    if novel_sims:
        lines.append(f"- **Avg similarity (Novel):** {sum(novel_sims)/len(novel_sims):.4f}")
    if all_lats:
        lines.append(f"- **Avg latency:** {sum(all_lats)/len(all_lats):.0f} ms")
    lines.append(f"- **Total CO₂:** {_fmt_co2(total_co2)}")
    lines.append("")

    return "\n".join(lines)


def main(api_url: str = "http://localhost:8000") -> None:
    """Run full test suite and generate report."""
    # ── Load queries ──────────────────────────────────────────────────────────
    qa_items = load_qa_batches(n_per_batch=5)
    novel_items = [
        {"query": q, "expected_answer": None, "batch": None, "type": "novel"}
        for q in NOVEL_QUESTIONS
    ]
    all_items = qa_items + novel_items
    print(f"Loaded {len(all_items)} queries ({len(qa_items)} QA + {len(novel_items)} novel)")

    # ── Verify API is reachable ───────────────────────────────────────────────
    try:
        with urllib.request.urlopen(f"{api_url}/health", timeout=5) as r:
            health = json.loads(r.read().decode())
        if health.get("status") != "ok":
            print(f"[ERROR] API health check failed: {health}")
            sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Cannot reach API at {api_url}: {exc}")
        sys.exit(1)
    print(f"API reachable at {api_url} ✓")

    # ── Run queries ───────────────────────────────────────────────────────────
    records = []
    for i, item in enumerate(all_items, 1):
        label = f"[{i:02d}/{len(all_items)}] ({item['type']}) {item['query'][:60]}"
        print(label)
        result = query_chat_api(item["query"], api_url=api_url)
        result.update({
            "expected_answer": item.get("expected_answer"),
            "batch":           item.get("batch"),
            "type":            item["type"],
        })
        hit = "✓" if result["cache_hit"] else "✗"
        sim = f"{result['similarity']:.4f}" if result["similarity"] is not None else "—"
        lat = f"{result['wall_time_ms']:.0f}ms"
        print(f"  cache={hit}  sim={sim}  wall={lat}")
        records.append(result)

    # ── Write report ──────────────────────────────────────────────────────────
    now = datetime.now()
    report_dir = ROOT / "docs" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{now.strftime('%Y-%m-%d')}-chat-api-test-report.md"

    md = format_report(records, generated_at=now.strftime("%Y-%m-%d %H:%M"))
    report_path.write_text(md, encoding="utf-8")
    print(f"\nReport written → {report_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EcoCache /chat API test report generator")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    main(api_url=args.api_url)
