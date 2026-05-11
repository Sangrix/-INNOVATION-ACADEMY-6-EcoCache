# EcoCache RAG API

## 사전 조건

Qdrant가 실행 중이고 임베딩 파이프라인이 완료되어 있어야 합니다.

```bash
# Qdrant가 아직 실행 중이 아니라면
docker run -d -p 6333:6333 \
  -v "$(pwd)/qdrant_data:/qdrant/storage" \
  qdrant/qdrant

# 임베딩 파이프라인 (최초 1회)
cd rag/
python embed_pipeline.py
```

## 설치 및 실행

```bash
# 의존성 설치 (루트 requirements + api requirements)
pip install -r requirements.txt
pip install -r api/requirements.txt

# API 서버 실행
cd api/
uvicorn main:app --reload --port 8000
```

## 엔드포인트

### `POST /chat`

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "졸업학점 알려줘"}' | python3 -m json.tool
```

**응답 예시:**

```json
{
    "success": true,
    "error": null,
    "result": {
        "response": "졸업에 필요한 학점은 ...",
        "similarity": 0.8231,
        "cache_hit": false,
        "latency": 1843.5,
        "co2_grams": null,
        "ci_g_per_kwh": 385.0,
        "sources": ["inha_notice_008", "inha_notice_013"]
    }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `response` | string \| null | LLM 생성 답변 (LM Studio 미연결 시 null) |
| `similarity` | float \| null | rank-1 결과의 코사인 유사도 |
| `cache_hit` | bool | qa_pairs 캐시 히트 여부 |
| `latency` | float | 검색 소요 시간 (ms) |
| `co2_grams` | null | 탄소 측정 미통합 (예정) |
| `ci_g_per_kwh` | float \| null | 현재 한국 탄소 집약도 (시간대별 정적값) |
| `sources` | string[] | 반환된 문서의 doc_id 목록 |

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## LLM 답변 활성화

LM Studio에서 모델을 로드하고 Local Server를 시작한 뒤, `.env`에 모델명을 설정합니다.

```dotenv
LM_STUDIO_MODEL=EEVE-Korean-10.8B-v1.0
```

모델명이 비어 있으면 `response` 필드가 `null`로 반환되고 나머지 필드는 정상 동작합니다.

## 자동 문서 (Swagger UI)

서버 실행 후 브라우저에서 확인:

```
http://localhost:8000/docs
```
