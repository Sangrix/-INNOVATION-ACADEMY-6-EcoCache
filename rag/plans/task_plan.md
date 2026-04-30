# EcoCache RAG 아키텍처 분리 + 베이스라인 2개 구현 계획

## Goal
현재 `embed_pipeline.py` + `query.py` 단일 구조를:
1. **임베딩 파이프라인** (embed_pipeline.py — 공통, 변경 최소)
2. **쿼리 추론 아키텍처** (Baseline 1 Pure RAG / Baseline 2 Semantic Cache)
로 명확하게 분리하고, 두 베이스라인을 비교할 수 있도록 구현한다.

## Current Phase
모든 Phase 완료 ✓

## 기존 완료 Phases (Phase 1~6)
| # | 이름 | 상태 |
|---|------|------|
| 1 | 프로젝트 구조 설정 | complete ✓ |
| 2 | Qdrant 초기화 확인 | complete ✓ |
| 3 | 데이터 로더 및 전처리 | complete ✓ |
| 4 | 임베딩 파이프라인 구현 | complete ✓ |
| 5 | 쿼리 인터페이스 구현 | complete ✓ |
| 6 | 검증 실행 | complete ✓ |

## 신규 Phases (아키텍처 분리 + 베이스라인)

| # | 이름 | 상태 | 결과물 |
|---|------|------|--------|
| 7 | Retriever Base 추출 | complete ✓ | `retriever_base.py` — 공통 모델 싱글턴·search() |
| 8 | Baseline 1: Pure RAG | complete ✓ | `baseline_pure_rag.py` — documents만 검색 |
| 9 | Baseline 2: Semantic Cache RAG | complete ✓ | `baseline_semantic_cache.py` — qa_pairs→documents fallback |
| 10 | query.py CLI 통합 | complete ✓ | `--mode pure_rag\|semantic_cache` 플래그 추가 |
| 11 | run_eval.py 두 베이스라인 비교 | complete ✓ | `--mode` 옵션으로 baseline 선택 평가 지원 |
| 12 | eval_dashboard.py 비교 뷰 | complete ✓ | 두 JSONL 동시 로드·모드별 쿼리 비교 탭 추가 |

## 목표 파일 구조

```
EcoCache/
├── embed_pipeline.py          ← 임베딩 파이프라인 (공통 — 거의 변경 없음)
├── retriever_base.py          ← 공통: 모델 로더, Qdrant 클라이언트, search()
├── baseline_pure_rag.py       ← Baseline 1: documents 컬렉션만 벡터 검색
├── baseline_semantic_cache.py ← Baseline 2: qa_pairs 우선 → threshold 미달 시 documents fallback
├── query.py                   ← CLI 진입점 (--mode 선택)
├── run_eval.py                ← 두 baseline 비교 평가 (--mode 옵션)
└── eval_dashboard.py          ← 대시보드 (비교 탭 추가)
```

## 아키텍처 설계

### 공통 인터페이스
```python
# retriever_base.py
class BaseRetriever:
    def retrieve(self, query: str, filters=None, top_k=5) -> dict:
        """
        반환 형식 (두 baseline 공통):
        {
            "source": "documents" | "qa_pairs",
            "results": [{"score": float, "payload": dict}, ...],
            "query": str,
            "qa_top1_score": float | None,
        }
        """
```

### Baseline 1 — Pure RAG
```python
# baseline_pure_rag.py
class PureRAGRetriever(BaseRetriever):
    # documents 컬렉션만 검색
    # qa_pairs 미사용
```

### Baseline 2 — Semantic Cache RAG
```python
# baseline_semantic_cache.py
class SemanticCacheRetriever(BaseRetriever):
    # qa_pairs 먼저 검색 → score >= threshold → 캐시 히트
    # threshold 미달 → documents fallback
```

## Key Decisions

- **공통 모델·클라이언트**: `retriever_base.py`에서 싱글턴 관리 (query.py에서 이동)
- **embed_pipeline.py**: Qdrant 적재 로직만 유지, 쿼리 관련 코드 없음
- **query.py**: 얇은 CLI 래퍼 — retriever 선택 후 `retriever.retrieve()` 호출
- **run_eval.py**: `--mode` 플래그로 baseline 선택, 기존 평가 로직 재사용
- **반환 dict 형식 통일**: `source`, `results`, `query`, `qa_top1_score` 키 유지 (eval_dashboard 호환)

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `CollectionInfo` has no attribute `vectors_count` | 1 | `points_count`로 교체 |
| `qa_pairs` 포인트 수 불일치 | 1 | qa_id 중복 수정 |
| `QdrantClient` has no attribute `search` | 1 | `query_points()`로 교체 |
