# EcoCache RAG 임베딩 파이프라인 설계 명세서

> 최종 수정: 2026-04-23 (임베딩 모델 변경: Solar → dragonkue/BGE-m3-ko)  
> 작성자: EcoCache 프로젝트 팀

---

## 1. 개요 (Overview)

### 목적

인하대학교 SW중심대학사업단 공지사항·외부홍보 데이터를 벡터 임베딩하여 RAG 기반 학생 Q&A 챗봇의 지식 베이스를 구축한다.

### 입력 데이터

| 배치 | 문서 파일 | QA 파일 | 문서 수 | QA 수 |
|------|-----------|---------|---------|-------|
| `sw_upstage_output/` | `inha_notice_data.json` | `inha_notice_qa.json` | 31 | 31 |
| `sw_upstage_output_2/` | `inha_sw_notice_157275_to_166292.json` | `inha_sw_notice_qa_157275_to_166292.json` | 31 | 31 |
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` | 31 | 31 |
| `pr_data/` | `inha_pr.json` | `inha_pr_qa.json` | 43 | 43 |
| **합계** | — | — | **136** | **136** |

**raw_text 길이 분포:**
- 최솟값: 0자 (빈 본문 존재)
- 중앙값: 806자 / 평균: 1,080자 / 최댓값: 5,929자
- 2,000자 이하: 115개 (85%)
- 2,000자 초과: 21개 (15%)

### 최종 결과물

- Qdrant 벡터 DB 컬렉션 2개 (`documents`, `qa_pairs`)
- 임베딩 파이프라인 스크립트 (`embed_pipeline.py`)
- 쿼리 인터페이스 스크립트 (`query.py`)

---

## 2. 임베딩 대상 (Embedding Targets)

두 종류의 청크를 별도 컬렉션으로 관리한다.

### 2-1. 문서 컬렉션 (`documents`)

- **입력 텍스트**: `[제목] {meta.title}\n\n{content.raw_text}`
- **목적**: 원문 기반 검색 — 챗봇이 공지 원문을 참조할 때 사용
- **예상 벡터 수**: 136개 이상 (긴 문서는 청킹으로 증가)

### 2-2. QA 컬렉션 (`qa_pairs`)

- **입력 텍스트**: `Q: {question.text}\nA: {answer.text}`
- **목적**: QA 기반 검색 — 학생 질문과 유사한 QA를 빠르게 매칭
- **예상 벡터 수**: 136개 (QA 페어는 단일 청크)

---

## 3. 청킹 전략 (Chunking Strategy)

> **단위 기준**: 모든 청킹 파라미터는 **문자 수(characters)** 기준이다. 토큰 수 혼용 금지.

### 데이터 분포 기반 정책

- raw_text 중앙값: 806자 / 평균: 1,080자 / 최댓값: 5,929자
- 2,000자 이하(115개, 85%): 단일 청크 처리
- 2,000자 초과(21개, 15%): 슬라이딩 윈도우 청킹 적용

### 청킹 파라미터

| 파라미터 | 값 | 비고 |
|----------|----|------|
| `CHUNK_THRESHOLD` | 2,000자 | 이 이하면 단일 청크 |
| `CHUNK_SIZE` | 1,500자 | 청킹 적용 시 청크 크기 (≈2,250토큰, Solar 4,096토큰 한도 내 안전) |
| `CHUNK_OVERLAP` | 150자 | 오버랩 |
| 텍스트 분리자 우선순위 | `\n\n` → `\n` → `。` → `.` | 의미 단위 우선 분리 |

### 청크 보강 (Context Enrichment)

각 청크 앞에 문서 제목과 날짜를 prefix로 추가한다:

```
[제목] 2026-1학기 i-PAC 인증 콘테스트 참여 신청 (~4.28.)
[날짜] 2026-04-03

