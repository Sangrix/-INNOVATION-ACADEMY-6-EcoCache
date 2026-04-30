# EcoCache

인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 벡터 데이터베이스에 색인하고,  
RAG(Retrieval-Augmented Generation) 기반으로 학생 질문에 답변하는 시스템입니다.

---

## 전체 아키텍처

시스템은 **임베딩 파이프라인**과 **쿼리 추론**으로 명확하게 분리되어 있습니다.

### 공통 — 임베딩 파이프라인

```
JSON 데이터셋 (문서 + QA 페어)
        │
        ▼
embed_pipeline.py
  └─ BGE-m3-ko 임베딩 (dragonkue/BGE-m3-ko)
  └─ 문서 청킹 (2,000자 초과 시 RecursiveCharacterTextSplitter)
        │
        ▼
      Qdrant
  ┌────┴────┐
  │         │
documents  qa_pairs
(문서 청크) (QA 페어)
```

두 Baseline이 동일한 Qdrant 컬렉션을 공유하며,  
쿼리 추론 방식만 다릅니다.

---

### Baseline 1 — Pure RAG

```
질문(query)
    │
    ▼
retriever_base.search()
    └─ query 임베딩
    └─ Qdrant: documents 컬렉션 벡터 검색 (top-k)
    │
    ▼
검색 결과 (문서 청크)
    │
    ▼
[선택] generate_answer()  ─→  LM Studio  ─→  자연어 답변
```

- `qa_pairs`를 **일절 참조하지 않음**
- 항상 `documents` 컬렉션에서 원문 청크 반환
- 순수 Dense Vector Retrieval 성능 측정용 베이스라인

---

### Baseline 2 — Semantic Cache RAG

```
질문(query)
    │
    ▼
retriever_base.search()
    └─ query 임베딩
    └─ Qdrant: qa_pairs 컬렉션 벡터 검색 (top-k)
    │
    ├─ top-1 score ≥ 0.75  ──→  qa_pairs 결과 반환  (캐시 히트 ✓)
    │
    └─ top-1 score < 0.75
           │
           ▼
       retriever_base.search()
           └─ Qdrant: documents 컬렉션 벡터 검색 (top-k)
           │
           ▼
       documents 결과 반환  (캐시 미스, fallback)
           │
           ▼
[선택] generate_answer()  ─→  LM Studio  ─→  자연어 답변
```

- QA 페어를 **시맨틱 캐시**로 활용 (유사 질문이 이미 있으면 즉시 반환)
- 캐시 미스 시 문서 원문으로 fallback
- 임계값(`QA_SIMILARITY_THRESHOLD=0.75`)으로 캐시 히트 기준 조정 가능

---

## 파일 구조

```
EcoCache/
├── config.py                  # 모든 설정 상수 (모델, 청킹, Qdrant, LM Studio)
│
├── embed_pipeline.py          # 임베딩 파이프라인: JSON → 임베딩 → Qdrant 업서트
│
├── retriever_base.py          # 공통: 모델·클라이언트 싱글턴, search(), BaseRetriever 추상 클래스
├── baseline_pure_rag.py       # Baseline 1: documents 컬렉션만 검색 (PureRAGRetriever)
├── baseline_semantic_cache.py # Baseline 2: qa_pairs → documents fallback (SemanticCacheRetriever)
│
├── query.py                   # CLI 진입점: --mode 선택, LLM 답변 생성, 평가 로깅
├── run_eval.py                # 배치 평가: 두 baseline 비교, --mode 옵션
├── eval_dashboard.py          # Streamlit 평가 대시보드 (두 로그 비교 탭 포함)
│
├── test_queries.json          # 25개 테스트 질문 세트 (8개 카테고리)
├── eval_log.jsonl             # 평가 결과 누적 로그 (자동 생성)
├── requirements.txt           # Python 의존성
├── spec.md                    # 임베딩 파이프라인 명세
├── spec_llm.md                # LLM 연결 명세 (LM Studio)
├── .env                       # 환경변수 (git 미포함)
│
├── sw_upstage_output/         # 배치 1: 2026년 최신 공지
├── sw_upstage_output_2/       # 배치 2: 2025년 11월 공지
├── sw_upstage_output_3/       # 배치 3: 2025년 12월~2026년 초
├── pr_data/                   # 외부홍보 게시물
└── qdrant_data/               # Qdrant 로컬 저장소 (자동 생성)
```

