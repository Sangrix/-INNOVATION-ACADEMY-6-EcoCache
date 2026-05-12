# LangChain RAG Pipeline

이 문서는 웹 데모에 붙일 LangChain 형태의 RAG 검색 파이프라인 구조를 정리합니다.

## 목적

- 기존 Qdrant 벡터 검색 구조를 유지합니다.
- QA semantic cache를 먼저 검색하고, 기준 점수 미달 시 documents 검색으로 내려갑니다.
- LLM provider가 아직 확정되지 않아도 retrieval, source metadata, response schema를 먼저 안정화합니다.
- 나중에 Lambda/API 스키마가 바뀌면 `rag/response_adapter.py`만 조정할 수 있게 분리합니다.

## 실행 흐름

```text
사용자 질문
→ QA 컬렉션 검색
→ top-1 similarity >= threshold 이면 cache hit
→ cache hit이면 QA 답변과 출처 반환
→ 아니면 documents 컬렉션 검색
→ 문서 출처와 similarity 반환
→ response_adapter에서 웹/API 응답 형태로 변환
```

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `rag/langchain_config.py` | top-k, threshold, chunk size 등 튜닝 설정 |
| `rag/document_loader.py` | JSON 데이터를 LangChain `Document`로 변환 |
| `rag/text_splitter.py` | LangChain text splitter 생성 |
| `rag/vector_store.py` | SentenceTransformer + Qdrant 검색 |
| `rag/semantic_cache_retriever.py` | QA cache hit/miss 판단과 문서 fallback |
| `rag/langchain_pipeline.py` | 전체 retrieval pipeline 실행 |
| `rag/response_adapter.py` | 백엔드 응답 스키마 변환 |
| `rag/retrieval_eval.py` | threshold/top-k 평가 실행 |

## 단일 질문 실행

Qdrant가 먼저 실행되어 있고, 기존 embedding pipeline으로 컬렉션이 만들어져 있어야 합니다.

```powershell
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?" --top-k 3 --threshold 0.8
```

## 작은 평가 실행

```powershell
python -m rag.retrieval_eval --query-file test_queries.json --top-k 3 --threshold 0.8 --limit 10
```

## 여러 설정 자동 비교

`top_k`와 `threshold` 후보를 한 번에 비교하려면 아래 명령을 사용합니다.

```powershell
python -m rag.retrieval_sweep --query-file test_queries.json --top-ks 3,5 --thresholds 0.75,0.8,0.85 --limit 10 --output-dir outputs/retrieval_sweep_test
```

생성되는 파일:

| 파일 | 내용 |
| --- | --- |
| `retrieval_sweep_summary.md` | 회의 공유용 요약 표 |
| `retrieval_sweep_summary.csv` | 엑셀/스프레드시트용 요약 표 |
| `retrieval_sweep_results.json` | 질문별 상세 결과 포함 전체 로그 |

## 다음 최적화 지점

- `threshold`: 0.75, 0.80, 0.85 후보 비교
- `top_k`: 3, 5 후보 비교
- `chunk_size`: 기존 값 기준으로 필요 시 1000, 1500, 2000 비교
- `source metadata`: 웹에서 클릭 가능한 `title`, `url`, `doc_id` 유지
