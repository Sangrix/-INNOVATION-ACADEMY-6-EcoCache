# EcoCache LLM 연결 명세 (LM Studio)

## 아키텍처

```
질문
 └─► rag_search()          ← Qdrant 벡터 검색 (qa_pairs → fallback → documents)
       └─► _build_context()  ← 검색 결과를 프롬프트 컨텍스트로 조립
             └─► generate_answer()  ← LM Studio OpenAI-호환 API 호출
                   └─► 자연어 답변 반환
```

## LM Studio 설정

| 항목 | 값 |
|------|----|
| 기본 URL | `http://localhost:1234/v1` |
| api_key | `"lm-studio"` (인증 없음, 임의 문자열) |
| 권장 모델 | EEVE-Korean-10.8B, Qwen2.5-7B-Instruct, gemma-3-12b-it |

**절차**
1. LM Studio에서 원하는 모델 로드
2. 상단 메뉴 **Local Server → Start Server** 클릭
3. `.env`에 아래 변수 설정

```
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=<LM Studio에서 로드한 모델명>
```

> `LM_STUDIO_MODEL`이 비어 있으면 `generate_answer()` 호출 시 `ValueError`가 발생합니다.

## 시스템 프롬프트

```
당신은 인하대학교 SW중심대학사업단 공지사항 안내 도우미입니다.
아래 참고 문서를 바탕으로 질문에 간결하고 정확하게 답하세요.
참고 문서에 없는 내용은 "해당 정보를 찾을 수 없습니다"라고 답하세요.
```

## 컨텍스트 조립 규칙

| 검색 출처 | 포맷 |
|-----------|------|
| `qa_pairs` | `Q: {question}\nA: {answer}` |
| `documents` | `[{title} / {published_at}]\n{text}` (text는 최대 `LM_CONTEXT_LIMIT ÷ 결과 수` 자) |

- rank 1~3 결과를 `"\n\n---\n\n"`으로 연결
- 컨텍스트 총 길이 상한: **2000자** (`LM_CONTEXT_LIMIT`)

## API 호출 파라미터

| 파라미터 | 값 | 이유 |
|----------|----|------|
| `temperature` | 0.3 | 사실 기반 답변 — 낮게 |
| `max_tokens` | 512 | 간결한 답변 목표 |
| `stream` | False | 기본값 |

## 환경변수 (.env)

```dotenv
# Qdrant (기존)
QDRANT_URL=http://localhost:6333

# LM Studio (신규)
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=EEVE-Korean-10.8B-v1.0
```

## CLI 사용법

```bash
# 벡터 검색 결과만 출력 (기존)
python query.py "i-PAC 콘테스트 신청 기간"

# 벡터 검색 + LLM 답변 생성
python query.py "i-PAC 콘테스트 신청 기간" --generate

# 생성 + 로그 기록
python query.py "i-PAC 콘테스트 신청 기간" --generate --log

# 필터 + 생성
python query.py "신청 기간" --board_type notice --generate
```

## 검증 절차

1. LM Studio에서 모델 로드 → Local Server 시작
2. `.env`에 `LM_STUDIO_MODEL=<모델명>` 입력
3. `python query.py "i-PAC 콘테스트 신청 기간" --generate` 실행
4. 벡터 검색 결과 + 자연어 답변이 순서대로 출력되는지 확인
5. 존재하지 않는 주제 (`"기숙사 신청"`) 로 실행 → "해당 정보를 찾을 수 없습니다" 응답 확인

## 관련 파일

| 파일 | 역할 |
|------|------|
| `config.py` | LM Studio URL·모델명·시스템 프롬프트 상수 |
| `query.py` | `_build_context()`, `generate_answer()`, `--generate` CLI 플래그 |
| `requirements.txt` | `openai>=1.0.0` 의존성 |
| `.env` | 런타임 환경변수 (LM_STUDIO_URL, LM_STUDIO_MODEL) |
