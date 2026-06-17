import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))

from main import _extract_sources

# Qdrant payloads are flat (see embed_pipeline.py):
# documents:  {doc_id, title, url, board_type, board_name, ...}
# QA pairs:   {qa_id, question, answer, reference_url, ...}


def test_document_hit_returns_url_and_title():
    result = {
        "results": [{
            "score": 0.9,
            "payload": {
                "doc_id": "inha_notice_001",
                "title":  "공지사항 제목",
                "url":    "https://swuniv.inha.ac.kr/page1",
            },
        }]
    }
    assert _extract_sources(result) == [
        {"url": "https://swuniv.inha.ac.kr/page1", "title": "공지사항 제목"}
    ]


def test_qa_hit_returns_reference_url_with_fallback_title():
    result = {
        "results": [{
            "score": 0.91,
            "payload": {
                "qa_id":         "inha_notice_qa_001",
                "question":      "신청 기간은 언제인가요?",
                "answer":        "4월 28일까지입니다.",
                "reference_url": "https://swuniv.inha.ac.kr/page1",
            },
        }]
    }
    assert _extract_sources(result) == [
        {"url": "https://swuniv.inha.ac.kr/page1", "title": "원문 보기"}
    ]


def test_deduplicates_by_url():
    result = {
        "results": [
            {"score": 0.9, "payload": {"title": "A", "url": "https://a.com"}},
            {"score": 0.8, "payload": {"title": "A", "url": "https://a.com"}},
        ]
    }
    assert len(_extract_sources(result)) == 1


def test_skips_results_without_url():
    result = {
        "results": [{
            "score": 0.9,
            "payload": {"doc_id": "d1", "title": "T"},
        }]
    }
    assert _extract_sources(result) == []


def test_qa_hit_with_empty_reference_url_is_skipped():
    result = {
        "results": [{
            "score": 0.88,
            "payload": {
                "qa_id":         "inha_notice_qa_002",
                "answer":        "답변 텍스트",
                "reference_url": "",
            },
        }]
    }
    assert _extract_sources(result) == []


def test_empty_results_returns_empty_list():
    assert _extract_sources({"results": []}) == []