{청크 본문}
```

### 빈 문서 처리 (우선순위 순)

| 조건 | 처리 방식 |
|------|-----------|
| `raw_text` 비어있고 `attachments` 있음 | `[제목] {title}\n[첨부] {file1}, {file2}` 형식으로 임베딩 |
| `raw_text` 비어있고 `attachments` 없음 | `[제목] {title}` 형식으로 임베딩 + `[WARN] 제목만으로 임베딩: {doc_id}` 로그 출력 |

> `[첨부 이미지 OCR N]` 레이블은 실제 OCR 본문의 일부이므로 전처리 없이 그대로 임베딩에 포함한다.

---

## 4. 임베딩 모델 (Embedding Model)

### 선택: dragonkue/BGE-m3-ko

| 항목 | 값 |
|------|-----|
| 모델 ID | `dragonkue/BGE-m3-ko` |
| 허깅페이스 | [dragonkue/BGE-m3-ko](https://huggingface.co/dragonkue/BGE-m3-ko) |
| 베이스 모델 | `BAAI/bge-m3` (한국어 데이터로 추가 파인튜닝) |
| 벡터 차원 | 1,024 |
| 최대 입력 토큰 | 8,192 tokens |
| 언어 | 한국어 특화 + 영어 + 다국어 (XLM-RoBERTa 기반) |
| 라이브러리 | `sentence-transformers` |
| 유사도 함수 | Cosine Similarity |

**선택 근거**: 한국어 공지사항 데이터에 특화된 로컬 실행 모델이다. Korean Embedding Benchmark(AutoRAG)에서 F1/Recall/NDCG 기준 최상위 성능(0.7456)을 기록했으며, 최대 8,192 토큰으로 긴 공지 본문도 단일 청크로 처리 가능하다. API 키 없이 로컬 추론이 가능해 비용이 발생하지 않는다.

**임베딩 방향**: 문서·QA 업서트 및 사용자 쿼리 모두 동일 모델(`dragonkue/BGE-m3-ko`) 사용 (대칭 임베딩).

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("dragonkue/BGE-m3-ko")
embeddings = model.encode(texts, normalize_embeddings=True)
# shape: (N, 1024)
```

### 대안 모델

| 모델 | 벡터 차원 | 최대 토큰 | 비고 |
|------|-----------|-----------|------|
| `BAAI/bge-m3` | 1,024 | 8,192 | BGE-m3-ko의 베이스. 다국어 범용, 한국어 파인튜닝 없음 |
| `jhgan/ko-sroberta-multitask` | 768 | 512 | 한국어 특화, 경량 모델. 긴 문서 처리 불리 |
| `upstage/solar-embedding-1-large` | 4,096 | 4,096 | API 기반, 한국어 성능 우수하나 유료 |
| `text-embedding-3-small` | 1,536 | 8,191 | OpenAI API 기반, 비용 발생 |

---

## 5. 벡터 데이터베이스 (Vector Database)

### 선택: Qdrant

| 항목 | 값 |
|------|-----|
| 배포 방식 | Docker 로컬 또는 Qdrant Cloud |
| 유사도 함수 | Cosine |
| Python SDK | `qdrant-client` |
| 메타데이터 필터 | 강력한 페이로드 필터 지원 |

**로컬 실행 (데이터 영속성 포함)**:

```bash
docker run -p 6333:6333 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

> 볼륨 마운트(`-v`) 없이 실행하면 컨테이너 재시작 시 모든 벡터 데이터가 소실된다. 반드시 위 명령어를 사용할 것.

### 컬렉션 설정

```python
from qdrant_client.models import VectorParams, Distance

client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
)

client.create_collection(
    collection_name="qa_pairs",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
)
```

### 대안

| DB | 특징 |
|----|------|
| Chroma | 로컬 개발용, 설정 간단 |
| Pinecone | 완전 관리형, 스케일 용이 |
| FAISS | 오프라인 전용, 메타데이터 필터 미지원 |

---

## 6. 파이프라인 아키텍처 (Pipeline Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                      embed_pipeline.py                       │
│                                                             │
│  JSON 로드 (8개 파일)                                        │
│      ↓                                                      │
│  전처리 (빈 텍스트 정책 적용, 제목·날짜 prefix 추가)         │
│      ↓                                                      │
│  청킹 (CHUNK_THRESHOLD 2,000자 기준, 슬라이딩 윈도우)        │
│      ↓                                                      │
│  임베딩 생성 (dragonkue/BGE-m3-ko 로컬 추론, 배치 32개)      │
│      ↓ [실패 시 해당 배치 스킵 + 로그 기록]                  │
│  Qdrant 업서트 (documents / qa_pairs 컬렉션)                 │
└─────────────────────────────────────────────────────────────┘
```

### 처리 흐름 의사코드

