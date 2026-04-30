# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

EcoCache는 인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 구조화된 JSON 데이터셋으로 변환하고,
RAG(검색 증강 생성) 기반 학생 Q&A 챗봇의 지식 베이스로 활용하는 프로젝트입니다.
문서 파싱·OCR에는 Upstage Document AI가 사용됩니다.

임베딩 파이프라인과 쿼리 추론이 명확히 분리되어 있으며,
두 가지 검색 Baseline(Pure RAG / Semantic Cache RAG)을 비교할 수 있습니다.

## 디렉토리 구조

```
EcoCache/
├── CLAUDE.md
├── .gitignore
├── .env                        ← 환경변수 (git 미포함)
├── test_queries.json           ← 25개 평가 질문 세트
│
├── rag/                        ← RAG 파이프라인 소스 코드
│   ├── config.py               ← 모든 설정 상수
│   ├── embed_pipeline.py       ← 임베딩 파이프라인 (공통)
│   ├── retriever_base.py       ← 공통: 모델·클라이언트 싱글턴, search(), BaseRetriever
│   ├── baseline_pure_rag.py    ← Baseline 1: documents만 검색
│   ├── baseline_semantic_cache.py ← Baseline 2: qa_pairs → documents fallback
│   ├── query.py                ← CLI 진입점 (--mode 선택)
│   ├── run_eval.py             ← 배치 평가 (--mode 선택)
│   ├── eval_dashboard.py       ← Streamlit 대시보드
│   ├── requirements.txt
│   │
│   ├── logs/                   ← 평가 로그 (git 미포함)
│   │   ├── eval_log.jsonl
│   │   ├── eval_pure_rag.jsonl
│   │   └── eval_semantic_cache.jsonl
│   │
│   └── plans/                  ← 기획·명세 문서
│       ├── task_plan.md
│       ├── findings.md
│       ├── progress.md
│       ├── spec.md
│       └── spec_llm.md
│
├── sw_upstage_output/          ← 배치 1: 2026년 최신 공지
├── sw_upstage_output_2/        ← 배치 2: 2025년 11월 공지
├── sw_upstage_output_3/        ← 배치 3: 2025년 12월~2026년 초
├── pr_data/                    ← 외부홍보 게시물
└── qdrant_data/                ← Qdrant 로컬 저장소 (git 미포함)
```

## 아키텍처

### 공통 임베딩 파이프라인 (`embed_pipeline.py`)

데이터 로딩 → 청킹 → BGE-m3-ko 임베딩 → Qdrant 업서트.
두 Baseline이 동일한 Qdrant 컬렉션(`documents`, `qa_pairs`)을 공유합니다.

### Baseline 1 — Pure RAG (`baseline_pure_rag.py`)

`documents` 컬렉션만 검색하는 순수 벡터 검색 베이스라인.
`qa_pairs`를 참조하지 않으며 항상 `"source": "documents"`를 반환합니다.

### Baseline 2 — Semantic Cache RAG (`baseline_semantic_cache.py`)

`qa_pairs` 먼저 검색(시맨틱 캐시) → top-1 유사도 ≥ `QA_SIMILARITY_THRESHOLD`(0.75)이면 반환.
임계값 미달 시 `documents` fallback.

### 공통 Retriever 인터페이스 (`retriever_base.py`)

```python
class BaseRetriever(ABC):
    def retrieve(self, query: str, filters=None, top_k=5) -> dict:
        # 반환 형식 (두 Baseline 공통):
        # { "source": "qa_pairs"|"documents",
        #   "results": [{"score": float, "payload": dict}, ...],
        #   "query": str, "qa_top1_score": float|None }
```

모델 싱글턴(`get_model`), 클라이언트 싱글턴(`get_client`), `search()`, `build_filter()`도 여기서 관리합니다.

## 주요 설정 (`rag/config.py`)

| 설정 | 값 | 설명 |
|------|-----|------|
| `EMBED_MODEL_ID` | `dragonkue/BGE-m3-ko` | 한국어 특화 임베딩 모델 (1024차원) |
| `EMBED_BATCH_SIZE` | `8` | CPU 기본값; GPU는 32 권장 |
| `CHUNK_THRESHOLD` | `2000` | 이 이하 문서는 단일 청크 |
| `CHUNK_SIZE` | `1500` | 청크 크기 (문자 수) |
| `CHUNK_OVERLAP` | `150` | 청크 오버랩 |
| `COLLECTION_DOCS` | `documents` | 문서 청크 컬렉션 |
| `COLLECTION_QA` | `qa_pairs` | QA 페어 컬렉션 |
| `QA_SIMILARITY_THRESHOLD` | `0.75` | Semantic Cache 히트 기준 |
| `TOP_K` | `5` | 검색 반환 수 |
| `LM_STUDIO_URL` | `.env` 또는 자동 감지 | WSL2 환경에서 Windows 호스트 IP 자동 교체 |

