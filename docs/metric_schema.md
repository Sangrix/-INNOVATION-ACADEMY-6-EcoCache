# EcoCache 메트릭 로그 테이블 스키마

> 팀 합의 기준: 한 응답 = 한 row

---

## 테이블 정의

| 컬럼명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `query` | `TEXT` | 사용자 입력 질문 | `"TOPCIT 신청 기간이 언제인가요?"` |
| `cache_hit` | `BOOLEAN` | QA 캐시 히트 여부 (`qa_pairs` 반환 시 `true`) | `true` |
| `similarity` | `FLOAT` | 검색 top-1 유사도 점수 | `0.8731` |
| `latency_ms` | `FLOAT` | 응답 전체 소요 시간 (밀리초) | `1243.5` |
| `co2_g` | `FLOAT` | 해당 응답에서 발생한 탄소량 (그램) | `0.0088` |
| `ci` | `FLOAT` | 응답 시점의 탄소집약도 (gCO2/kWh) | `385.0` |
| `model` | `TEXT` | 사용된 임베딩 모델명 | `"dragonkue/BGE-m3-ko"` |
| `timestamp` | `DATETIME` | 응답 생성 시각 (ISO 8601) | `"2026-05-11T09:14:00"` |

---

## DDL (SQL)

```sql
CREATE TABLE metric_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT      NOT NULL,
    cache_hit   BOOLEAN   NOT NULL,
    similarity  FLOAT     NOT NULL,
    latency_ms  FLOAT     NOT NULL,
    co2_g       FLOAT     NOT NULL DEFAULT 0.0,
    ci          FLOAT     NOT NULL DEFAULT 0.0,
    model       TEXT      NOT NULL,
    timestamp   DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## JSONL 형식 (현재 run_eval.py 로그와 호환)

```json
{
  "query": "TOPCIT 신청 기간이 언제인가요?",
  "cache_hit": true,
  "similarity": 0.8731,
  "latency_ms": 1243.5,
  "co2_g": 0.0088,
  "ci": 385.0,
  "model": "dragonkue/BGE-m3-ko",
  "timestamp": "2026-05-11T09:14:00"
}
```

---

## 비고

- `cache_hit`: `run_eval.py`의 `result["source"] == "qa_pairs"` 값과 대응
- `similarity`: `result["results"][0]["score"]` 값과 대응
- `co2_g`: `carbon_metrics` 내 각 stage `co2_g` 합산값
- `ci`: `carbon_optimizer.py`의 `get_current_ci()` 반환값 (GPU 환경에서만 측정)
- `ci` 미측정 환경(GPU 없음)에서는 `0.0` 기록

