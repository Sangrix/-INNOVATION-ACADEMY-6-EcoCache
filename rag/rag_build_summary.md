# RAG Build Summary

## 목적

웹 데모와 Lambda/API 연결을 위해 retrieval-only 실험 코드를 RAG 서비스 형태로 정리했습니다.

## 현재 구조

```text
사용자 질문
→ SemanticCacheRetriever
→ QA cache 검색
→ threshold 이상이면 cache answer 반환
→ threshold 미만이면 documents 검색
→ RagAnswerGenerator
→ LLM 답변 또는 retrieval fallback 답변 생성
→ response_adapter
→ 웹/API 응답 형태로 반환
```

cache hit이면 QA 답변을 즉시 반환하고 LLM을 호출하지 않습니다. documents 검색으로 내려간 경우에만 LM Studio 또는 fallback 답변 생성 단계로 넘어갑니다.

질문 임베딩은 요청당 한 번만 생성해서 QA cache 검색과 documents 검색에서 재사용합니다. 문서 임베딩은 Qdrant에 미리 적재된 값을 사용하므로 질문할 때마다 전체 문서를 다시 임베딩하지 않습니다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `langchain_pipeline.py` | 전체 RAG 실행 진입점 |
| `semantic_cache_retriever.py` | QA cache hit/miss 판단 및 documents fallback |
| `answer_generator.py` | cache 답변, LM Studio 답변, fallback 답변 생성 |
| `response_adapter.py` | 웹/API 응답 스키마로 변환 |
| `vector_store.py` | Qdrant 검색 |
| `document_loader.py` | JSON 데이터를 LangChain Document로 변환 |
| `text_splitter.py` | chunk 분할 |

## 현재 기본값

최적화 결과를 반영한 1차 기본값입니다.

```text
top_k = 5
threshold = 0.75
chunk_size = 2000
chunk_overlap = 200
```

## 응답 형태

```json
{
  "answer": "...",
  "cache_hit": false,
  "similarity": 0.82,
  "latency_ms": 120.5,
  "co2_grams": null,
  "ci_g_per_kwh": null,
  "sources": [
    {
      "rank": 1,
      "score": 0.82,
      "doc_id": "inha_notice_001",
      "title": "공지 제목",
      "url": "https://..."
    }
  ],
  "retrieval": {
    "source": "documents",
    "qa_top1_score": 0.62,
    "threshold": 0.75,
    "top_k": 5,
    "qa_top_k": 5,
    "doc_top_k": 5
  },
  "generation": {
    "mode": "llm",
    "model": "qwen2.5-7b-instruct",
    "error": null
  }
}
```

## generation mode

| mode | 의미 |
| --- | --- |
| `cache` | QA semantic cache에서 바로 답변 |
| `llm` | documents 검색 결과를 LLM에 넣어 답변 |
| `retrieval_fallback` | LLM 설정이 없거나 호출 실패 시 검색 결과 기반 답변 |
| `empty` | 검색 결과가 없는 경우 |

## LM Studio 연결

LM Studio Local Server가 켜져 있으면 documents 검색 결과를 context로 넣어 LLM 답변을 생성할 수 있습니다. `.env`에 `LM_STUDIO_MODEL`을 지정하면 해당 모델을 사용하고, 비워두면 LM Studio의 `/v1/models`에서 로드된 모델을 자동 감지합니다.

## 실행 예시

```powershell
$env:QDRANT_LOCAL_PATH=(Resolve-Path ".").Path + "\qdrant_local"
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?"
```

LLM 없이 retrieval만 확인:

```powershell
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?" --no-generate
```