## CLI 사용법

모든 명령은 `rag/` 디렉토리에서 실행합니다.

```bash
cd rag/

# 임베딩 파이프라인 (최초 1회)
python embed_pipeline.py

# 검색 쿼리
python query.py "질문" --mode pure_rag
python query.py "질문" --mode semantic_cache   # 기본값
python query.py "질문" --generate              # LM Studio 답변 생성
python query.py "질문" --log --log-file logs/my.jsonl

# 배치 평가
python run_eval.py --mode pure_rag       --log-file logs/eval_pure_rag.jsonl
python run_eval.py --mode semantic_cache --log-file logs/eval_semantic_cache.jsonl
python run_eval.py --summary-only --log-file logs/eval_pure_rag.jsonl

# 대시보드
streamlit run eval_dashboard.py
```

## 데이터 구조

### 문서(Document) 스키마

```json
{
  "doc_id": "inha_notice_001",
  "source": {
    "board_type": "notice | pr",
    "board_name": "공지사항 | 외부홍보",
    "url": "https://swuniv.inha.ac.kr/..."
  },
  "meta": {
    "title": "공지 제목",
    "published_at": "YYYY-MM-DD",
    "attachments": [{ "filename": "...", "url": "..." }]
  },
  "content": {
    "raw_text": "본문 전체 텍스트 (이미지 OCR 결과 포함)"
  }
}
```

### QA 페어 스키마

```json
{
  "qa_id": "inha_notice_qa_001",
  "source_doc_id": "inha_notice_001",
  "question": { "text": "질문 텍스트" },
  "answer": {
    "text": "답변 텍스트",
    "reference_url": "https://swuniv.inha.ac.kr/..."
  }
}
```

## 데이터 배치 구조

| 폴더 | 문서 파일 | QA 파일 | 기간/범위 |
|------|-----------|---------|-----------|
| `sw_upstage_output/` | `inha_notice_data.json` | `inha_notice_qa.json` | 2026년 최신 공지 (inha_notice_001~) |
| `sw_upstage_output_2/` | `inha_sw_notice_157275_to_166292.json` | `inha_sw_notice_qa_157275_to_166292.json` | 2025년 11월 공지 (게시글 ID 기준) |
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` | 2025년 12월~2026년 초 (inha_notice_093~) |
| `pr_data/` | `inha_pr.json` | `inha_pr_qa.json` | 외부홍보 게시판 (inha_pr_001~) |

### doc_id 명명 규칙

- `inha_notice_NNN` — 순번 기반 (sw_upstage_output, sw_upstage_output_3)
- `inha_sw_notice_NNNNNN` — 원본 게시글 ID 기반 (sw_upstage_output_2)
- `inha_pr_NNN` — 외부홍보 게시물 순번 기반 (pr_data)

## 새 데이터 추가 시 유의사항

- 배치 폴더명 규칙: `sw_upstage_output_N/` (N은 순번)
- QA 파일의 `source_doc_id`는 같은 배치의 문서 `doc_id`와 반드시 일치해야 합니다
- `doc_id`와 `qa_id`는 전체 데이터셋 내에서 고유해야 합니다
- `raw_text`에 이미지 OCR 결과가 포함된 경우 `[첨부 이미지 OCR N]` 레이블이 붙습니다
- 새 배치 추가 후 `embed_pipeline.py` 재실행 필요 (upsert 방식이므로 기존 데이터 유지)

## 평가 로그 형식 (`logs/*.jsonl`)

한 쿼리 = 한 줄 JSONL. `config.mode` 필드로 어떤 Baseline으로 실행됐는지 구분합니다.

```json
{
  "timestamp": "2026-04-30T...",
  "config": { "mode": "pure_rag", "embed_model": "...", "qa_similarity_threshold": 0.75, ... },
  "query": "질문 텍스트",
  "source": "documents",
  "qa_top1_score": 0.6123,
  "results": [{ "rank": 1, "score": 0.8234, "doc_id": "...", "title": "...", ... }]
}
```
