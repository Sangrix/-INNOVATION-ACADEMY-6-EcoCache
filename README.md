# EcoCache

인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 벡터 데이터베이스에 색인하고,  
RAG(Retrieval-Augmented Generation) 기반으로 학생 질문에 답변하는 시스템입니다.

---

## 전체 아키텍처

```
JSON 데이터셋 (문서 + QA 페어)
        │
        ▼
embed_pipeline.py  ──  BGE-m3-ko 임베딩  ──▶  Qdrant
                                                  │
                                    ┌─────────────┤
                                    │             │
                              qa_pairs       documents
                                    │             │
                                    └──────┬──────┘
                                           │
                                      query.py
                                     rag_search()
                                    (QA 우선 → fallback)
                                           │
                               ┌───────────┴────────────┐
                               │                        │
                        벡터 검색 결과           generate_answer()
                                                  (LM Studio)
                                                  자연어 답변
```

**2단계 검색 흐름:**  
1. `qa_pairs` 컬렉션에서 유사 QA를 검색 → top-1 유사도 ≥ 0.75이면 반환  
2. 임계값 미달 시 `documents` 컬렉션으로 fallback

---

## 데이터셋

총 4개 배치로 구성되며, 각 배치마다 문서(doc)와 QA 페어(qa) 파일이 쌍을 이룹니다.

| 폴더 | 문서 파일 | QA 파일 | 내용 |
|------|-----------|---------|------|
| `sw_upstage_output/` | `inha_notice_data.json` | `inha_notice_qa.json` | 2026년 최신 공지 (inha_notice_001~) |
| `sw_upstage_output_2/` | `inha_sw_notice_157275_to_166292.json` | `inha_sw_notice_qa_157275_to_166292.json` | 2025년 11월 공지 (게시글 ID 기반) |
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` | 2025년 12월~2026년 초 공지 (inha_notice_093~) |
| `pr_data/` | `inha_pr.json` | `inha_pr_qa.json` | 외부홍보 게시판 (inha_pr_001~) |

---

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

주요 패키지:

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
# Qdrant (로컬 기본값은 생략 가능)
QDRANT_URL=http://localhost:6333

# LM Studio (LLM 답변 생성 시 필요)
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=EEVE-Korean-10.8B-v1.0
```

> `LM_STUDIO_MODEL`은 LM Studio에서 현재 로드된 모델명과 일치해야 합니다.

---

## 실행 방법

### Step 1 — 임베딩 파이프라인 실행

JSON 데이터를 벡터로 변환하여 Qdrant에 저장합니다.  
최초 1회 또는 데이터가 추가될 때마다 실행합니다.

```bash
python embed_pipeline.py
```

완료 시 두 개의 컬렉션이 생성됩니다:

| 컬렉션 | 내용 | 벡터 수 (참고) |
|--------|------|---------------|
| `documents` | 문서 청크 (제목 + 본문) | ~수백 개 |
| `qa_pairs` | QA 페어 (Q+A 합산 텍스트) | ~수백 개 |

### Step 2 — 검색 쿼리

#### 기본 검색

```bash
python query.py "i-PAC 콘테스트 신청 기간"
```

#### 검색 + LLM 자연어 답변 생성

LM Studio에서 모델을 로드하고 Local Server를 시작한 뒤 실행합니다.

```bash
python query.py "i-PAC 콘테스트 신청 기간" --generate
```

#### 검색 결과 로그 기록

```bash
python query.py "캡스톤 성과 발표 날짜" --log
python query.py "캡스톤 성과 발표 날짜" --log --log-file my_run.jsonl
```

#### 게시판 유형 필터

```bash
python query.py "해커톤 신청" --board_type notice
python query.py "LG Aimers 모집" --board_type pr
```

#### 옵션 조합

```bash
python query.py "신청 기간" --generate --log --board_type notice
```

**CLI 옵션 전체:**

| 옵션 | 설명 |
|------|------|
| `--generate` | LM Studio로 자연어 답변 생성 |
| `--log` | 결과를 `eval_log.jsonl`에 기록 |
| `--log-file <경로>` | 로그 파일 경로 지정 |
| `--board_type <값>` | 필터: `notice` \| `pr` |

### Step 3 — 배치 평가 실행

