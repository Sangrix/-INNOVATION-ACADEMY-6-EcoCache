# SPEC-EVAL-001 Compact (Run Phase용)

## 요구사항 요약

**REQ-F-001**: alpha_base ∈ {0.10,0.15,0.20,0.25} × CI ∈ {350,380,420,460,500}, k=0.5 고정 → 20조합 × 25쿼리 = 500회 실행

**REQ-F-002**: 퀴리별 기록: `cache_hit`(bool), `qa_top1_score`, `top1_score`, `co2_g`, `latency_ms`

**REQ-F-003**: 조합별 집계: `cache_hit_rate`, `total_co2_mg`, `avg_top1_score`, `avg_latency_ms`, `alpha_computed`

**REQ-F-004**: 완료 후 `docs/eval_reports/YYYYMMDD_HHMMSS_grid_eval_report.md` 생성 — (1)설정표 (2)결과표 (3)CO₂표 (4)ASCII히트맵 (5)최적조합요약

**REQ-F-005**: per-combination JSONL 로그 → `rag/logs/grid/alpha{A}_ci{CI}_eval.jsonl`

**REQ-F-006**: `scripts/run_grid_eval.sh` — Qdrant 연결 확인 → venv 활성화 → `python rag/grid_eval.py` 실행

**REQ-C-001**: `--alpha-list` CLI → 기본 스윕 대체
**REQ-C-002**: `--ci-list` CLI → 기본 스윕 대체
**REQ-C-003**: `--output-dir` CLI → 리포트 경로 변경
**REQ-C-004**: B1/B2 로그 존재 시 비교 섹션 추가

**REQ-NF-001**: 조합별 진행 출력 `[N/20] alpha=X.XX CI=YYY → hit_rate=Z.Z% CO2=W.Wmg`
**REQ-NF-002**: JSONL에 `alpha_base`, `ci_simulated`, `k` 필드 포함
**REQ-NF-003**: bash 4+, Linux/macOS 호환

## 생성 파일

- `rag/grid_eval.py` [NEW]
- `scripts/run_grid_eval.sh` [NEW]
- `docs/eval_reports/.gitkeep` [NEW]

## 변경 금지

`run_eval.py`, `config.py`, `baseline_ciasc.py`, `test_queries.json` 변경 없음

## 인수 조건 체크리스트

- [ ] 기본 실행: 20조합 × 25쿼리 완료, JSONL 20개 + .md 1개 생성
- [ ] CI=425(중립)에서 `alpha_computed` == `alpha_base` (amplification 없음)
- [ ] `--alpha-list 0.10,0.20 --ci-list 350,500` → 4조합만 실행
- [ ] Qdrant 미응답 시 bash 스크립트 exit 1
- [ ] carbon 미설치 환경: ImportError 없이 co2_g=0.0으로 완료
- [ ] ruff check 통과
