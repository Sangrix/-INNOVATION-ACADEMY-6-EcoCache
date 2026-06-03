# Chat API Test Report Generator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tests/generate_report.py` — a script that fires 30 queries (20 sampled from QA pairs + 10 novel) at the live `/chat` API and writes a full markdown report to `docs/reports/`.

**Architecture:** Three pure functions (`load_qa_batches`, `query_chat_api`, `format_report`) wired by a `main()` entrypoint. Each function is independently testable with mocks. The script assumes the API is already running at `http://localhost:8000` and the 4 QA JSON files are at `data/`.

**Tech Stack:** Python 3.10 stdlib (`json`, `pathlib`, `datetime`, `time`, `urllib.request`) — no new deps. `pytest` + `unittest.mock` for tests.

---

## File Map

| File | Role |
|------|------|
| `tests/generate_report.py` | Main script: loads queries, hits API, writes report |
| `tests/test_generate_report.py` | Unit tests for the three core functions |
| `docs/reports/` | Output directory (created by script at runtime) |

---

### Task 1: load_qa_batches() + NOVEL_QUESTIONS

Loads 5 QA pairs from each of 4 data files (20 total). Returns a list of dicts with `query`, `expected_answer`, `batch`, and `type` fields. Also defines the 10 hardcoded novel questions.

**Files:**
- Create: `tests/generate_report.py`
- Create: `tests/test_generate_report.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_generate_report.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch, mock_open
import json


MOCK_QA = [
    {
        "qa_id": f"qa_{i:03d}",
        "source_doc_id": f"doc_{i:03d}",
        "question": {"text": f"질문 {i}"},
        "answer": {"text": f"답변 {i}", "reference_url": "https://example.com"},
    }
    for i in range(10)
]


def test_load_qa_batches_returns_20_items():
    import generate_report
    mock_data = json.dumps(MOCK_QA)
    with patch("builtins.open", mock_open(read_data=mock_data)):
        with patch("generate_report.Path.exists", return_value=True):
            batches = generate_report.load_qa_batches()
    assert len(batches) == 20


def test_load_qa_batches_each_item_has_required_fields():
    import generate_report
    mock_data = json.dumps(MOCK_QA)
    with patch("builtins.open", mock_open(read_data=mock_data)):
        with patch("generate_report.Path.exists", return_value=True):
            batches = generate_report.load_qa_batches()
    for item in batches:
        assert "query" in item
        assert "expected_answer" in item
        assert "batch" in item
        assert item["type"] == "qa_pair"


def test_novel_questions_count():
    import generate_report
    assert len(generate_report.NOVEL_QUESTIONS) == 10


def test_novel_questions_are_strings():
    import generate_report
    for q in generate_report.NOVEL_QUESTIONS:
        assert isinstance(q, str)
        assert len(q) > 5
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'generate_report'`

- [ ] **Step 3: Create tests/generate_report.py with load_qa_batches and NOVEL_QUESTIONS**

```python
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
    (DATA_DIR / "sw_upstage_output"  / "inha_notice_qa.json",                    "sw_upstage_output (공지사항 2026)"),
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
```

- [ ] **Step 4: Run tests**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py -v 2>&1 | tail -15
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/generate_report.py tests/test_generate_report.py
git commit -m "feat: add generate_report scaffold with load_qa_batches and NOVEL_QUESTIONS"
```

---

### Task 2: query_chat_api()

Sends one query to the `/chat` endpoint and returns a flat result dict.

**Files:**
- Modify: `tests/generate_report.py` (add `query_chat_api`)
- Modify: `tests/test_generate_report.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate_report.py`:

```python
from unittest.mock import MagicMock
import urllib.request

API_RESPONSE = {
    "success": True,
    "error": None,
    "result": {
        "response": "테스트 답변입니다.",
        "similarity": 0.8821,
        "cache_hit": True,
        "latency": 342.1,
        "co2_grams": 0.000021,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_001", "inha_notice_002"],
        "timings": [],
    },
}


