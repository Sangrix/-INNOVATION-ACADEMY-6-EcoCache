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

## Qdrant 실행 방식

Docker가 있으면 Qdrant 서버를 띄워서 사용할 수 있습니다. Docker가 없으면 `QDRANT_LOCAL_PATH`를 지정해 파일 기반 로컬 Qdrant로 실행할 수 있습니다.

```powershell
$env:QDRANT_LOCAL_PATH=(Resolve-Path ".").Path + "\qdrant_local"
```

이 값을 지정하면 `localhost:6333` 서버에 접속하지 않고, `qdrant_local` 폴더에 벡터 데이터를 저장합니다.

## 단일 질문 실행

Qdrant 서버 또는 `QDRANT_LOCAL_PATH`가 준비되어 있고, 기존 embedding pipeline으로 컬렉션이 만들어져 있어야 합니다.

```powershell
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?" --top-k 3 --threshold 0.8
```

LM Studio 모델이 설정되어 있지 않으면 documents fallback 시 검색 결과 기반 fallback 답변을 반환합니다. LLM 없이 retrieval 결과만 확인하려면 아래 옵션을 사용합니다.

```powershell
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?" --no-generate
```

LM Studio를 켜서 자연어 답변 생성을 붙일 때는 `.env` 또는 PowerShell 환경변수로 모델명을 지정합니다.

```powershell
$env:LM_STUDIO_MODEL="qwen2.5-7b-instruct"
python -m rag.langchain_pipeline "졸업 이수학점이 어떻게 되나요?"
```

## 작은 평가 실행

```powershell
python -m rag.retrieval_eval --query-file test_queries.json --top-k 3 --threshold 0.8 --limit 10
```

## 여러 설정 자동 비교

`top_k`와 `threshold` 후보를 한 번에 비교하려면 아래 명령을 사용합니다.

```powershell
python -m rag.retrieval_sweep --query-file test_queries.json --top-ks 3,5 --thresholds 0.7,0.75,0.8,0.85 --limit 10 --sample-mode even --output-dir outputs/retrieval_sweep_test
```

`--sample-mode even`은 평가셋 앞쪽 10개만 쓰지 않고 전체 평가셋에서 고르게 10개를 뽑습니다. 모델 첫 로딩 시간이 평균 지연에 섞이지 않도록 warmup은 기본으로 실행됩니다.

전체 50개 평가셋을 돌릴 때는 `--limit`을 빼고 실행합니다.

```powershell
python -m rag.retrieval_sweep --query-file test_queries.json --top-ks 3,5 --thresholds 0.7,0.75,0.8,0.85 --output-dir outputs/retrieval_sweep_full
```

생성되는 파일:

| 파일 | 내용 |
| --- | --- |
| `retrieval_sweep_summary.md` | 회의 공유용 요약 표 |
| `retrieval_sweep_summary.csv` | 엑셀/스프레드시트용 요약 표 |
| `retrieval_sweep_results.json` | 질문별 상세 결과 포함 전체 로그 |

## 다음 최적화 지점

- `threshold`: 0.70, 0.75, 0.80, 0.85 후보 비교
- `top_k`: 3, 5 후보 비교
- `chunk_size`: 기존 값 기준으로 필요 시 1000, 1500, 2000 비교
- `source metadata`: 웹에서 클릭 가능한 `title`, `url`, `doc_id` 유지

## chunk_size / chunk_overlap 자동 비교

`top_k=5`, `threshold=0.75`를 고정하고 chunk 설정만 비교합니다.

| preset | chunk_size | chunk_overlap |
| --- | --- | --- |
| A | 1000 | 100 |
| B | 1500 | 150 |
| C | 2000 | 200 |

```powershell
python -m rag.chunk_sweep --presets A,B,C --top-k 5 --threshold 0.75 --output-dir outputs/chunk_sweep
```

생성되는 파일:

| 파일 | 내용 |
| --- | --- |
| `chunk_sweep_summary.md` | 회의 공유용 요약 표 |
| `chunk_sweep_summary.csv` | 엑셀/스프레드시트용 요약 표 |
| `chunk_sweep_results.json` | 전체 결과 JSON |

## QA top_k / document top_k 분리 비교

이미 만들어진 Qdrant 인덱스를 그대로 사용하므로 재임베딩은 필요 없습니다.

```powershell
python -m rag.split_topk_sweep --pairs 3:5,5:5,3:7 --threshold 0.75 --output-dir outputs/split_topk_sweep
```

| pair | 의미 |
| --- | --- |
| `3:5` | QA 캐시는 3개 검색, 문서는 5개 검색 |
| `5:5` | QA 캐시와 문서 모두 5개 검색 |
| `3:7` | QA 캐시는 3개 검색, 문서는 7개 검색 |
