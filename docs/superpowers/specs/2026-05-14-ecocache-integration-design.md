# EcoCache 통합 설계 — feat/vector_embed + develop

**날짜:** 2026-05-14  
**범위:** 두 브랜치 기능 통합, 기능별 폴더 분리, Docker Compose 인프라

---

## 1. 목표

`feat/vector_embed` (RAG 파이프라인 + FastAPI)와 `origin/develop` (탄소 모니터링 + CIASC)를 하나의 코드베이스로 통합한다.

---

## 2. 디렉토리 구조

```
EcoCache/
├── rag/                        # RAG 파이프라인
│   ├── config.py               # 전체 설정 (QDRANT, 임베딩, CIASC, 탄소)
│   ├── embed_pipeline.py       # 임베딩 파이프라인 (carbon_monitor 통합)
│   ├── retriever_base.py       # BaseRetriever ABC + 싱글턴
│   ├── baseline_pure_rag.py    # B1: documents 전용
│   ├── baseline_semantic_cache.py  # B2: QA → docs fallback
│   ├── baseline_ciasc.py       # CIASC: CI 연동 동적 threshold
│   ├── query.py                # CLI + rag_search() + generate_answer()
│   ├── run_eval.py             # 배치 평가 (b1/b2/ciasc)
│   ├── eval_dashboard.py       # Streamlit 대시보드
│   └── requirements.txt
│
├── carbon/                     # 탄소 모니터링 (독립 모듈)
│   ├── carbon_monitor.py       # CarbonMonitor (codecarbon + pynvml)
│   ├── carbon_optimizer.py     # CarbonAdaptiveOptimizer (Electricity Maps API)
│   ├── collector.py            # PostgreSQL CI 수집 데몬 (15분 주기)
│   └── requirements.txt
│
├── api/                        # FastAPI 엔드포인트
│   ├── main.py                 # POST /chat (co2_grams 실제 측정)
│   ├── schemas.py              # ChatRequest / ChatResponse (cache_hit, co2_grams)
│   └── requirements.txt
│
├── infra/                      # 인프라
│   ├── docker-compose.yml      # Qdrant + PostgreSQL
│   └── schema.sql              # carbon_intensity_logs 테이블
│
├── data/                       # 입력 데이터
│   ├── sw_upstage_output/
│   ├── sw_upstage_output_2/
│   ├── sw_upstage_output_3/
│   └── pr_data/
│
├── docs/
├── test_queries.json
├── .env.example
└── README.md
```

---

## 3. 모듈 간 의존성

```
carbon/carbon_monitor.py   ← (config 불필요, from_config(cfg) 패턴)
carbon/carbon_optimizer.py ← rag/config.py (sys.path로 rag/ 추가)
carbon/collector.py        ← carbon/carbon_optimizer.py + env vars

rag/config.py              ← .env (dotenv)
rag/embed_pipeline.py      ← rag/config.py, carbon/carbon_monitor.py
rag/query.py               ← rag/config.py, carbon/carbon_monitor.py
rag/run_eval.py            ← rag/query.py, carbon/carbon_optimizer.py
rag/baseline_ciasc.py      ← rag/retriever_base.py, carbon/carbon_optimizer.py

api/main.py                ← rag/ (sys.path), carbon/carbon_monitor.py
```

`sys.path` 패턴: 각 모듈 상단에서 필요한 경로만 추가 (기존 `api/main.py` 방식 일관 적용).

---

## 4. 핵심 변경 사항

### 4-1. rag/config.py
- `DOC_PATHS`, `QA_PATHS`: `../data/` 기준으로 업데이트
- 탄소·CIASC 설정 유지 (develop 브랜치 그대로)
- `CARBON_LOG_PATH` 기본값: `rag/logs/carbon_metrics.jsonl`

### 4-2. carbon/ sys.path
`carbon_optimizer.py`, `collector.py`: 상단에 `rag/` sys.path 추가
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
import config
```

### 4-3. rag/baseline_ciasc.py (신규)
develop의 `run_eval.py`에 인라인으로 있던 CIASC 로직을 `BaseRetriever` 구현체로 분리.

### 4-4. api/main.py — co2_grams 실제 통합
- `CarbonMonitor.track()` context manager로 `/chat` 핸들러 래핑
- `ChatResult.co2_grams` 실측값 반환 (기존: 항상 null)
- `cache_hit` 필드: `result["source"] == "qa_pairs"` 그대로 유지

### 4-5. infra/docker-compose.yml
Qdrant + PostgreSQL을 단일 파일로 관리:
```yaml
services:
  qdrant:   image: qdrant/qdrant, port 6333, volume qdrant_data
  postgres: image: postgres:16, port 5432, volume postgres_data
            env: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
            healthcheck + init script (schema.sql)
```

---

## 5. API 응답 스키마

```json
{
  "success": true,
  "result": {
    "response": "LLM 생성 답변 (없으면 null)",
    "similarity": 0.8821,
    "cache_hit": true,
    "latency": 142.3,
    "co2_grams": 0.000012,
    "ci_g_per_kwh": 385.0,
    "sources": ["inha_notice_001"]
  }
}
```

---

## 6. .env.example

```
# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# PostgreSQL (collector)
POSTGRES_DB=ecocache
POSTGRES_USER=ecocache
POSTGRES_PASSWORD=ecocache
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Electricity Maps
ELECTRICITY_MAPS_API_KEY=
ELECTRICITY_MAPS_ZONE=KR

# Carbon Monitor
CARBON_MONITOR_ENABLED=true
CARBON_INTENSITY_G_PER_KWH=350.0
CARBON_GPU_INDEX=0
CARBON_SAMPLE_INTERVAL=0.1

# CIASC
CIASC_BASE_THRESHOLD=0.75
CIASC_CI_MIN=350
CIASC_CI_MAX=500
CIASC_THETA_MIN=0.70
CIASC_THETA_MAX=0.95
CIASC_FIXED_CI=

# LM Studio
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=
```
