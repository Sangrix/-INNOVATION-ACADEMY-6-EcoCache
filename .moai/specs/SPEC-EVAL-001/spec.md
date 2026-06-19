---
id: SPEC-EVAL-001
version: 1.0.0
status: draft
created: 2026-06-20
updated: 2026-06-20
author: codie0226
priority: high
issue_number: 0
---

# SPEC-EVAL-001: CIASC 그리드 스윕 평가 파이프라인

## HISTORY

| Version | Date       | Author      | Change                             |
|---------|------------|-------------|-----------------------------------|
| 1.0.0   | 2026-06-20 | codie0226   | Initial draft (인터뷰 2 라운드)    |

---

## Overview

CIASC Retriever의 핵심 파라미터인 `alpha_base`와 탄소 집약도(Carbon Intensity, CI)를
그리드 스윕(4×5 = 20 조합)으로 순열 실험하여, 각 조합의 **캐시 히트율**·**CO₂**·**검색 정확도**를
측정하고 논문용 Markdown 리포트와 자동화 bash 스크립트를 생성한다.

**신규 파일 추가 (Greenfield)**

| 파일 | 유형 | 설명 |
|------|------|------|
| `rag/grid_eval.py` | [NEW] | 그리드 스윕 실험 + .md 리포트 생성 |
| `scripts/run_grid_eval.sh` | [NEW] | 전체 파이프라인 자동화 bash 스크립트 |

**읽기 전용 참조 (변경 없음)**

| 파일 | 참조 목적 |
|------|----------|
| `rag/run_eval.py` | `run_eval()` 함수 import |
| `rag/config.py` | CIASC 상수(CI_MIN, CI_MAX, THETA_*) |
| `rag/baseline_ciasc.py` | `CIASCRetriever` import |
| `test_queries.json` | 25개 평가 쿼리 (변경 없음) |

---

## 실험 설계

### 스윕 파라미터

| 파라미터 | 스윕 값 | 고정 값 |
|---------|--------|--------|
| `alpha_base` | {0.10, 0.15, 0.20, 0.25} | — |
| CI (g/kWh) | {350, 380, 420, 460, 500} | — |
| `k` | — | 0.5 |
| `theta_base` | — | 0.75 |
| `test_queries` | — | `test_queries.json` (25개) |

**총 실행 횟수**: 4 × 5 × 25 = **500 검색**

### CI 시뮬레이션 방식

`config.CIASC_FIXED_CI`를 각 그리드 포인트에서 Python 코드 내부에서 직접 덮어쓴다.
실제 Electricity Maps API 호출 없이 오프라인 실험이 가능하다.

```
config.CIASC_FIXED_CI = ci_value  # 각 그리드 반복 전 설정
retriever = CIASCRetriever(alpha=alpha_base)
```

---

## Requirements

### Functional Requirements

**REQ-F-001** (Event-Driven)
When `grid_eval.py` is invoked, the system shall iterate over all 20 (alpha_base, CI) combinations
in `ALPHA_BASE_SWEEP × CI_SWEEP` and execute all queries in `test_queries.json` for each combination.

**REQ-F-002** (Event-Driven)
When processing each grid combination, the system shall record the following per-query metrics:
- `cache_hit`: bool — `result["source"] == "qa_pairs"`
- `qa_top1_score`: float — `result["qa_top1_score"]`
- `top1_score`: float — top-ranked result score
- `co2_g`: float — sum of `co2_g` from `result["metrics"]`
- `latency_ms`: float — wall-clock duration of `retrieve()` call

**REQ-F-003** (Event-Driven)
When all queries for a (alpha_base, CI) combination complete, the system shall compute and store:
- `cache_hit_rate`: float — cache_hits / total_queries
- `total_co2_mg`: float — sum(co2_g) × 1000
- `avg_top1_score`: float
- `avg_latency_ms`: float
- `alpha_computed`: float — the dynamic alpha value computed for this CI

