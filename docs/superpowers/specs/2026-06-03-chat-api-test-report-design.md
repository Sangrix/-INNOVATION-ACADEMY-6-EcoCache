# EcoCache /chat API Test Report — Design Spec

## Goal

Run a representative set of queries against the live `/chat` API and produce a markdown report that shows retrieval accuracy, LLM response quality, latency, and carbon metrics across two query types: questions drawn from embedded QA pairs (expected cache hits) and novel questions not present in the QA pairs (expected document fallback).

## Query Set

**QA Pair Questions (20 total):** 5 sampled from each of the 4 data batches, chosen to span different topics within each batch. These should trigger cache hits (`source: qa_pairs`, similarity ≥ 0.75).

**Novel Questions (10 total):** Handcrafted Korean questions about the Inha SW department domain that are NOT literally in any QA pair. These test document retrieval (`source: documents`).

Novel question topics (designed to exercise the document corpus):
1. SW중심대학 사업단 소개 및 주요 목표는 무엇인가요?
2. 2026년 상반기에 진행되는 SW 관련 공모전 목록은?
3. 인하대 SW 전공 학생이 받을 수 있는 장학금 종류는 무엇인가요?
4. SW중심대학 산학협력 프로그램에 참여하려면 어떻게 해야 하나요?
5. 오픈소스 프로젝트 참여 기회는 어떻게 찾을 수 있나요?
6. 인하대학교 SW중심대학 취업 연계 프로그램이 있나요?
7. AI 관련 자격증 취득을 지원하는 프로그램에 대해 알려주세요.
8. 해외 인턴십이나 글로벌 프로그램을 지원하려면 무엇이 필요한가요?
9. SW중심대학사업단이 주관하는 세미나나 특강 일정은 어디서 확인하나요?
10. 2025년 하반기 또는 2026년에 개최된 해커톤 정보가 있나요?

## Script

**File:** `tests/generate_report.py`

Assumes the `/chat` API is already running at `http://localhost:8000`.

```
Usage: python3.10 tests/generate_report.py [--api-url URL]
Output: docs/reports/YYYY-MM-DD-chat-api-test-report.md
```

Logic:
1. Load all 4 QA pair JSON files from `data/`
2. Sample 5 QA pairs per batch (first 5 by index)
3. Append 10 hardcoded novel questions
4. For each query: POST to `/chat`, record full response + wall-clock time
5. Write markdown report

## Report Structure

```markdown
# EcoCache /chat API Test Report — YYYY-MM-DD HH:MM

## Summary

| # | Query | Type | Cache Hit | Similarity | Latency (ms) | CO₂ (mg) |
|---|-------|------|-----------|------------|--------------|----------|
| 1 | ...   | QA   | ✓         | 0.8821     | 342          | 0.021    |

## QA Pair Questions

### Batch 1 — sw_upstage_output (공지사항)
#### Q1: [question text]
**Answer:** [llm response or *(no LLM response)*]
**Cache hit:** ✓ | **Similarity:** 0.XXXX | **Latency:** XXXms
**CO₂:** X.XXXmg | **CI:** XXX gCO₂/kWh
**Sources:** `doc_id_1`, `doc_id_2`, ...

... (repeat per question)

## Novel Questions

#### Q21: [question text]
... (same structure)

## Observations

Auto-generated counts:
- QA cache hit rate: N/20
- Novel cache hit rate: N/10 (expected: 0)
- Average similarity (QA): X.XXXX
- Average similarity (novel): X.XXXX
- Average latency: XXXms
- Total CO₂: X.XXX mg
```

## Output Location

`docs/reports/YYYY-MM-DD-chat-api-test-report.md`

The `docs/reports/` directory will be created if it doesn't exist.

## Error Handling

- If the API returns `success: false`, record the error in place of the answer.
- If a field is missing (e.g., `co2_grams` is null), display `—`.
- If the API is unreachable, exit with a clear message.
