# EcoCache — 브랜치 개요

> **브랜치:** `fead/co2-eval-results-20260502`  
> **기준 커밋:** `d3a1245` (feat: add eval pipeline with B1/B2/CIASC modes and 50 test queries)  
> **작성일:** 2026-05-03

---

## 1. 무엇을 만들었나

EcoCache는 인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 대상으로 한 **RAG(검색 증강 생성) 기반 학생 Q&A 시스템**입니다.

이 브랜치의 핵심 기여는 단순한 검색 성능 평가를 넘어, **탄소 효율**을 검색 전략의 하나로 다루었다는 점입니다. 구체적으로는 전력망의 탄소 집약도(Carbon Intensity, CI)가 높아지는 시간대에 캐시 재사용을 적극적으로 유도함으로써, 정확도를 유지하면서 임베딩 연산에 소비되는 에너지·CO2를 줄이는 방법을 실험했습니다.

---

## 2. 시스템 아키텍처

```
JSON 데이터셋 (문서 + QA 페어)
        │
        ▼
 embed_pipeline.py
 (BGE-m3-ko 임베딩 → Qdrant 업서트)
        │
        ▼
    Qdrant 벡터 DB
   ┌────┴────┐
qa_pairs  documents
   └────┬────┘
        │
   query.py  ─────────────────────────────────────────────────┐
   rag_search()                                               │
   ┌──────────────────────────────────────────────────────┐   │
   │  1단계: qa_pairs 검색                                │   │
   │         top-1 유사도 ≥ θ(t) → QA 답변 반환          │   │  carbon_monitor.py
   │         (캐시 히트)                                  │   │  (stage별 전력/CO2 측정)
   │  2단계: documents 검색 fallback                      │   │
   │         (캐시 미스 → 원문 청크 반환)                 │   │
   └──────────────────────────────────────────────────────┘   │
        │                                                     │
        ▼                                                     │
   generate_answer()    ◄────────────────────────────────────┘
   (LM Studio, OpenAI 호환 API)
   자연어 답변 생성
```

**θ(t) — 동적 임계값 (CIASC 모드)**

```
θ(t) = 0.75 − α × (CI_norm − 0.5)
CI_norm = clamp((CI − 350) / 150, 0, 1)
범위: [0.70, 0.95]
```

CI가 높을수록 θ가 낮아져 캐시 히트 조건이 완화되고, 더 많은 질문이 QA 캐시에서 처리됩니다. CI가 낮을수록 θ가 높아져 정확도 우선으로 동작합니다.

---

## 3. 코드 구조

```
EcoCache/
│
│  ── 핵심 파이프라인 ──
├── config.py               모든 설정 상수 (임베딩 모델, 청킹, Qdrant, LM Studio, 탄소 측정)
├── embed_pipeline.py       JSON 데이터 → BGE-m3-ko 임베딩 → Qdrant 업서트
├── query.py                RAG 2단계 검색 + LLM 답변 생성 + 평가 로깅
├── carbon_monitor.py       stage별 전력·CO2 측정 (CodeCarbon + pynvml GPU 샘플링)
├── carbon_optimizer.py     CI 기반 동적 θ(t) 계산 (CIASC 알고리즘)
│
│  ── 평가 ──
├── run_eval.py             B1/B2/CIASC 모드 배치 평가 + CO2 요약 출력
├── eval_dashboard.py       Streamlit 평가 대시보드 (4탭)
├── test_queries.json       50문항 테스트 세트 (9개 카테고리)
│
│  ── 로그 (실험 산출물) ──
├── b1_eval_log.jsonl       B1 모드 실험 결과
├── b2_eval_log.jsonl       B2 모드 실험 결과
├── ciasc_alpha0.25_eval_log.jsonl
├── ciasc_alpha0.50_eval_log.jsonl
├── ciasc_alpha1.00_eval_log.jsonl
│
│  ── 문서 ──
├── docs/co2_eval_results_20260502.md   2026-05-02 로컬 GPU 재측정 결과 및 해석
├── spec.md                              임베딩 파이프라인 명세
├── spec_llm.md                          LM Studio 연결 명세
├── snapshots/feat_eval_pipeline_original_20260502_190451/
│   └── (콘솔 출력·JSONL 로그 전 모드 원본 보관)
│
│  ── 데이터 ──
├── sw_upstage_output/      배치 1: 2026년 최신 공지 (inha_notice_001~)
├── sw_upstage_output_2/    배치 2: 2025년 11월 공지 (게시글 ID 기반)
├── sw_upstage_output_3/    배치 3: 2025년 12월~2026년 초 공지
└── pr_data/                외부홍보 게시물
```

