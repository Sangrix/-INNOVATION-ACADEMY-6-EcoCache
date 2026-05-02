# CO2 평가 결과 - 2026-05-02

## 목적

이 실행은 `feat/eval-pipeline` 브랜치를 로컬 GPU 환경에서 다시 측정하고, 콘솔 요약에서 CO2가 `0`으로 표시되던 문제를 수정하기 위해 진행했습니다.

평가 로직은 기존 브랜치 구현을 최대한 그대로 유지했습니다. 이 브랜치에서 수정한 코드 범위는 `run_eval.py`의 CO2 집계 경로뿐입니다.

## 실행 환경

- 기준 브랜치/커밋: `origin/feat/eval-pipeline` / `d3a1245`
- 로컬 GPU: NVIDIA GeForce RTX 3050 4GB Laptop GPU
- 임베딩 모델: `dragonkue/BGE-m3-ko`
- 벡터 DB: Qdrant 로컬 서버
- 테스트 세트: `test_queries.json` 50문항
- CO2 환산용 탄소 집약도: `430 gCO2/kWh`
- LLM 생성: 비활성화
- 결과 폴더: `snapshots/feat_eval_pipeline_original_20260502_190451`

## CO2 요약 오류 수정

`query.py`는 탄소 측정값을 `result["metrics"]`에 담아 반환합니다. 하지만 기존 `run_eval.py`는 `result["carbon_metrics"]`를 읽고 있었습니다.

이 키 이름 불일치 때문에 개별 JSONL 로그에는 CO2 값이 들어가 있었지만, 콘솔/배치 요약에서는 CO2가 `0`으로 표시될 수 있었습니다.

수정한 줄은 아래와 같습니다.

```python
carbon_metrics = result.get("metrics") or result.get("carbon_metrics", {})
```

## 결과 표

| 설정 | Source 정확도 | 캐시 히트율 | 평균 지연 | 총 CO2 | 질문당 CO2 | 임계값 |
|---|---:|---:|---:|---:|---:|---|
| B1 (캐시 없음) | 66.0% | 0.0% | 18,204 ms | 1.4236 g | 0.02847 g | 1.10 고정 |
| B2 (정적 캐시) | 68.0% | 2.0% | 16,617 ms | 1.0794 g | 0.02159 g | 0.90 고정 |
| CIASC alpha=0.25 | 72.0% | 6.0% | 20,516 ms | 1.0590 g | 0.02118 g | 0.80 -> 0.95 |
| CIASC alpha=0.50 | 72.0% | 6.0% | 16,280 ms | 1.0554 g | 0.02111 g | 0.80 -> 0.95 |
| CIASC alpha=1.00 | 78.0% | 12.0% | 15,827 ms | 1.0154 g | 0.02031 g | 0.76 -> 0.95 |

## 해석

이번 실행에서는 CIASC가 B2보다 낮은 CO2를 보였고, `alpha=1.00`에서 Source 정확도와 캐시 히트율이 가장 높게 나왔습니다.

다만 이 CIASC 수치는 최종 알고리즘 검증 결과라기보다는, 현재 브랜치 상태를 그대로 재현한 결과로 해석해야 합니다. 현재 브랜치에는 다음 두 가지 구현상 주의점이 있습니다.

- `carbon_optimizer.py` 내부에서 CLI로 전달한 alpha 값을 `alpha = 0.15`로 다시 덮어씁니다. 따라서 `--alpha 0.25`, `--alpha 0.5`, `--alpha 1.0`이 실제 임계값 계산식에 제대로 반영되지 않습니다.
- `base_theta = config.QA_SIMILARITY_THRESHOLD`가 직전 임계값을 다음 계산의 기준값으로 다시 사용합니다. 이 때문에 질문이 진행될수록 임계값이 누적 증가하여 `0.95`에 도달합니다.

이 두 가지 때문에 현재 threshold 변화는 순수한 "질문별 CI 적응형 계산"이라고 보기 어렵습니다. 팀에서 이 동작이 오류라고 확인하면, 다음 실행에서는 아래 항목을 수정해야 합니다.

- 하드코딩된 `alpha = 0.15` 제거
- `base_theta = 0.75`처럼 고정 기준 임계값 사용, 또는 논문 수식에 맞게 구현 정렬
- 질문 간 임계값 누적 방지

## 원본 결과 파일

원본 결과 파일은 아래 폴더에 포함되어 있습니다.

```text
snapshots/feat_eval_pipeline_original_20260502_190451/
```

주요 파일:

- `b1_console.txt`
- `b2_console.txt`
- `ciasc_alpha0.25_console.txt`
- `ciasc_alpha0.5_console.txt`
- `ciasc_alpha1.0_console.txt`
- `b1_eval_log.jsonl`
- `b2_eval_log.jsonl`
- `ciasc_alpha0.25_eval_log.jsonl`
- `ciasc_alpha0.5_eval_log.jsonl`
- `ciasc_alpha1.0_eval_log.jsonl`
- `carbon_metrics.jsonl`
