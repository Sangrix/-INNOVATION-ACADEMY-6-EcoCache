# Progress — 희승: RAG API 베이스라인 + 출처 표시

## 세션 로그

### 2026-05-11 — 플래닝 세션

**완료:**
- 기존 코드베이스 파악 (`rag/` 디렉토리 구조, 재사용 가능 컴포넌트 목록화)
- `task_plan.md`, `findings.md`, `progress.md` 생성
- Phase 1~4 범위 및 기술 스택 결정 (FastAPI + Qdrant 재사용)
- 응답 JSON 초안 스키마 도출

**블로커:**
- "위 스키마" 원본 문서 미확인 → 사용자 확인 필요
- 학사정보 원본 파일 위치·형식 미확인 → 사용자 확인 필요

**다음 세션 시작 전 확인할 것:**
1. "위 스키마" 문서 공유
2. 학사정보 데이터 파일 경로 안내
3. 위 두 가지 확인 후 Phase 1(ingestion) 즉시 착수 가능

---

### 2026-05-11 — 구현 세션

**확인된 사항:**
- "위 스키마" = `{success, error, result: {response, similarity, cache_hit, latency, co2_grams, ci_g_per_kwh, sources}}`
- ingestion SKIP — 기존 Qdrant 컬렉션(`documents`, `qa_pairs`) 재사용
- python3.10 환경 사용 (패키지: `~/.local/lib/python3.10/site-packages/`)

**생성된 파일:**
- `api/schemas.py` — Pydantic ChatRequest / ChatResult / ChatResponse
- `api/main.py` — FastAPI 앱, lifespan으로 모델 사전 로드, `/chat` + `/health`
- `api/requirements.txt` — fastapi>=0.111.0, uvicorn[standard]>=0.29.0
- `api/README.md` — curl 예제 + 필드 설명 + LM Studio 활성화 방법

**검증:**
- python3.10 구문 검사 통과
- schemas 필드 직렬화 검증 완료
- fastapi + uvicorn 설치 확인 (fastapi 0.136.1 / uvicorn 0.46.0)

**남은 작업:**
- Qdrant 실행 후 `curl localhost:8000/chat -d '{"query":"졸업학점 알려줘"}'` 실제 호출 검증

---

## 현재 Phase 상태

| Phase | 상태 | 메모 |
|-------|------|------|
| Phase 1 — Ingestion 스크립트 | SKIP | 기존 Qdrant 데이터 재사용 |
| Phase 2 — FastAPI /chat | **완료** | `api/main.py` |
| Phase 3 — 스키마 전 필드 확보 | **완료** | `api/schemas.py` |
| Phase 4 — README | **완료** | `api/README.md` |
| 검증 — curl 테스트 | **완료** | success:true, 스키마 전 필드 정상 반환 |