```python
# 1. 데이터 로드
docs = load_all_json_files(DOC_PATHS)
qas  = load_all_json_files(QA_PATHS)

# 2. 문서 청킹 및 임베딩
chunks = []
for doc in docs:
    chunks.extend(prepare_document(doc))  # 빈 문서 정책 + 청킹 처리

for batch in batched(chunks, size=32):
    texts = [c["text"] for c in batch]
    vectors = embed_model.encode(texts, normalize_embeddings=True).tolist()
    upsert_to_qdrant("documents", batch, vectors)

# 3. QA 임베딩
for batch in batched(qas, size=32):
    texts = [f"Q: {q['question']['text']}\nA: {q['answer']['text']}" for q in batch]
    vectors = embed_model.encode(texts, normalize_embeddings=True).tolist()
    upsert_to_qdrant("qa_pairs", batch, vectors)
```

### 에러 처리

`dragonkue/BGE-m3-ko`는 로컬 추론 모델이므로 API rate limit 오류가 없다. 대신 다음 예외를 처리한다:

```python
from sentence_transformers import SentenceTransformer

embed_model = SentenceTransformer("dragonkue/BGE-m3-ko")

def safe_encode(texts: list[str]) -> list | None:
    try:
        return embed_model.encode(texts, normalize_embeddings=True).tolist()
    except Exception as e:
        logger.warning(f"[SKIP] 임베딩 실패 배치 스킵: {e}")
        return None
```

인코딩 실패 배치는 스킵하고 실패 로그를 기록한다. 파이프라인 전체는 중단하지 않는다.

> **초기 실행 시**: 모델 최초 로드 시 HuggingFace에서 약 2.27GB 다운로드가 발생한다. 이후 캐시(`~/.cache/huggingface/`)에서 로드된다.

---

## 7. 벡터 메타데이터 스키마 (Metadata Schema)

### 포인트 ID 생성

모든 포인트 ID는 `uuid5(NAMESPACE_DNS, "{doc_id}_{chunk_index}")` 방식으로 생성한다.

```python
import uuid

def make_point_id(doc_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{chunk_index}"))

# 예: make_point_id("inha_notice_001", 0)
# → "a3f2c1d4-..." (고정 UUID)
```

**재실행 시 동작**: 동일 `doc_id` + `chunk_index` 조합은 항상 같은 UUID를 생성하므로 Qdrant upsert 시 자동 덮어쓰기된다.

> [!WARNING] OPEN ITEM:
> 현재 재실행 정책은 **upsert 덮어쓰기(잠정)**이다. 다음 시나리오에 대한 정책이 미결:
> - 기존 문서가 삭제된 경우 (벡터 DB에서 삭제되지 않음)
> - 청킹 결과 청크 수가 줄어든 경우 (이전 chunk_index의 고아 포인트 잔류)
> 향후 증분/스냅샷 정책 결정 시 이 항목을 업데이트할 것.

### documents 컬렉션 페이로드

```json
{
  "doc_id": "inha_notice_001",
  "chunk_index": 0,
  "chunk_total": 1,
  "title": "2026-1학기 i-PAC 인증 콘테스트 참여 신청",
  "published_at": "2026-04-03",
  "board_type": "notice",
  "board_name": "공지사항",
  "url": "https://swuniv.inha.ac.kr/...",
  "text": "청크 본문 텍스트"
}
```

### qa_pairs 컬렉션 페이로드

```json
{
  "qa_id": "inha_notice_qa_001",
  "source_doc_id": "inha_notice_001",
  "question": "신청 기간은 언제인가요?",
  "answer": "4월 1일(수) ~ 28일(화)",
  "reference_url": "https://swuniv.inha.ac.kr/...",
  "text": "Q: 신청 기간은 언제인가요?\nA: 4월 1일(수) ~ 28일(화)"
}
```

---

## 8. 검색 전략 (Retrieval Strategy)

### 기본 검색 (Dense)

```python
def search(query: str, collection: str, top_k: int = 5, filters: dict = None):
    query_vector = embed_model.encode([query], normalize_embeddings=True).tolist()[0]
    return qdrant_client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=top_k,
        query_filter=build_filter(filters),
    )
```

### 메타데이터 필터 예시

```python
# 공지사항만 검색
filters = {"board_type": "notice"}

# 특정 기간 공지 검색
filters = {"published_at": {"gte": "2026-01-01", "lte": "2026-04-30"}}
```

### 선택적 하이브리드 검색 (향후 확장)

Dense + BM25 결합:
- Dense 가중치: 0.7 / BM25 가중치: 0.3
- RRF(Reciprocal Rank Fusion) 적용

### RAG 응답 생성 흐름