---

## 데이터셋

총 4개 배치로 구성되며, 각 배치마다 문서(doc)와 QA 페어(qa) 파일이 쌍을 이룹니다.

| 폴더 | 문서 파일 | QA 파일 | 내용 |
|------|-----------|---------|------|
| `sw_upstage_output/` | `inha_notice_data.json` | `inha_notice_qa.json` | 2026년 최신 공지 (inha_notice_001~) |
| `sw_upstage_output_2/` | `inha_sw_notice_157275_to_166292.json` | `inha_sw_notice_qa_157275_to_166292.json` | 2025년 11월 공지 (게시글 ID 기반) |
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` | 2025년 12월~2026년 초 (inha_notice_093~) |
| `pr_data/` | `inha_pr.json` | `inha_pr_qa.json` | 외부홍보 게시판 (inha_pr_001~) |

---

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

| 패키지 | 용도 |
|--------|------|
| `sentence-transformers` | BGE-m3-ko 임베딩 모델 |
| `qdrant-client` | 벡터 DB 클라이언트 |
| `langchain-text-splitters` | 문서 청킹 |
| `torch` | 임베딩 연산 |
| `streamlit`, `altair` | 평가 대시보드 |
| `openai` | LM Studio API 호출 (OpenAI 호환) |

### 2. Qdrant 실행 (Docker)

```bash
docker run -d \
  -p 6333:6333 \
  -v "$(pwd)/qdrant_data:/qdrant/storage" \
  qdrant/qdrant
```

### 3. 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다:

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=<LM Studio에서 로드한 모델명>
```

> **WSL2 사용 시**: `LM_STUDIO_URL`을 `localhost`로 설정해도 됩니다.  
> `config.py`가 `/proc/version`을 읽어 WSL2 환경임을 감지하면  
> 자동으로 Windows 호스트 IP(기본 게이트웨이)로 교체합니다.
>
> 단, LM Studio의 Local Server가 `0.0.0.0`에 바인딩되어 있어야 하며,  
> Windows 방화벽에서 1234 포트가 허용되어야 합니다.

---

## 실행 방법

### Step 1 — 임베딩 파이프라인

JSON 데이터를 벡터로 변환하여 Qdrant에 저장합니다.  
최초 1회 또는 데이터가 추가될 때마다 실행합니다.

```bash
python embed_pipeline.py
```

완료 시 Qdrant에 두 컬렉션이 생성됩니다:

| 컬렉션 | 내용 | 포인트 수 (참고) |
|--------|------|----------------|
| `documents` | 문서 청크 (제목 + 본문) | 189 |
| `qa_pairs` | QA 페어 (Q+A 합산 텍스트) | 136 |

---

### Step 2 — 검색 쿼리 (`query.py`)

`--mode` 옵션으로 두 Baseline 중 하나를 선택합니다.  
기본값은 `semantic_cache`입니다.

#### Baseline 1: Pure RAG

```bash
python query.py "i-PAC 콘테스트 신청 기간" --mode pure_rag
```

#### Baseline 2: Semantic Cache RAG (기본값)

```bash
python query.py "i-PAC 콘테스트 신청 기간"
python query.py "i-PAC 콘테스트 신청 기간" --mode semantic_cache
```

#### LLM 자연어 답변 생성

LM Studio에서 모델을 로드하고 Local Server를 시작한 뒤 실행합니다.