**REQ-F-004** (Event-Driven)
When all 20 grid combinations complete, the system shall generate a Markdown report at
`docs/eval_reports/YYYYMMDD_HHMMSS_grid_eval_report.md` containing:
1. 실험 설정 표 (고정 파라미터, 스윕 범위)
2. 전체 그리드 결과 표 (alpha × CI → 캐시 히트율, CO₂(mg), Top-1 유사도, 지연)
3. ASCII 캐시 히트율 히트맵 (alpha 행 × CI 열)
4. 최적 조합 요약 (히트율 최고, CO₂ 최소, 균형점)
5. B1/B2 베이스라인 대비 탄소 절감 비율 (기존 로그 파일이 있을 경우)

**REQ-F-005** (Event-Driven)
When `grid_eval.py` is invoked, the system shall write per-combination JSONL logs to
`rag/logs/grid/alpha{ALPHA}_ci{CI}_eval.jsonl` for reproducibility.

**REQ-F-006** (Event-Driven)
When `scripts/run_grid_eval.sh` is executed, the script shall:
1. Verify Qdrant is reachable at `http://localhost:6333` (또는 `QDRANT_URL` 환경변수)
2. Activate Python venv if `rag/.venv` or `.venv` exists
3. Execute `python rag/grid_eval.py` with configurable flags
4. Print the report path on completion

### Conditional Requirements

**REQ-C-001** (If-Then)
If `--alpha-list` CLI argument is provided to `grid_eval.py`, the system shall use the
user-supplied comma-separated list instead of the default `ALPHA_BASE_SWEEP`.

**REQ-C-002** (If-Then)
If `--ci-list` CLI argument is provided, the system shall use the user-supplied
comma-separated list instead of the default `CI_SWEEP`.

**REQ-C-003** (If-Then)
If `--output-dir` is provided, the system shall write the report to the specified directory
instead of `docs/eval_reports/`.

**REQ-C-004** (Optional)
Where B1/B2 baseline JSONL logs exist in `rag/logs/` (`b1_eval_log.jsonl`, `b2_eval_log.jsonl`),
the report shall include a baseline comparison section showing CO₂ reduction percentage.

### Non-Functional Requirements

**REQ-NF-001** (Performance)
The script shall print a progress line after each grid combination completes
(format: `[N/20] alpha=X.XX CI=YYY → hit_rate=Z.Z% CO2=W.Wmg`).

**REQ-NF-002** (Observability)
Each JSONL log entry shall include the grid parameters (`alpha_base`, `ci_simulated`, `k`)
alongside the standard eval log fields for full reproducibility.

**REQ-NF-003** (Portability)
`scripts/run_grid_eval.sh` shall work on Linux/macOS with bash 4+. No external dependencies
beyond the existing `rag/requirements.txt`.

---

## Exclusions (What NOT to Build)

- **Qdrant 재임베딩 없음**: 임베딩 파이프라인(`embed_pipeline.py`) 실행 및 수정 없음. 기존 벡터 DB 그대로 사용.
- **LM Studio 답변 생성 없음**: `--generate` 플래그 없이 검색 결과만 측정. LLM 추론 지연·탄소는 포함하지 않음.
- **k 값 스윕 없음**: k=0.5 고정. alpha와 CI 2차원만 스윕.
- **카테고리별 분리 분석 없음**: 전체 25개 쿼리를 하나의 풀로 취급. 카테고리별 히트율은 리포트에 미포함.
- **웹 대시보드 없음**: Streamlit/HTML 시각화 없음. 순수 텍스트 Markdown 리포트만 생성.
- **기존 파일 수정 없음**: `run_eval.py`, `config.py`, `baseline_ciasc.py` 등 기존 코드 변경 없음.

---

## Constraints

- Python 3.10+, 기존 `rag/requirements.txt` 의존성 추가 없음
- `grid_eval.py`는 `rag/` 디렉토리에서 실행 가능해야 함 (`python grid_eval.py`)
- CI 시뮬레이션은 `config.CIASC_FIXED_CI` 런타임 패치로 구현 (환경변수 아님)
- 리포트 출력 디렉토리 `docs/eval_reports/`는 없으면 자동 생성
- bash 스크립트는 실행 권한(`chmod +x`) 포함하여 생성