`test_queries.json`의 25개 테스트 질문을 일괄 실행하고 성능을 측정합니다.

```bash
# 전체 실행
python run_eval.py

# 특정 카테고리만 실행
python run_eval.py --category exact_match

# 기존 로그 파일 요약만 출력
python run_eval.py --summary-only
```

출력 예시:
```
============================================================
 평가 요약
============================================================
 총 질문 수     : 25
 Source 정확도  : 20/25 (80.0%)
 Doc Hit율      : 15/20 (75.0%)
 Top-1 유사도   : 평균 0.8123

 [카테고리별 Top-1 평균]
  exact_match               0.9512  (n=3)
  paraphrase                0.8734  (n=3)
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

### Step 4 — 평가 대시보드

```bash
streamlit run eval_dashboard.py
```

브라우저에서 `http://localhost:8501` 접속.

**탭 구성:**

| 탭 | 내용 |
|----|------|
| 결과 테이블 | 각 쿼리를 펼쳐서 rank별 doc_id·score·답변 내용 확인 |
| Score 분포 | Top-1 유사도 히스토그램, QA vs Document 산점도 |
| Threshold 시뮬레이터 | 임계값 슬라이더로 qa_pairs/documents 비율 실시간 확인 |
| 실험 비교 | config별 성능 비교 테이블·박스플롯·히트맵 |

---

## 파일 구조

```
EcoCache/
├── config.py               # 모든 설정 상수 (모델, 청킹, Qdrant, LM Studio)
├── embed_pipeline.py       # JSON → 임베딩 → Qdrant 업서트
├── query.py                # RAG 검색 + LLM 답변 생성 + 평가 로깅
├── run_eval.py             # 배치 평가 실행 스크립트
├── eval_dashboard.py       # Streamlit 평가 대시보드
├── test_queries.json       # 25개 테스트 질문 세트
├── eval_log.jsonl          # 평가 결과 누적 로그 (자동 생성)
├── requirements.txt        # Python 의존성
├── spec.md                 # 임베딩 파이프라인 명세
├── spec_llm.md             # LLM 연결 명세 (LM Studio)
├── .env                    # 환경변수 (git 미포함)
│
├── sw_upstage_output/      # 배치 1: 2026년 최신 공지
├── sw_upstage_output_2/    # 배치 2: 2025년 11월 공지
├── sw_upstage_output_3/    # 배치 3: 2025년 12월~2026년 초
├── pr_data/                # 외부홍보 게시물
└── qdrant_data/            # Qdrant 로컬 저장소 (자동 생성)
```

---

## 주요 설정값 (config.py)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `EMBED_MODEL_ID` | `dragonkue/BGE-m3-ko` | 한국어 특화 BGE 임베딩 모델 |
| `VECTOR_SIZE` | `1024` | 임베딩 벡터 차원 |
| `CHUNK_THRESHOLD` | `2000` | 이 이하 본문은 단일 청크로 처리 |
| `CHUNK_SIZE` | `1500` | 청킹 적용 시 청크 크기 (문자 수) |
| `CHUNK_OVERLAP` | `150` | 청크 간 오버랩 |
| `QA_SIMILARITY_THRESHOLD` | `0.75` | QA 검색 통과 기준 유사도 |
| `TOP_K` | `5` | 검색 반환 결과 수 |
| `LM_TEMPERATURE` | `0.3` | LLM 생성 온도 (사실 기반 답변) |
| `LM_MAX_TOKENS` | `512` | LLM 최대 출력 토큰 수 |
| `LM_CONTEXT_LIMIT` | `2000` | 프롬프트 컨텍스트 최대 문자 수 |

GPU가 있는 경우 `EMBED_BATCH_SIZE`를 `8` → `32`로 늘리면 파이프라인 속도가 향상됩니다.

---

## LM Studio 연결

자세한 내용은 [`spec_llm.md`](spec_llm.md) 참조.

**빠른 시작:**
1. LM Studio에서 원하는 모델 로드
2. **Local Server → Start Server** 클릭
3. `.env`에 `LM_STUDIO_MODEL=<모델명>` 입력
4. `python query.py "질문" --generate` 실행

권장 모델: `EEVE-Korean-10.8B`, `Qwen2.5-7B-Instruct`, `gemma-3-12b-it`