```bash
python query.py "캡스톤 성과 발표 날짜" --generate
python query.py "캡스톤 성과 발표 날짜" --mode pure_rag --generate
```

#### 검색 결과 로그 기록

```bash
python query.py "질문" --log
python query.py "질문" --log --log-file my_run.jsonl
python query.py "질문" --mode pure_rag --log --log-file pure_rag.jsonl
```

#### 게시판 유형 필터

```bash
python query.py "해커톤 신청" --board_type notice
python query.py "LG Aimers 모집" --board_type pr
```

**CLI 옵션 전체:**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode <모드>` | `semantic_cache` | `pure_rag` \| `semantic_cache` |
| `--generate` | — | LM Studio로 자연어 답변 생성 |
| `--log` | — | 결과를 `eval_log.jsonl`에 기록 |
| `--log-file <경로>` | `eval_log.jsonl` | 로그 파일 경로 지정 |
| `--board_type <값>` | — | 필터: `notice` \| `pr` |

---

### Step 3 — 배치 평가 (`run_eval.py`)

`test_queries.json`의 25개 테스트 질문을 일괄 실행하고 성능을 측정합니다.

#### 두 Baseline 각각 평가

```bash
# Baseline 1 평가
python run_eval.py --mode pure_rag --log-file eval_pure_rag.jsonl

# Baseline 2 평가
python run_eval.py --mode semantic_cache --log-file eval_semantic_cache.jsonl
```

#### 기타 옵션

```bash
# 특정 카테고리만 실행
python run_eval.py --mode pure_rag --category exact_match

# 기존 로그 파일 요약만 출력
python run_eval.py --summary-only --log-file eval_pure_rag.jsonl
```

**CLI 옵션 전체:**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode <모드>` | `semantic_cache` | `pure_rag` \| `semantic_cache` |
| `--test-file <경로>` | `test_queries.json` | 테스트 질문 파일 |
| `--log-file <경로>` | `eval_log.jsonl` | 결과 로그 파일 |
| `--category <이름>` | — | 카테고리 필터 |
| `--summary-only` | — | 기존 로그 요약만 출력 (평가 실행 안 함) |

출력 예시:
```
============================================================
 평가 요약  [mode: pure_rag]
============================================================
 총 질문 수     : 25
 Source 정확도  : 18/25 (72.0%)
 Doc Hit율      : 14/20 (70.0%)
 Top-1 유사도   : 평균 0.7834

 [카테고리별 Top-1 평균]
  exact_match               0.9102  (n=3)
  paraphrase                0.8521  (n=3)
  ...
```

**테스트 카테고리:**

| 카테고리 | 설명 |
|----------|------|
| `exact_match` | QA 파일과 완전히 일치하는 질문 |
| `paraphrase` | 구어체·축약형으로 변환한 질문 |
| `specific_info` | 신청 방법·기간 등 복합 질문 |
| `general_topic` | 장학금·해커톤 등 넓은 토픽 |
| `external_program` | 외부홍보(pr_data) 대상 질문 |
| `cross_source` | 공지 + 외부홍보에 동시 관련 |
| `edge_low_relevance` | 데이터셋에 없는 토픽 (낮은 유사도 확인) |
| `edge_ambiguous` | 여러 문서에 반복되는 중의적 질문 |
| `detail_retrieval` | 일시·장소·방법 등 세부 정보 추출 |

---

### Step 4 — 평가 대시보드 (`eval_dashboard.py`)

```bash
streamlit run eval_dashboard.py
```

브라우저에서 `http://localhost:8501` 접속.

**사이드바 설정:**

| 항목 | 설명 |
|------|------|
| 로그 파일 (주) | 분석할 JSONL 파일 경로 |
| 로그 파일 (비교용) | 두 번째 JSONL 파일 경로 — Tab 4 비교 활성화 |
| QA Threshold | 시뮬레이션 임계값 조절 |
| 경계 마진 (±) | 🟢🟡🔴 경계 기준 조절 |
| 출처 필터 | `qa_pairs` / `documents` 선택 |

