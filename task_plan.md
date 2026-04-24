# EcoCache RAG 임베딩 파이프라인 구축 계획

## Goal
spec.md 기반으로 인하대 SW중심대학 공지사항·외부홍보 136개 문서 + 136개 QA 페어를
dragonkue/BGE-m3-ko 모델로 임베딩하여 Qdrant 벡터 DB에 적재하는 파이프라인을 구축한다.

## Current Phase
모든 Phase 완료 ✓

## Phases

| # | 이름 | 상태 | 결과물 |
|---|------|------|--------|
| 1 | 프로젝트 구조 설정 | complete | `requirements.txt`, `.env`, `config.py` ✓ |
| 2 | Qdrant 초기화 확인 | complete | `init_collections()` in `embed_pipeline.py` ✓ |
| 3 | 데이터 로더 및 전처리 | complete | `load_all_docs/qas()`, `prepare_doc_chunks()` ✓ |
| 4 | 임베딩 파이프라인 구현 | complete | `embed_pipeline.py` 완성 ✓ |
| 5 | 쿼리 인터페이스 구현 | complete | `query.py` (CLI + `rag_search()`) ✓ |
| 6 | 검증 실행 | complete | documents 189, qa_pairs 136 — 검증 통과 ✓ |

## Key Decisions (spec.md 기반)

- **임베딩 모델**: `dragonkue/BGE-m3-ko` (로컬, 1024차원, 8192토큰)
- **벡터 DB**: Qdrant (size=1024, Distance.COSINE)
- **컬렉션**: `documents` / `qa_pairs` 분리
- **청킹**: 문자 수 기준, THRESHOLD=2000 / SIZE=1500 / OVERLAP=150
- **포인트 ID**: `uuid5(NAMESPACE_DNS, "{doc_id}_{chunk_index}")`
- **빈 문서**: 첨부파일명 fallback → 없으면 제목만 + WARN 로그
- **배치 크기**: 기본 32 (CPU 환경에서는 8로 줄이기)
- **재실행**: upsert 덮어쓰기 (OPEN ITEM: 고아 포인트 잔류)

## 입력 데이터 경로

| 경로 | 문서 파일 | QA 파일 |
|------|-----------|---------|
| `sw_upstage_output/` | `inha_notice_data.json` | `inha_notice_qa.json` |
| `sw_upstage_output_2/` | `inha_sw_notice_157275_to_166292.json` | `inha_sw_notice_qa_157275_to_166292.json` |
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` |
| `pr_data/` | `inha_pr.json` | `inha_pr_qa.json` |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `CollectionInfo` has no attribute `vectors_count` | 1 | `points_count`로 교체 (Qdrant 신버전 API 변경) |
| `qa_pairs` 포인트 수 105/136 불일치 | 1 | `sw_upstage_output_2` QA 파일 `qa_id` 중복 수정 (`inha_notice_qa_` → `inha_sw_notice_qa_`) |
| `QdrantClient` has no attribute `search` | 1 | `query_points()`로 교체 (Qdrant 신버전 API 변경) |
