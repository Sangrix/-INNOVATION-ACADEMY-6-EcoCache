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

### 다음 작업 (Phase 6: 검증)
- [ ] Docker로 Qdrant 실행: `docker run -p 6333:6333 -v $(pwd)/qdrant_data:/qdrant/storage qdrant/qdrant`
- [ ] 패키지 설치: `pip install -r requirements.txt`
- [ ] 파이프라인 실행: `python embed_pipeline.py`
- [ ] 벡터 수 확인: documents ≥ 136, qa_pairs == 136
- [ ] 샘플 쿼리 5개 테스트: `python query.py "i-PAC 콘테스트 신청 기간"`

### 메모
- 노트북 CPU 환경 고려: EMBED_BATCH_SIZE=8 기본값 검토 필요
- 최장 문서 5,929자 ≈ 8,894 토큰 — BGE-m3-ko 8,192 한도 근접, 청킹으로 안전 처리