**탭 구성:**

| 탭 | 내용 |
|----|------|
| 결과 테이블 | 각 쿼리를 펼쳐서 rank별 doc_id·score·답변 내용 확인 |
| Score 분포 | Top-1 유사도 히스토그램, QA vs Document 산점도 |
| Threshold 시뮬레이터 | 임계값 슬라이더로 qa_pairs/documents 비율 실시간 확인 |
| Baseline 비교 | **두 Baseline 점수 비교**: 요약 테이블·박스플롯·쿼리별 산점도·차이 테이블 |

#### 두 Baseline 비교 방법

```bash
# 각 Baseline 로그 생성
python run_eval.py --mode pure_rag       --log-file eval_pure_rag.jsonl
python run_eval.py --mode semantic_cache --log-file eval_semantic_cache.jsonl

# 대시보드 실행
streamlit run eval_dashboard.py
# 사이드바 → 로그 파일(주): eval_pure_rag.jsonl
#            로그 파일(비교용): eval_semantic_cache.jsonl
# → Tab 4 "Baseline 비교" 에서 쿼리별 점수 차이 확인
```

---

## 주요 설정값 (`config.py`)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `EMBED_MODEL_ID` | `dragonkue/BGE-m3-ko` | 한국어 특화 BGE 임베딩 모델 |
| `VECTOR_SIZE` | `1024` | 임베딩 벡터 차원 |
| `EMBED_BATCH_SIZE` | `8` | 임베딩 배치 크기 (GPU 환경은 32 권장) |
| `CHUNK_THRESHOLD` | `2000` | 이 이하 본문은 단일 청크로 처리 |
| `CHUNK_SIZE` | `1500` | 청킹 적용 시 청크 크기 (문자 수) |
| `CHUNK_OVERLAP` | `150` | 청크 간 오버랩 |
| `QA_SIMILARITY_THRESHOLD` | `0.75` | Semantic Cache 히트 기준 유사도 |
| `TOP_K` | `5` | 검색 반환 결과 수 |
| `LM_TEMPERATURE` | `0.3` | LLM 생성 온도 |
| `LM_MAX_TOKENS` | `512` | LLM 최대 출력 토큰 수 |
| `LM_CONTEXT_LIMIT` | `2000` | 프롬프트 컨텍스트 최대 문자 수 |

---

## LM Studio 연결

자세한 내용은 [`spec_llm.md`](spec_llm.md) 참조.

**빠른 시작:**
1. LM Studio에서 원하는 모델 로드
2. **Local Server → Start Server** 클릭 (서버 주소: `0.0.0.0`, 포트: `1234`)
3. `.env`에 `LM_STUDIO_MODEL=<모델명>` 입력
4. `python query.py "질문" --generate` 실행

권장 모델: `EEVE-Korean-10.8B`, `Qwen2.5-7B-Instruct`, `gemma-3-12b-it`

**WSL2 환경에서 Windows LM Studio 연결:**

```powershell
# Windows PowerShell (관리자)

# 포트 프록시 설정 (WSL2 게이트웨이 → LM Studio)
netsh interface portproxy add v4tov4 `
  listenaddress=<WSL2_GATEWAY_IP> listenport=1234 `
  connectaddress=127.0.0.1         connectport=1234

# 방화벽 규칙 추가
New-NetFirewallRule -DisplayName "LM Studio WSL2" `
  -Direction Inbound -Protocol TCP -LocalPort 1234 -Action Allow
```

> WSL2 게이트웨이 IP 확인: WSL2 터미널에서 `ip route show default | awk '{print $3}'`
>
> `config.py`가 WSL2를 자동 감지하여 `localhost` → Windows 호스트 IP로 교체합니다.  
> `.env`의 `LM_STUDIO_URL`은 `http://localhost:1234/v1`로 유지해도 됩니다.
