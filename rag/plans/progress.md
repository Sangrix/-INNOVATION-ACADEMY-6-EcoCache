# Progress Log — EcoCache RAG 파이프라인

## Session 1 — 2026-04-23

### 완료 작업
- [x] spec.md 작성 및 /spec-review 검토 완료
- [x] 임베딩 모델 변경: Solar → dragonkue/BGE-m3-ko
- [x] task_plan.md, findings.md, progress.md 생성

### 완료된 작업 (세션 1)
- [x] Phase 1: requirements.txt, .env, config.py 생성
- [x] Phase 2: init_collections() — Qdrant 컬렉션 자동 생성 로직 포함
- [x] Phase 3: embed_pipeline.py — 로더, 빈 문서 정책, 청킹 구현
- [x] Phase 4: embed_pipeline.py — BGE-m3-ko 임베딩 + upsert 완성
- [x] Phase 5: query.py — rag_search() + CLI 인터페이스

### 완료된 작업 (세션 2 — Phase 6: 검증)
- [x] Qdrant Docker 실행 (사용자 완료)
- [x] 패키지 설치 (사용자 완료)
- [x] `embed_pipeline.py` `vectors_count` → `points_count` 버그 수정
- [x] `sw_upstage_output_2` QA qa_id 중복 수정 (31건 재정의)
- [x] `query.py` `client.search()` → `client.query_points()` 버그 수정
- [x] 파이프라인 실행 성공: documents 189포인트, qa_pairs 136포인트
- [x] 검증 통과 (assert 모두 통과)
- [x] 샘플 쿼리 5개 정상 응답 확인

### 최종 상태
- 모든 6개 Phase 완료 ✓
- GPU(cuda) 환경에서 실행, 임베딩 성능 양호
- RAG 검색 정상 작동 확인

---

## Session 3 — 2026-04-30

### 목표
- RAG 아키텍처를 임베딩 파이프라인 / 쿼리 추론으로 분리
- Baseline 1 (Pure RAG) + Baseline 2 (Semantic Cache RAG) 구현

### 완료된 작업
- [x] Phase 7: retriever_base.py 생성 — get_model, get_client, search, build_filter, BaseRetriever
- [x] Phase 8: baseline_pure_rag.py — PureRAGRetriever (documents만)
- [x] Phase 9: baseline_semantic_cache.py — SemanticCacheRetriever (qa_pairs → documents)
- [x] Phase 10: query.py — get_retriever() 팩토리, --mode 플래그, 기존 log/generate 유지
- [x] Phase 11: run_eval.py — --mode 옵션, mode 필드 로그 기록, 요약 분리
- [x] Phase 12: eval_dashboard.py — 사이드바 2번째 로그, Tab 4 모드별 비교·산점도·쿼리별 차이 테이블

### 최종 상태
- 모든 Phase 7~12 완료 ✓
- 문법 검사 통과 (6개 파일)
- 임포트 연결 테스트 통과