---

## 4. 핵심 모듈 설명

### 4-1. `embed_pipeline.py` — 임베딩 파이프라인

4개 배치의 문서(doc)와 QA 페어(qa)를 읽어 두 개의 Qdrant 컬렉션으로 구성합니다.

- **청킹 전략**: 본문 길이 ≤ 2000자 → 단일 청크, 초과 시 `RecursiveCharacterTextSplitter`(chunk=1500, overlap=150)
- **임베딩 모델**: `dragonkue/BGE-m3-ko` (1024차원, 코사인 유사도)
- **Qdrant 컬렉션**

  | 컬렉션 | 저장 단위 | 포함 필드 |
  |--------|-----------|-----------|
  | `documents` | 문서 청크 | doc_id, chunk_index, title, published_at, board_type, text |
  | `qa_pairs` | QA 페어 | qa_id, source_doc_id, question, answer, reference_url |

### 4-2. `query.py` — RAG 검색

```
rag_search(query)
 └─ search(qa_pairs, top_k=3) → qa_top1_score
      ├─ ≥ θ(t): {"source": "qa_pairs", "results": [...]}
      └─ < θ(t): search(documents, top_k=3) → {"source": "documents", "results": [...]}
```

`generate_answer()`를 추가로 호출하면 검색 결과를 컨텍스트로 LM Studio에 전달해 자연어 답변을 생성합니다.

### 4-3. `carbon_monitor.py` — 탄소 측정

`CarbonMonitor.track(stage_name)` 컨텍스트 매니저로 각 단계를 감쌉니다.

- **전력 측정**: pynvml로 GPU 전력을 0.1초 간격 샘플링
- **에너지 측정**: CodeCarbon `EmissionsTracker`
- **CO2 환산**: `energy_kwh × CI_value(g/kWh)`
- **측정 항목**: `qa_pairs_retrieval`, `documents_retrieval`, `llm_generation`

### 4-4. `carbon_optimizer.py` — CIASC 알고리즘

한국 시간대별 탄소 집약도 룩업테이블(0시~21시, 정적 프록시 데이터)을 기반으로 현재 CI를 가져오고, 수식에 따라 `qa_similarity_threshold`를 동적으로 결정합니다.

| 시간대 | CI (gCO2/kWh) |
|--------|--------------|
| 12:00 | 385 (가장 낮음) |
| 15:00 | 375 (가장 낮음) |
| 0:00  | 430 (높음) |
| 3:00  | 415 |

CI가 높은 밤 시간대에 θ를 낮춰 캐시 히트를 유도하는 것이 핵심 아이디어입니다.

### 4-5. `run_eval.py` — 배치 평가

세 가지 모드를 동일한 50문항 세트로 실행하고 공정하게 비교합니다.

| 모드 | 전략 | θ |
|------|------|---|
| **B1** | 캐시 없음 (Pure RAG) | 1.10 고정 (사실상 항상 documents) |
| **B2** | 정적 시맨틱 캐시 | 0.90 고정 |
| **CIASC** | CI 적응형 동적 캐시 | 0.70~0.95 동적 결정 |

---

## 5. 실험 설계

### 목적

RAG 시스템에서 시맨틱 캐시의 임계값을 고정하지 않고 **전력망의 탄소 집약도에 따라 동적으로 조정**하면:

1. 정확도(Source 정확도)를 유지하거나 높일 수 있는가?
2. 캐시 히트율을 높여 총 CO2 배출량을 줄일 수 있는가?
3. α 값에 따라 CO2–정확도 트레이드오프가 어떻게 달라지는가?

### 평가 지표

| 지표 | 정의 |
|------|------|
| **Source 정확도** | `expected_source`와 실제 반환 출처가 일치한 비율 |
| **캐시 히트율** | 전체 질문 중 `qa_pairs`에서 처리된 비율 |
| **Top-1 유사도** | 반환된 rank-1 결과의 코사인 유사도 평균 |
| **총 CO2 (g)** | 배치 전체의 임베딩·검색 CO2 합산 |
| **평균 지연 (ms)** | 질문당 `rag_search()` 평균 응답 시간 |

### 테스트 세트 (50문항)

9개 카테고리로 구성된 `test_queries.json`:

| 카테고리 | 설명 |
|----------|------|
| `exact_match` | QA 파일과 완전히 일치하는 질문 |
| `paraphrase` | 구어체·축약형으로 변환한 질문 |
| `specific_info` | 신청 방법·기간 등 복합 정보 질문 |
| `general_topic` | 장학금·해커톤 등 넓은 토픽 |
| `external_program` | 외부홍보(pr_data) 대상 질문 |
| `cross_source` | 공지 + 외부홍보에 동시에 관련된 질문 |
| `edge_low_relevance` | 데이터셋에 없는 토픽 (낮은 유사도 동작 검증) |
| `edge_ambiguous` | 여러 문서에 반복되는 중의적 질문 |
| `detail_retrieval` | 일시·장소·방법 등 세부 정보 추출 |