def _make_mock_urlopen(response_dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_dict).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_query_chat_api_returns_flat_dict():
    import generate_report
    mock_resp = _make_mock_urlopen(API_RESPONSE)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = generate_report.query_chat_api("테스트 질문", api_url="http://localhost:8000")
    assert result["query"] == "테스트 질문"
    assert result["response"] == "테스트 답변입니다."
    assert result["cache_hit"] is True
    assert result["similarity"] == 0.8821
    assert result["latency_ms"] == 342.1
    assert result["co2_grams"] == 0.000021
    assert result["ci_g_per_kwh"] == 395.5
    assert result["sources"] == ["inha_notice_001", "inha_notice_002"]
    assert "wall_time_ms" in result


def test_query_chat_api_handles_api_error():
    import generate_report
    error_response = {"success": False, "error": "Retriever not initialized", "result": None}
    mock_resp = _make_mock_urlopen(error_response)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = generate_report.query_chat_api("질문", api_url="http://localhost:8000")
    assert result["success"] is False
    assert result["error"] == "Retriever not initialized"
    assert result["response"] is None


def test_query_chat_api_handles_connection_error():
    import generate_report
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        result = generate_report.query_chat_api("질문", api_url="http://localhost:8000")
    assert result["success"] is False
    assert "refused" in result["error"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py::test_query_chat_api_returns_flat_dict -v
```

Expected: `AttributeError: module 'generate_report' has no attribute 'query_chat_api'`

- [ ] **Step 3: Add query_chat_api() to tests/generate_report.py**

Append after `load_qa_batches`:

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py -v 2>&1 | tail -15
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/generate_report.py tests/test_generate_report.py
git commit -m "feat: add query_chat_api with error handling"
```

---

### Task 3: format_report()

Takes the full list of query results and formats them into a markdown string.

**Files:**
- Modify: `tests/generate_report.py` (add `format_report`)
- Modify: `tests/test_generate_report.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate_report.py`:

```python
SAMPLE_RECORDS = [
    {
        "query": "신청 기간은 언제인가요?",
        "expected_answer": "4월 1일~28일",
        "batch": "sw_upstage_output (공지사항 2026)",
        "type": "qa_pair",
        "success": True,
        "error": None,
        "response": "신청 기간은 4월 1일부터 28일까지입니다.",
        "cache_hit": True,
        "similarity": 0.8821,
        "latency_ms": 342.1,
        "wall_time_ms": 355.0,
        "co2_grams": 0.000021,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_001"],
    },
    {
        "query": "SW중심대학 사업단 소개 및 주요 목표는 무엇인가요?",
        "expected_answer": None,
        "batch": None,
        "type": "novel",
        "success": True,
        "error": None,
        "response": "인하대학교 SW중심대학 사업단은...",
        "cache_hit": False,
        "similarity": 0.6123,
        "latency_ms": 5200.0,
        "wall_time_ms": 5215.0,
        "co2_grams": 0.000089,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_012", "inha_pr_001"],
    },
]


def test_format_report_contains_summary_table():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Summary" in md
    assert "Cache Hit" in md
    assert "Similarity" in md
    assert "Latency" in md
    assert "CO₂" in md


def test_format_report_contains_qa_section():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## QA Pair Questions" in md
    assert "신청 기간은 언제인가요?" in md
    assert "4월 1일부터 28일까지" in md


def test_format_report_contains_novel_section():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Novel Questions" in md
    assert "SW중심대학 사업단 소개" in md


def test_format_report_contains_observations():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Observations" in md
    assert "cache hit" in md.lower() or "Cache Hit" in md


def test_format_report_cache_hit_symbol():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "✓" in md   # cache hit symbol
    assert "✗" in md   # cache miss symbol
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py -k "format_report" -v
```

Expected: `AttributeError: module 'generate_report' has no attribute 'format_report'`

- [ ] **Step 3: Add format_report() to tests/generate_report.py**

Append after `query_chat_api`:

```python
def _fmt_float(val: float | None, decimals: int = 4) -> str:
    return f"{val:.{decimals}f}" if val is not None else "—"


def _fmt_co2(val: float | None) -> str:
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
        lines += [
            f"#### Q{qa_idx}: {r['query']}",
            "",
        ]
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
                f"**Latency:** {r['latency_ms']:.0f} ms  |  "
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
                f"**Latency:** {r['latency_ms']:.0f} ms  |  "
                f"**Wall time:** {r['wall_time_ms']:.0f} ms",
                "",
                f"**CO₂:** {_fmt_co2(r['co2_grams'])}  |  "
                f"**CI:** {_fmt_float(r['ci_g_per_kwh'], 1)} gCO₂/kWh",
                "",
                f"**Sources:** {', '.join(f'`{s}`' for s in r['sources']) or '—'}",
                "",
            ]

    # ── Observations ──────────────────────────────────────────────────────────
    qa_hits     = sum(1 for r in qa_records   if r["cache_hit"])
    novel_hits  = sum(1 for r in novel_records if r["cache_hit"])
    qa_sims     = [r["similarity"] for r in qa_records   if r["similarity"] is not None]
    novel_sims  = [r["similarity"] for r in novel_records if r["similarity"] is not None]
    all_lats    = [r["latency_ms"] for r in records if r["latency_ms"] is not None]
    total_co2   = sum(r["co2_grams"] for r in records if r["co2_grams"] is not None)

    lines += [
        "## Observations",
        "",
        f"- **QA pair cache hit rate:** {qa_hits}/{len(qa_records)} "
        f"({qa_hits/len(qa_records)*100:.0f}%)" if qa_records else "- **QA pair cache hit rate:** —",
        f"- **Novel cache hit rate:** {novel_hits}/{len(novel_records)} "
        f"({novel_hits/len(novel_records)*100:.0f}%)" if novel_records else "- **Novel cache hit rate:** —",
        f"- **Avg similarity (QA):** {sum(qa_sims)/len(qa_sims):.4f}" if qa_sims else "- **Avg similarity (QA):** —",
        f"- **Avg similarity (Novel):** {sum(novel_sims)/len(novel_sims):.4f}" if novel_sims else "- **Avg similarity (Novel):** —",
        f"- **Avg latency:** {sum(all_lats)/len(all_lats):.0f} ms" if all_lats else "- **Avg latency:** —",
        f"- **Total CO₂:** {_fmt_co2(total_co2)}",
        "",
    ]

    return "\n".join(lines)
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -m pytest tests/test_generate_report.py -v 2>&1 | tail -20
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/generate_report.py tests/test_generate_report.py
git commit -m "feat: add format_report with summary table, QA/novel sections, observations"
```

---

### Task 4: main() entrypoint

Wires load → query → format → write. Handles `--api-url` CLI arg and creates `docs/reports/`.

**Files:**
- Modify: `tests/generate_report.py` (add `main` and `if __name__ == "__main__"` block)

- [ ] **Step 1: Append main() to tests/generate_report.py**

```python
def main(api_url: str = "http://localhost:8000") -> None:
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
```

- [ ] **Step 2: Verify no import errors**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 -c "import sys; sys.path.insert(0,'tests'); import generate_report; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run all tests still pass**

```bash
python3.10 -m pytest tests/test_generate_report.py -v 2>&1 | tail -15
```

Expected: all 12 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/generate_report.py
git commit -m "feat: add main() entrypoint with health check, progress output, report write"
```

---

### Task 5: Live run + commit report

Start the API, run the script, commit the generated report.

**Files:**
- Create: `docs/reports/2026-06-03-chat-api-test-report.md` (generated at runtime)

- [ ] **Step 1: Start the API server**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache/api
python3.10 -m uvicorn main:app --port 8000 --log-level warning &
sleep 4
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Run the report generator**

```bash
cd /home/chs/dev/INNOVATION-ACADEMY-6-EcoCache
python3.10 tests/generate_report.py --api-url http://localhost:8000
```

Expected output ends with:
```
Report written → docs/reports/2026-06-03-chat-api-test-report.md
```

Watch the progress lines — QA pair questions should show `cache=✓` (most of them), novel questions should show `cache=✗`.

- [ ] **Step 3: Sanity-check the report**

```bash
head -60 docs/reports/2026-06-03-chat-api-test-report.md
```

Verify the summary table has 30 rows, the QA section has 4 batches, and the novel section has 10 entries.

- [ ] **Step 4: Stop the server**

```bash
pkill -f "uvicorn main:app" 2>/dev/null || true
```

- [ ] **Step 5: Commit the script + report**

```bash
git add tests/generate_report.py docs/reports/
git commit -m "feat: add report generator + 2026-06-03 chat API test report"
```
