# 탄소 측정 실행 요약

## 검증 범위

- 임베딩 파이프라인 실행
- 단일 질의 retrieval 샘플 확인
- 25문항 배치 평가(`test_queries.json`) 실행
- 탄소 로그 출력 형식 확인

## 단일 질의 샘플

- 질의: `i-PAC 콘테스트 신청 기간은 언제인가요?`
- 선택된 source: `documents`
- QA top1 점수: `0.7188`

| 단계 | 실행 시간 (s) | CO2 (g) | 최대 전력 (W) | 평균 전력 (W) |
|------|--------------:|--------:|---------------:|--------------:|
| `documents_embedding` | 16.8450 | 0.0511 | 30.19 | 22.36 |
| `qa_embedding` | 2.6760 | 0.0137 | 27.07 | 14.46 |
| `qa_pairs_retrieval` | 0.4225 | 0.0061 | 8.54 | 6.46 |
| `documents_retrieval` | 0.1497 | 0.0032 | 4.45 | 3.96 |

## 25문항 배치 평가

- Source 정확도: `24/25 (96.0%)`
- Document hit율: `20/21 (95.2%)`
- QA hit 횟수: `6`
- Document fallback 횟수: `19`
- 평균 top-1 유사도: `0.6898`
- 총 retrieval CO2: `0.3852 g`
- 질문당 평균 retrieval CO2: `0.0154 g`

| 단계 | 호출 수 | 총 실행 시간 (s) | 평균 실행 시간 (s) | 총 CO2 (g) | 평균 CO2 (g) |
|------|--------:|------------------:|-------------------:|------------:|-------------:|
| `qa_pairs_retrieval` | 25 | 55.5169 | 2.2207 | 0.2197 | 0.0088 |
| `documents_retrieval` | 19 | 41.7692 | 2.1984 | 0.1655 | 0.0087 |

## 비고

- `llm_generation`은 [query.py](C:\Users\gunhu\project\eco_cache_branch\query.py)에 이미 통합되어 있습니다.
- 다만 `run_eval.py`는 현재 retrieval만 평가하므로, 위 배치 평가에는 `llm_generation`이 포함되지 않았습니다.
- 이 브랜치에서는 retrieval threshold나 모델 값은 변경하지 않았습니다.
- [carbon_metrics_sample.json](C:\Users\gunhu\project\eco_cache_branch\examples\carbon_metrics_sample.json)은 실제 로그 구조 예시를 보여주기 위한 파일이라, 키 이름(`stage`, `duration_sec` 등)은 코드와 동일하게 유지했습니다.
