# Acceptance Criteria: SPEC-EVAL-001

## 시나리오 1: 기본 그리드 스윕 실행

**Given** Qdrant가 `http://localhost:6333`에서 실행 중이고 `documents`/`qa_pairs` 컬렉션이 임베딩되어 있을 때
**When** `cd rag && python grid_eval.py` 를 실행하면
**Then**
- 총 20개 조합 × 25개 쿼리 = 500회 검색이 완료된다
- `logs/grid/alpha0.10_ci350_eval.jsonl` ~ `alpha0.25_ci500_eval.jsonl` 형식의 JSONL 파일 20개가 생성된다
- `docs/eval_reports/YYYYMMDD_HHMMSS_grid_eval_report.md` 파일이 생성된다
- 리포트에 "전체 그리드 결과" 표, "CO₂ 집계" 표, "ASCII 히트맵", "최적 조합 요약" 섹션이 모두 존재한다
- 진행 상황이 `[N/20] alpha=X.XX CI=YYY → hit_rate=Z.Z% CO2=W.Wmg` 형식으로 출력된다

## 시나리오 2: CI 시뮬레이션 정확성

**Given** `config.CIASC_FIXED_CI`가 코드 내부에서 런타임 패치되는 환경에서
**When** CI=350과 CI=500 두 극단값을 각각 실행하면
**Then**
- CI=350(저탄소)에서 계산된 `alpha_computed` 값이 CI=500(고탄소)보다 다른 값이어야 한다
  (공식: α(CI) = α_base × (1 + k × |CI_norm − 0.5|) 에 따라)
- CI=350, alpha_base=0.15, k=0.5 → `alpha_computed` ≈ 0.15 × (1 + 0.5 × 0.5) = 0.1875
- CI=500, alpha_base=0.15, k=0.5 → `alpha_computed` ≈ 0.15 × (1 + 0.5 × 0.5) = 0.1875
- CI=425(중립), alpha_base=0.15 → `alpha_computed` == 0.15 (증폭 없음)

## 시나리오 3: CLI 파라미터 오버라이드

**Given** `grid_eval.py`가 CLI 인수를 지원할 때
**When** `python grid_eval.py --alpha-list 0.10,0.20 --ci-list 350,500` 을 실행하면
**Then**
- 2 × 2 = 4개 조합만 실행된다
- 출력에 `[4/4]`가 마지막 진행 줄로 표시된다
- 지정하지 않은 alpha(0.15, 0.25)와 CI(380, 420, 460) 조합은 실행되지 않는다

## 시나리오 4: bash 스크립트 실행

**Given** 프로젝트 루트 디렉토리에서
**When** `bash scripts/run_grid_eval.sh` 를 실행하면
**Then**
- Qdrant 연결 성공 시 `grid_eval.py` 자동 실행
- Qdrant 미응답 시 `[오류] Qdrant 연결 실패: http://localhost:6333` 출력 후 exit 1
- 완료 시 생성된 리포트 파일 경로를 출력한다

## 시나리오 5: CO₂ 기록 정확성

**Given** carbon 모니터링이 활성화된 환경에서 실험이 완료되면
**When** JSONL 로그 파일을 열면
**Then**
- 각 항목에 `alpha_base`, `ci_simulated`, `k`, `co2_g`, `cache_hit`, `top1_score`, `latency_ms` 필드가 존재한다
- `co2_g` 값이 0.0 이상이다 (carbon 모듈 비활성 시 0.0 허용)

## 시나리오 6: carbon 모듈 없는 환경 (fallback)

**Given** `carbon_optimizer` 모듈이 설치되지 않은 환경에서
**When** `python grid_eval.py` 를 실행하면
**Then**
- ImportError 없이 실행이 완료된다
- `co2_g` 값은 모두 `0.0`으로 기록되고 리포트에 "carbon 미측정" 주석이 표시된다

## 품질 게이트

- [ ] `ruff check rag/grid_eval.py` 통과 (린트 오류 없음)
- [ ] `scripts/run_grid_eval.sh` bash 문법 오류 없음 (`bash -n scripts/run_grid_eval.sh`)
- [ ] 시나리오 3 (CLI 오버라이드) 4개 조합 실행 시 약 60초 이내 완료 (Qdrant 로컬 기준)
- [ ] 생성된 리포트 `.md` 파일이 GitHub Markdown으로 올바르게 렌더링 됨
