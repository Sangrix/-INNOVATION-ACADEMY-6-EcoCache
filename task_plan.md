# Task Plan — 희승: RAG API 베이스라인 + 출처 표시

**목표:** `POST /chat` 엔드포인트 1개. 학사정보 ingestion → retrieval → LLM → 출처 포함 JSON 응답.  
**검증 기준:** `curl localhost:8000/chat -d '{"query":"졸업학점 알려줘"}'` 실행 시 JSON 응답 반환.  
**시작일:** 2026-05-11

---

## 현재 프로젝트 컨텍스트

기존 `rag/` 디렉토리에는 이미 Qdrant 기반 임베딩 파이프라인과 검색 로직이 있다.
이번 태스크는 그 위에 **FastAPI HTTP 레이어**를 올려 외부에서 호출 가능한 API를 만드는 것이다.

- 기존 임베딩 모델: `dragonkue/BGE-m3-ko` (1024차원)
- 기존 Qdrant 컬렉션: `documents`, `qa_pairs`
- 기존 검색: `rag/retriever_base.py`, `rag/baseline_semantic_cache.py`
- 기존 LLM 연결: `rag/query.py` → `generate_answer()` (LM Studio)

---

## 응답 JSON 스키마

> ⚠️ **"위 스키마"가 외부 문서에 정의되어 있다면 해당 파일을 공유해 주세요.**  
> 아래는 "출처 표시" 요건을 기준으로 도출한 **초안 스키마**입니다.

```json
{
  "answer": "string | null",
  "sources": [
    {
      "doc_id": "string",
      "title": "string",
      "url": "string | null",
      "published_at": "string | null",
      "score": 0.0,
      "chunk_index": 0,
      "text_preview": "string"
    }
  ],
  "cache_hit": false,
  "qa_top1_score": null,
  "retrieval_source": "qa_pairs | documents",
  "latency_ms": 0.0,
  "error": null
}
```

---

## 체크리스트

- [x] **Phase 1** — ingestion SKIP (기존 Qdrant 데이터 재사용)
- [x] **Phase 2** — FastAPI 앱 + `POST /chat` 엔드포인트
- [x] **Phase 3** — 응답 JSON 스키마 전 필드 자리 확보
- [x] **Phase 4** — README (curl 호출 방법)
- [x] **검증** — curl 테스트 통과

---

## Phase 1 — 학사정보 ingestion 스크립트

**목표:** 학사정보 JSON/텍스트 → 청킹 → 임베딩 → Qdrant `academic_info` 컬렉션 업서트  
**상태:** `[ ] not_started`

### 결정사항
- 벡터 DB: Qdrant (기존 인프라 재사용, 컬렉션만 추가)
- 임베딩: 기존 `dragonkue/BGE-m3-ko` 그대로 사용
- 컬렉션 이름: `academic_info` (기존 `documents`, `qa_pairs`와 분리)
- 데이터 소스: TBD — 학사정보 파일 경로/형식 확인 필요

### 작업 항목
- [ ] 학사정보 원본 파일 위치·형식 파악
- [ ] `ingest_academic.py` 작성 (청킹 + 임베딩 + Qdrant 업서트)
- [ ] 실행 후 Qdrant 포인트 수 확인

---

## Phase 2 — FastAPI 앱 + POST /chat

**목표:** `uvicorn` 으로 `localhost:8000` 에서 실행되는 API 서버  
**상태:** `[ ] not_started`

### 기술 스택
- **FastAPI** + **uvicorn**
- 기존 `rag/retriever_base.py` + `rag/query.py` 재사용
- LLM: `generate_answer()` (LM Studio, 없으면 `null` 반환)

### 파일 구조 (신규)
```
api/
├── main.py          FastAPI 앱, /chat 라우터
├── schemas.py       Pydantic 요청/응답 모델
└── requirements.txt fastapi, uvicorn 추가
```

### /chat 흐름
```
POST /chat {"query": "..."}
  → rag_search(query)            # retriever_base.search()
  → generate_answer(query, result)  # LM Studio (선택)
  → ChatResponse(answer, sources, cache_hit, ...)
```

---

## Phase 3 — 응답 JSON 스키마 전 필드 자리 확보

**목표:** 모든 필드가 `null`/기본값이라도 응답에 포함  
**상태:** `[ ] not_started`

- Pydantic `Optional` + 기본값으로 처리
- `sources` 필드: `List[SourceItem]`  
- `error` 필드: 예외 발생 시 채워짐

---

## Phase 4 — README

**목표:** clone 직후 curl 테스트까지 10줄 안에 설명  
**상태:** `[ ] not_started`

포함 내용:
1. 의존성 설치
2. Qdrant 실행
3. ingestion 실행
4. API 서버 실행
5. curl 예제 + 기대 응답

---

## 오류 로그

| 오류 | 발생 단계 | 해결 |
|------|-----------|------|
| (없음) | — | — |

---

## 결정 로그

| 결정 | 근거 |
|------|------|
| Qdrant 재사용 | 기존 인프라, 설치 불필요 |
| FastAPI | 빠른 Pydantic 통합, 자동 docs |
| LLM 없어도 작동 | `generate_answer` 실패 시 answer=null, sources만 반환 |
