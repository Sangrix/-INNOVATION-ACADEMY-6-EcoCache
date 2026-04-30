# Findings — EcoCache RAG 파이프라인

## 데이터셋 현황 (탐색 완료)

- 총 문서: 136개 / 총 QA: 136개 (4개 배치)
- raw_text: 최솟값 0자, 중앙값 806자, 평균 1,080자, 최댓값 5,929자
- 2,000자 초과 문서: 21개 (15%) → 청킹 필요
- 빈 raw_text 문서 존재 (최솟값 0자) → 빈 문서 처리 정책 적용 필요

## 모델 정보 (dragonkue/BGE-m3-ko)

- 파라미터: 0.6B / 텐서: F32 → 모델 크기 ~2.27GB
- 최대 시퀀스: 8,192 토큰 → 5,929자 최장 문서도 안전 (≈8,894토큰 경계선)
- Korean AutoRAG 벤치마크 F1: 0.7456 (1위)
- 노트북 CPU 환경: 가능 (RAM 8GB+), batch_size=8 권장
- GPU 환경: batch_size=16~32, float16 사용 시 메모리 절반

## 스크립트 구조 결정

```
EcoCache/
├── spec.md
├── .env
├── config.py
├── embed_pipeline.py
├── query.py
└── requirements.txt
```

## 청킹 전략

- `langchain_text_splitters.RecursiveCharacterTextSplitter` 사용
- separators: ["\n\n", "\n", "。", "."]
- chunk_size=1500 (문자), chunk_overlap=150 (문자)
- 2,000자 이하 문서: 분리자 없이 단일 청크

## 포인트 ID 전략

- `uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{chunk_index}")` 고정 UUID
- 재실행 시 동일 ID → Qdrant upsert 자동 덮어쓰기

## Qdrant 주의사항

- Docker 실행 시 반드시 볼륨 마운트 필요 (`-v $(pwd)/qdrant_data:/qdrant/storage`)
- 컬렉션 벡터 차원: 1024 (BGE-m3-ko 출력)
- 유사도 함수: COSINE

## 아키텍처 분리 설계 (Session 3)

### 현재 query.py 분리 대상 코드
- `get_model()`, `get_client()` → `retriever_base.py`로 이동
- `search()`, `build_filter()` → `retriever_base.py`로 이동
- `rag_search()` → 두 baseline으로 분리:
  - `baseline_pure_rag.py`: documents만 검색
  - `baseline_semantic_cache.py`: qa_pairs → documents fallback
- `generate_answer()`, `log_result()`, `print_results()` → query.py 유지 (표현 계층)

### 공통 반환 dict 형식 (eval_dashboard 호환)
```python
{
    "source": "documents" | "qa_pairs",
    "results": [{"score": float, "payload": dict}, ...],
    "query": str,
    "qa_top1_score": float | None,
}
```

### 두 Baseline 차이점
| | Pure RAG | Semantic Cache RAG |
|---|---|---|
| qa_pairs 검색 | 없음 | 항상 먼저 시도 |
| fallback | 없음 (documents만) | threshold 미달 시 documents |
| 용도 | 순수 벡터 검색 베이스라인 | 캐시 효과 측정 |
| source 반환값 | 항상 "documents" | "qa_pairs" 또는 "documents" |
