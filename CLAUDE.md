# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

EcoCache는 인하대학교 SW중심대학사업단 공지사항·홍보 게시물을 구조화된 JSON 데이터셋으로 변환하는 프로젝트입니다. 수집된 데이터는 RAG(검색 증강 생성) 기반 학생 Q&A 챗봇의 지식 베이스로 활용하는 것을 목적으로 합니다. 문서 파싱·OCR에는 Upstage Document AI가 사용됩니다.

## 데이터 구조

### 문서(Document) 스키마

모든 문서 파일(`*_notice_data*.json`, `inha_pr.json`)은 동일한 구조를 따릅니다:

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

모든 QA 파일(`*_qa*.json`, `inha_pr_qa.json`)은 동일한 구조를 따릅니다:

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
| `sw_upstage_output_3/` | `inha_notice_data3.json` | `swuniv_notice_qa3.json` | 2025년 12월~2026년 초 공지 (inha_notice_093~) |
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
