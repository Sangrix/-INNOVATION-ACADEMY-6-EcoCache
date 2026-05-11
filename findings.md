# Findings — 희승: RAG API 베이스라인 + 출처 표시

## 기존 코드베이스 파악 (2026-05-11)

### 재사용 가능한 컴포넌트

| 파일 | 재사용 방법 |
|------|------------|
| `rag/retriever_base.py` | `get_model()`, `get_client()`, `search()` 직접 import |
| `rag/baseline_semantic_cache.py` | `SemanticCacheRetriever.retrieve()` — qa_pairs→documents 2단계 검색 |
| `rag/baseline_pure_rag.py` | `PureRAGRetriever.retrieve()` — documents만 검색 |
| `rag/query.py` | `generate_answer()`, `_build_context()` — LM Studio 연동 |
| `rag/config.py` | Qdrant URL, 임베딩 모델, LM Studio 설정 (WSL2 자동 감지 포함) |

### Qdrant 컬렉션 현황

| 컬렉션 | 용도 |
|--------|------|
| `documents` | 공지사항·홍보 게시물 청크 |
| `qa_pairs` | QA 페어 (시맨틱 캐시) |

→ 학사정보용 `academic_info` 컬렉션을 추가로 생성 예정

### rag_search() 반환 스키마 (현재)

```python
{
    "source": "qa_pairs" | "documents",
    "results": [
        {"score": float, "payload": {...}}
    ],
    "query": str,
    "qa_top1_score": float | None,
}
```

### /chat 응답에 필요한 매핑

| API 필드 | 현재 retrieval 필드 |
|----------|-------------------|
| `retrieval_source` | `result["source"]` |
| `cache_hit` | `result["source"] == "qa_pairs"` |
| `qa_top1_score` | `result["qa_top1_score"]` |
| `sources[].doc_id` | `payload["doc_id"]` (documents) / `payload["source_doc_id"]` (qa_pairs) |
| `sources[].title` | `payload["title"]` |
| `sources[].url` | `payload["url"]` |
| `sources[].score` | `r["score"]` |
| `sources[].chunk_index` | `payload["chunk_index"]` |
| `sources[].text_preview` | `payload["text"][:120]` |

### WSL2 LM Studio 연결

`config.py`의 `_lm_studio_url()`이 자동으로 Windows 게이트웨이 IP로 교체한다.  
LM Studio에서 "Listen on all interfaces (0.0.0.0)" 활성화 필요.

---

## LLM 빈 응답 문제 (해결됨)

- **증상:** `generate_answer()` 가 `''` (빈 문자열) 반환, `finish_reason: length`
- **원인:** `LM_MAX_TOKENS=512`일 때 입력 컨텍스트(~2089자 ≈ 700토큰) + 512 = ~1212토큰이 모델 컨텍스트 한도를 초과. LM Studio가 출력 예약 토큰을 포함해 총량을 계산하는 방식 때문에 발생.
- **해결:** `LM_MAX_TOKENS = 4096`으로 상향. 응답 정상화.
- **재현 조건:** 컨텍스트가 500자 이하면 `max_tokens=512`도 통과. 대형 문서가 많을수록 빈 응답 위험.

## 미확인 사항

- [ ] **"위 스키마"** — 외부 문서에 정의된 스키마가 있는지 확인 필요
- [ ] **학사정보 원본 파일** — 경로·형식(JSON/PDF/텍스트) 미확인
- [ ] **학사정보 컬렉션** — 기존 `documents`에 합칠지 별도 컬렉션으로 분리할지 결정 필요
