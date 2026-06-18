# EcoCache

인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 지식 베이스로 활용하는
**RAG 기반 학생 Q&A 챗봇** + **탄소 발자국 측정** 통합 시스템.

## 핵심 기능

| 기능 | 설명 |
|------|------|
| **RAG 파이프라인** | BGE-m3-ko 임베딩 → Qdrant 벡터 검색 |
| **Semantic Cache** | QA 페어 캐시로 반복 질문 응답 가속 |
| **CIASC** | 탄소 집약도(CI) 연동 동적 캐시 임계값 조절 |
| **탄소 모니터링** | 쿼리·임베딩·LLM 단계별 CO2 실측 (codecarbon) |
| **FastAPI** | `/chat` 엔드포인트 — `cache_hit`, `co2_grams` 반환 |
| **CI 수집** | Electricity Maps API → PostgreSQL 15분 주기 수집 |

---

## 디렉토리 구조

```
EcoCache/
├── rag/                        # RAG 파이프라인
│   ├── config.py               # 전체 설정
│   ├── embed_pipeline.py       # 임베딩 파이프라인
│   ├── retriever_base.py       # BaseRetriever 인터페이스
│   ├── baseline_pure_rag.py    # B1: documents 전용
│   ├── baseline_semantic_cache.py  # B2: QA 캐시 → docs fallback
│   ├── baseline_ciasc.py       # CIASC: CI 연동 동적 threshold
│   ├── query.py                # CLI 진입점
│   ├── run_eval.py             # 배치 평가 (b1/b2/ciasc)
│   ├── eval_dashboard.py       # Streamlit 대시보드
│   └── requirements.txt
│
├── carbon/                     # 탄소 모니터링 (독립 모듈)
│   ├── carbon_monitor.py       # CarbonMonitor (codecarbon + pynvml)
│   ├── carbon_optimizer.py     # CarbonAdaptiveOptimizer (Electricity Maps)
│   ├── collector.py            # PostgreSQL CI 수집 데몬
│   └── requirements.txt
│
├── api/                        # FastAPI 엔드포인트
│   ├── main.py                 # POST /chat, GET /health
│   ├── schemas.py              # 요청/응답 스키마
│   └── requirements.txt
│
├── infra/                      # 인프라
│   ├── docker-compose.yml      # Qdrant + PostgreSQL
│   └── schema.sql              # carbon_intensity_logs 테이블
│
├── data/                       # 입력 데이터
│   ├── sw_upstage_output/      # 2026년 최신 공지
│   ├── sw_upstage_output_2/    # 2025년 11월 공지
│   ├── sw_upstage_output_3/    # 2025년 12월~2026년 초
│   └── pr_data/                # 외부홍보 게시물
│
├── test_queries.json           # 25개 평가 질문 세트
└── .env.example                # 환경변수 템플릿
```

---

## 빠른 시작

### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일에서 필요한 값 설정
```

### 2. 인프라 기동 (Qdrant + PostgreSQL)

```bash
cd infra
docker compose up -d
cd ..
```

### 3. 패키지 설치

```bash
pip install -r rag/requirements.txt
pip install -r carbon/requirements.txt
pip install -r api/requirements.txt
```

### 4. 임베딩 파이프라인 실행 (최초 1회)

```bash
cd rag
python embed_pipeline.py
```

### 5. 검색 쿼리

```bash
cd rag

# B1: Pure RAG (캐시 없음)
python query.py "i-PAC 콘테스트 신청 기간" --mode b1

# B2: Semantic Cache (정적 임계값)
python query.py "장학금 신청 방법" --mode b2

# CIASC: CI 연동 동적 임계값
python query.py "현장실습 신청 기간" --mode ciasc

# LLM 답변 생성 (LM Studio 필요)
python query.py "장학금 신청 방법" --generate

# 로그 기록
python query.py "질문" --log --log-file logs/my.jsonl
```

### 6. 배치 평가

```bash
cd rag

python run_eval.py --mode b1
python run_eval.py --mode b2
python run_eval.py --mode ciasc --alpha 0.25
python run_eval.py --compare          # b1/b2/ciasc 비교 표
python run_eval.py --summary-only --log-file logs/b2_eval_log.jsonl
```

### 7. Streamlit 대시보드

```bash
cd rag
streamlit run eval_dashboard.py
```

### 8. FastAPI 서버

```bash
cd api
uvicorn main:app --reload --port 8000
```

API 호출 예시:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "장학금 신청 기간이 언제인가요?"}'
```

응답 예시:
```json
{
  "success": true,
  "result": {
    "response": "장학금 신청은 ...",
    "similarity": 0.8821,
    "cache_hit": true,
    "latency": 142.3,
    "co2_grams": 0.000012,
    "ci_g_per_kwh": 420.0,
    "alpha_used": 0.1525,
    "sources": ["inha_notice_001"]
  }
}
```

`alpha_used`: CIASC 모드에서 실제 사용된 동적 α 값. B1/B2 모드에서는 `null`.

### 9. CI 수집 데몬 (선택)

```bash
# PostgreSQL이 실행 중인 상태에서
cd carbon
python collector.py
```

---

## 평가 모드 비교

| 모드 | 설명 | 캐시 임계값 |
|------|------|------------|
| `b1` | Pure RAG — 캐시 없음 | 1.1 (사실상 비활성) |
| `b2` | Semantic Cache — 정적 | θ = 0.90 고정 |
| `ciasc` | CI-Adaptive — 동적 | θ(t) = f(현재 탄소 집약도) |

**CIASC 동작 원리:**
- CI가 높을수록(탄소 배출 多) → θ 낮아짐 → 캐시 히트 쉬워짐 (전력 절감)
- CI가 낮을수록 → θ 높아짐 → 더 정확한 문서 검색
- **동적 α**: `α(CI) = α_base × (1 + k × |CI_norm − 0.5|)` — CI 극단값일수록 α 민감도 증폭

---

## 환경변수 주요 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 주소 |
| `POSTGRES_*` | `ecocache` | PostgreSQL 연결 정보 |
| `ELECTRICITY_MAPS_API_KEY` | (없음) | 실시간 CI 조회 (없으면 정적 프록시) |
| `CARBON_MONITOR_ENABLED` | `true` | 탄소 측정 활성화 |
| `CIASC_FIXED_CI` | (없음) | CI 고정값 (테스트용) |
| `CIASC_ALPHA_K` | `0.5` | 동적 α 증폭 계수 (k=0이면 고정 α) |
| `LM_STUDIO_MODEL` | (없음) | LLM 모델명 (`--generate` 필요) |

---

## 데이터 배치 구조

| 폴더 | 기간/범위 | doc_id 패턴 |
|------|----------|-------------|
| `data/sw_upstage_output/` | 2026년 최신 공지 | `inha_notice_001~` |
| `data/sw_upstage_output_2/` | 2025년 11월 공지 | `inha_sw_notice_NNNNNN` |
| `data/sw_upstage_output_3/` | 2025년 12월~2026년 초 | `inha_notice_093~` |
| `data/pr_data/` | 외부홍보 게시판 | `inha_pr_001~` |
