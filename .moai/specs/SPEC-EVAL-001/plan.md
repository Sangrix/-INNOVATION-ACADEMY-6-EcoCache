# Plan: SPEC-EVAL-001 구현 계획

## 기술 스택

- Python 3.10+
- 기존 `rag/run_eval.py::run_eval()` 함수 재사용
- `rag/baseline_ciasc.py::CIASCRetriever` 직접 사용
- `rag/config.py` 런타임 패치 (CIASC_FIXED_CI)
- bash 4+ (스크립트)

## 파일 구조

```
rag/
└── grid_eval.py          ← [NEW] 그리드 스윕 + 리포트 생성

scripts/
└── run_grid_eval.sh      ← [NEW] 자동화 bash 스크립트

docs/
└── eval_reports/         ← [NEW] 리포트 출력 디렉토리 (자동 생성)
    └── YYYYMMDD_HHMMSS_grid_eval_report.md

rag/logs/
└── grid/                 ← [NEW] per-combination JSONL 로그
    └── alpha{A}_ci{CI}_eval.jsonl
```

## 구현 세부 계획

### 1. `rag/grid_eval.py`

#### 상수 정의

```python
ALPHA_BASE_SWEEP = [0.10, 0.15, 0.20, 0.25]
CI_SWEEP         = [350, 380, 420, 460, 500]
K_FIXED          = 0.5
```

#### CI 시뮬레이션 방식

`config.py`는 import 시 `CIASC_FIXED_CI`를 `os.getenv("CIASC_FIXED_CI")`로 로드한다.
이미 import된 후에는 `config.CIASC_FIXED_CI = float(ci)` 로 직접 패치하면 된다.

`carbon_optimizer.get_optimizer().get_current_ci()` 내부에서 `config.CIASC_FIXED_CI`를
확인하는 경우 패치가 즉시 반영된다. 그렇지 않을 경우를 위해 백업 방법으로
`CIASCRetriever._get_threshold()`를 부분 오버라이드하거나,
`carbon_optimizer` 모듈의 `FIXED_CI` 패치를 사용한다.

**안전한 구현 순서**:
1. `import config` 후 루프에서 `config.CIASC_FIXED_CI = float(ci)` 설정
2. `carbon_optimizer` 모듈도 필요시 패치 (`carbon_optimizer._OPTIMIZER = None` 리셋)
3. 각 반복에서 `CIASCRetriever(alpha=alpha_base, k=K_FIXED)` 인스턴스 생성
4. 직접 `retriever._get_threshold()` 호출로 계산된 alpha와 theta 검증

#### 핵심 루프 구조

```python
for alpha_base in ALPHA_BASE_SWEEP:
    for ci in CI_SWEEP:
        # 1. CI 시뮬레이션 세팅
        config.CIASC_FIXED_CI = float(ci)
        
        # 2. Retriever 생성
        retriever = CIASCRetriever(alpha=alpha_base, k=K_FIXED)
        
        # 3. alpha 계산값 확인 (검증용)
        alpha_computed = retriever._calculate_dynamic_alpha(float(ci))
        
        # 4. 25개 쿼리 실행
        combo_records = []
        for query_item in queries:
            t0 = time.perf_counter()
            result = retriever.retrieve(query_item["query"])
            latency_ms = (time.perf_counter() - t0) * 1000
            
            co2_g = sum(v.get("co2_g", 0.0) for v in 
                        result.get("metrics", {}).values() if isinstance(v, dict))
            
            combo_records.append({...})
            log_jsonl(record, log_path)
        
        # 5. 집계
        grid_result[alpha_base][ci] = aggregate(combo_records)
        print(f"[{n}/20] alpha={alpha_base:.2f} CI={ci} → ...")
```

#### 리포트 생성

`generate_report(grid_results, output_path)` 함수:
1. **실험 설정 표**: 파라미터 고정값/스윕 범위
2. **전체 결과 표**: `| alpha\\CI | 350 | 380 | 420 | 460 | 500 |` 형태의 히트율 표
3. **CO₂ 표**: 동일 구조로 CO₂(mg) 값
4. **ASCII 히트맵**: 히트율을 `█▓▒░ ` 5단계로 표현
5. **최적 조합 요약**: argmax(hit_rate), argmin(co2), 균형점(hit_rate/co2 비율)
6. **B1/B2 비교** (선택): `rag/logs/b1_eval_log.jsonl`이 있을 때만

#### ASCII 히트맵 예시

```
  캐시 히트율 히트맵 (α × CI)
         CI→  350   380   420   460   500
  α=0.10  │  ▒▒▒   ░░░   ░░░   ░░░   ░░░
  α=0.15  │  ▓▓▓   ▒▒▒   ▒▒▒   ░░░   ░░░
  α=0.20  │  ███   ▓▓▓   ▒▒▒   ▒▒▒   ░░░
  α=0.25  │  ███   ███   ▓▓▓   ▒▒▒   ▒▒▒
  (██=80%+  ▓▓=60-80%  ▒▒=40-60%  ░░=20-40%  공백=<20%)
```

#### CLI 인터페이스

```
python grid_eval.py [OPTIONS]

옵션:
  --alpha-list  콤마 구분 alpha 값 (기본: 0.10,0.15,0.20,0.25)
  --ci-list     콤마 구분 CI 값 (기본: 350,380,420,460,500)
  --test-file   쿼리 JSON 경로 (기본: ../test_queries.json)
  --output-dir  리포트 출력 디렉토리 (기본: ../docs/eval_reports)
  --log-dir     JSONL 로그 디렉토리 (기본: logs/grid)
  --no-report   리포트 생성 스킵 (JSONL만 저장)
```

### 2. `scripts/run_grid_eval.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Qdrant 연결 확인
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
curl -sf "${QDRANT_URL}/healthz" > /dev/null || { echo "[오류] Qdrant 연결 실패: ${QDRANT_URL}"; exit 1; }

# 2. Python 환경 활성화 (venv 자동 탐색)
if [ -f "rag/.venv/bin/activate" ]; then
  source rag/.venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

# 3. 실험 실행
cd rag
python grid_eval.py "$@"
```

## 의존성 체인

```
grid_eval.py
├── import config            (기존, 변경 없음)
├── import baseline_ciasc    (기존, 변경 없음)
│   └── CIASCRetriever
└── import run_eval          (기존, 변경 없음)
    └── rag_search, log_result (선택적)
```

## 리스크 및 완화

| 리스크 | 완화 방법 |
|--------|----------|
| carbon_optimizer가 config 패치를 반영 못 함 | `get_optimizer()` 싱글턴 초기화 우회 또는 `_get_threshold` 내부 분기 추가 |
| CO₂ 메트릭이 없음 (carbon 모듈 미설치) | `result.get("metrics", {})` 기본값 0.0으로 처리 |
| 500회 실행 중 Qdrant 타임아웃 | `retriever_base.search()`의 기존 예외 처리 활용, 실패 시 재시도 1회 |

## MX Tag 계획

`grid_eval.py`는 신규 파일이므로 주요 함수에:
- `generate_report()`: `# @MX:NOTE: ASCII heatmap uses 5-tier char encoding for hit-rate visualization`
- `run_grid_sweep()`: `# @MX:ANCHOR: main entry point; referenced by run_grid_eval.sh`

## 구현 순서

1. `rag/grid_eval.py` 작성 (핵심 루프 + 리포트 생성)
2. `scripts/run_grid_eval.sh` 작성
3. `docs/eval_reports/` 디렉토리 생성 (`.gitkeep`)
4. 간단한 dry-run 테스트 (1개 조합만 실행하여 검증)
