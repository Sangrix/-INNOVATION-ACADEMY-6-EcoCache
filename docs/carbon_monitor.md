# 탄소 측정 모듈 통합 문서

## 목적

이 문서는 기존 EcoCache 파이프라인에 탄소 배출량과 전력 사용량 측정을
어떻게 붙였는지 설명합니다.

이번 통합의 목표는 다음과 같습니다.

- retrieval threshold는 바꾸지 않기
- 모델 선택이나 프롬프트 로직은 건드리지 않기
- 기존 파이프라인 단계만 감싸서 측정값을 남기기

즉, 파이프라인 동작을 바꾸는 것이 아니라 **측정 레이어를 얹는 것**이 핵심입니다.

## 관련 파일

- `carbon_monitor.py`
- `config.py`
- `embed_pipeline.py`
- `query.py`
- `requirements.txt`

## 무엇을 측정하나

측정 대상 함수는 실행 결과와 함께 metrics 딕셔너리를 반환합니다.

metrics에는 아래 값이 들어갑니다.

- `stage`: 어떤 단계인지 식별하는 이름
- `duration_sec`: 실행 시간(초)
- `energy_kwh`: 사용 에너지(kWh)
- `co2_g`: 추정 CO2 배출량(g)
- `peak_power_W`: 실행 중 최대 전력(W)
- `avg_power_W`: 실행 중 평균 전력(W)
- `extra`: 컬렉션명, top_k 같은 보조 정보

## 통합 지점

### 임베딩 파이프라인

`embed_pipeline.py`에서 아래 단계를 감쌉니다.

- `documents_embedding`
- `qa_embedding`

### 질의 파이프라인

`query.py`에서 아래 단계를 감쌉니다.

- `qa_pairs_retrieval`
- `documents_retrieval`
- `llm_generation`

| 단계 | 실행 조건 |
|------|-----------|
| `documents_embedding` | `python embed_pipeline.py` 실행 시 문서 청크를 업서트할 때 측정 |
| `qa_embedding` | `python embed_pipeline.py` 실행 시 QA 청크를 업서트할 때 측정 |
| `qa_pairs_retrieval` | `rag_search()`가 호출될 때마다 측정 |
| `documents_retrieval` | `qa_top1_score < 0.75`일 때만 추가 측정 |
| `llm_generation` | `python query.py "..." --generate`로 생성까지 실행할 때만 측정 |

## 사용 방식

가장 기본적인 사용 패턴은 아래와 같습니다.

```python
from carbon_monitor import CarbonMonitor

carbon_monitor = CarbonMonitor.from_config(config)

result, metrics = carbon_monitor.run(
    "documents_embedding",
    some_existing_function,
    *args,
    **kwargs,
)
```

즉, 기존 함수를 `carbon_monitor.run()`으로 감싸기만 하면
실행 결과와 측정 결과를 같이 받을 수 있습니다.

## 설정값

환경변수는 아래와 같습니다.

```dotenv
CARBON_MONITOR_ENABLED=true
CARBON_INTENSITY_G_PER_KWH=350.0
CARBON_GPU_INDEX=0
CARBON_SAMPLE_INTERVAL=0.1
CARBON_LOG_PATH=carbon_metrics.jsonl
```

각 값의 의미:

- `CARBON_MONITOR_ENABLED`: 측정 기능 사용 여부
- `CARBON_INTENSITY_G_PER_KWH`: kWh당 CO2 환산값
- `CARBON_GPU_INDEX`: 측정 대상 GPU 인덱스
- `CARBON_SAMPLE_INTERVAL`: 전력 샘플링 주기(초)
- `CARBON_LOG_PATH`: JSONL 로그 저장 경로

## 출력 형식

측정 결과는 JSON Lines 형식으로 한 줄씩 저장됩니다.

예시:

```json
{
  "stage": "documents_embedding",
  "duration_sec": 16.845,
  "energy_kwh": 0.00014592237952754716,
  "co2_g": 0.0511,
  "peak_power_W": 30.19,
  "avg_power_W": 22.36,
  "extra": {
    "collection": "documents",
    "chunk_count": 189
  }
}
```

## 배치 평가 메모

25개 테스트 질문 세트를 이 브랜치에서 실행했고, retrieval 로그는 아래 파일에 저장했습니다.

- `examples/test_set_eval_log.jsonl`

요약:

- Source 정확도: `24/25 (96.0%)`
- Document hit율: `20/21 (95.2%)`
- QA hit 횟수: `6`
- Document fallback 횟수: `19`
- 평균 top-1 유사도: `0.6898`
- 배치 전체 retrieval CO2: `0.3852 g`

단계별 retrieval 총합:

| 단계 | 호출 수 | 총 실행 시간 (s) | 총 CO2 (g) |
|------|--------:|------------------:|------------:|
| `qa_pairs_retrieval` | 25 | 55.5169 | 0.2197 |
| `documents_retrieval` | 19 | 41.7692 | 0.1655 |

`llm_generation`은 [query.py](C:\Users\gunhu\project\eco_cache_branch\query.py)에
통합되어 있지만, `run_eval.py`는 현재 retrieval만 평가하므로 배치 실행에서는
LLM 생성 단계가 기록되지 않았습니다.

## 참고 사항

- 이 브랜치는 탄소 측정 모듈을 붙이는 데 초점을 둡니다.
- retrieval threshold나 검색 로직은 조정하지 않습니다.
- RAG 파이프라인의 기본 설계는 유지합니다.