---

## 6. 실험 결과 (2026-05-02 로컬 GPU)

**실행 환경**: NVIDIA RTX 3050 4GB / `dragonkue/BGE-m3-ko` / CI 환산 430 gCO2/kWh

| 설정 | Source 정확도 | 캐시 히트율 | 평균 지연 | 총 CO2 | 질문당 CO2 | θ 변화 |
|------|-------------:|------------:|----------:|-------:|-----------:|--------|
| **B1** (캐시 없음) | 66.0% | 0.0% | 18,204 ms | 1.4236 g | 0.02847 g | 1.10 고정 |
| **B2** (정적 캐시) | 68.0% | 2.0% | 16,617 ms | 1.0794 g | 0.02159 g | 0.90 고정 |
| **CIASC α=0.25** | 72.0% | 6.0% | 20,516 ms | 1.0590 g | 0.02118 g | 0.80 → 0.95 |
| **CIASC α=0.50** | 72.0% | 6.0% | 16,280 ms | 1.0554 g | 0.02111 g | 0.80 → 0.95 |
| **CIASC α=1.00** | **78.0%** | **12.0%** | **15,827 ms** | **1.0154 g** | **0.02031 g** | 0.76 → 0.95 |

**B1 대비 CIASC α=1.00 개선량:**
- Source 정확도: +12.0%p
- CO2: −28.7% (1.4236 g → 1.0154 g)
- 평균 지연: −13.1%

---

## 7. 현재 구현의 주의점

이번 실험 결과는 현재 브랜치 상태를 **그대로 재현**한 것으로, 알고리즘 최종 검증 결과로 해석하기 전에 아래 두 가지를 확인해야 합니다.

**① alpha 하드코딩**  
`carbon_optimizer.py` 내부에서 `alpha = 0.15`로 덮어씁니다. CLI에서 `--alpha 0.25/0.5/1.0`을 전달해도 실제 수식에 반영되지 않습니다.

```python
# carbon_optimizer.py L33 — 현재 상태
alpha = 0.15  # 조정 계수 (2주차 실험 대상)  ← CLI 인자를 무시
```

**② 임계값 누적 증가**  
CIASC 모드에서 `base_theta = config.QA_SIMILARITY_THRESHOLD`를 사용하는데, 이 값이 직전 질문에서 업데이트된 θ를 그대로 다음 기준값으로 씁니다. 결과적으로 질문이 진행될수록 θ가 누적 증가해 최종적으로 0.95에 도달합니다.

**수정 방향:**
```python
# 권장: 고정 기준값 사용
base_theta = 0.75  # config 값 대신 상수로 고정
```

이 두 가지를 수정하면 α 변화에 따른 CO2–정확도 트레이드오프를 공정하게 측정할 수 있습니다.

---

## 8. 실행 방법 요약

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. Qdrant 실행
docker run -d -p 6333:6333 -v "$(pwd)/qdrant_data:/qdrant/storage" qdrant/qdrant

# 3. 임베딩 파이프라인 (최초 1회)
python embed_pipeline.py

# 4. 단건 검색
python query.py "i-PAC 콘테스트 신청 기간"

# 5. LLM 답변 생성 (LM Studio 서버 실행 후)
python query.py "캡스톤 성과 발표 날짜" --generate

# 6. 배치 평가
python run_eval.py --mode b1
python run_eval.py --mode b2
python run_eval.py --mode ciasc --alpha 1.0

# 7. 모드 간 비교 표 출력
python run_eval.py --compare

# 8. 평가 대시보드
streamlit run eval_dashboard.py
```

---

## 9. 다음 단계

| 항목 | 내용 |
|------|------|
| alpha 하드코딩 수정 | `carbon_optimizer.py`에서 인자로 받은 alpha가 수식에 반영되도록 수정 |
| 임계값 누적 문제 수정 | `base_theta`를 고정값으로 변경 |
| 실시간 CI 연동 | 정적 룩업테이블 → 실제 API(KPX, Electricity Maps 등) 교체 |
| Hybrid Search | Dense + Sparse(BM25) 검색 병행으로 키워드 정확도 향상 |
| 시맨틱 캐시 자가 성장 | `generate_answer()` 결과를 `qa_pairs`에 upsert해 캐시 자동 확장 |