```
사용자 질문
    ↓
qa_pairs 검색 (top-3)
    ↓
top-1 유사도 ≥ QA_SIMILARITY_THRESHOLD?
    YES → QA 답변 직접 활용
    NO  → documents 검색 (top-3) → 원문 기반 답변 생성
    ↓
Claude API로 최종 답변 생성 (검색 결과를 컨텍스트로)
```

`QA_SIMILARITY_THRESHOLD`는 `config.py`에서 설정하며 기본값은 `0.75`이다.

---

## 9. 구현 요구사항 (Implementation Requirements)

### Python 패키지

```txt
# requirements.txt
qdrant-client>=1.9.0
sentence-transformers>=3.0.0    # dragonkue/BGE-m3-ko 로컬 추론
langchain-text-splitters>=0.2.0
python-dotenv>=1.0.0
tqdm>=4.66.0
torch>=2.0.0                    # sentence-transformers 의존성 (CPU 전용 시 torch-cpu 가능)
```

### 환경변수 (`.env`)

```env
# 임베딩 모델은 로컬 실행이므로 API 키 불필요
QDRANT_URL=http://localhost:6333    # 로컬 Docker
QDRANT_API_KEY=                     # Qdrant Cloud 사용 시 필요
```

### config.py 파라미터 목록

```python
# 임베딩 모델
EMBED_MODEL_ID         = "dragonkue/BGE-m3-ko"
EMBED_BATCH_SIZE       = 32     # 한 번에 인코딩할 텍스트 수 (GPU 메모리에 따라 조정)

# 청킹 (모두 문자 수 기준)
CHUNK_THRESHOLD        = 2000   # 자: 이 이하면 단일 청크
CHUNK_SIZE             = 1500   # 자: 청킹 적용 시 청크 크기
CHUNK_OVERLAP          = 150    # 자: 오버랩

# 검색
QA_SIMILARITY_THRESHOLD = 0.75  # QA → documents fallback 기준
TOP_K                  = 5
```

### 스크립트 구조

```
EcoCache/
├── spec.md                 # 이 파일
├── .env                    # 환경변수 (git 제외)
├── config.py               # 경로·환경변수·파라미터 설정
├── embed_pipeline.py       # 메인 파이프라인 (로드→청킹→임베딩→업서트)
├── query.py                # 검색 인터페이스 (함수 또는 CLI)
└── requirements.txt
```

---

## 10. 스코프 아웃 (Out of Scope)

다음 기능은 **이번 버전의 구현 범위에 포함되지 않는다**:

| 항목 | 사유 |
|------|------|
| 하이브리드 검색(BM25 + Dense) 구현 | 향후 확장 예정, 현재 Dense 단독으로 충분 |
| 실시간 웹 크롤링 및 자동 데이터 업데이트 | 데이터 수집은 별도 파이프라인 범위 |
| REST API 서버 배포 (FastAPI 등) | 챗봇 통합 단계에서 별도 구현 |
| 스트리밍 응답 지원 | LLM 레이어 범위 |
| 증분 업데이트 자동화 (신규 배치 감지) | 재실행 정책 미결(§7 OPEN ITEM) 해결 후 |
| 멀티테넌시 / 사용자별 컬렉션 분리 | 현재 단일 지식 베이스로 충분 |

---

## 11. 검증 계획 (Verification Plan)

### 11-1. 파이프라인 완료 후 벡터 수 확인

```python
info_doc = client.get_collection("documents")
info_qa  = client.get_collection("qa_pairs")
assert info_doc.vectors_count >= 136, "문서 벡터 수 부족"
assert info_qa.vectors_count == 136,  "QA 벡터 수 불일치"
```

### 11-2. 샘플 쿼리 테스트 (5개)

| 쿼리 | 예상 top-1 문서/QA |
|------|-------------------|
| "i-PAC 콘테스트 신청 기간" | `inha_notice_001` |
| "SW역량평가 COEIC 응시 방법" | (관련 공지) |
| "장학금 신청 일정" | (관련 공지) |
| "외부 공모전 참가 지원" | (pr 관련) |
| "인하대 소프트웨어 융합대학 행사" | (pr 관련) |

**목표**: top-1 정확도 ≥ 80% (5개 중 4개 이상 일치)

### 11-3. 성능 지표

| 지표 | 목표 |
|------|------|
| 임베딩 처리 시간 | 136개 기준 ≤ 3분 |
| 검색 응답 시간 | ≤ 500ms |
| top-1 코사인 유사도 | ≥ 0.75 |
