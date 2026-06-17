import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))

from main import _extract_sources


def test_document_hit_returns_url_and_title():
    result = {
        "results": [{
            "score": 0.9,
            "payload": {
                "doc_id": "inha_notice_001",
                "source": {"url": "https://swuniv.inha.ac.kr/page1"},
                "meta":   {"title": "공지사항 제목"},
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
                "qa_id":  "inha_notice_qa_001",
                "answer": {"text": "답변", "reference_url": "https://swuniv.inha.ac.kr/page1"},
            },
        }]
    }
    assert _extract_sources(result) == [
        {"url": "https://swuniv.inha.ac.kr/page1", "title": "원문 보기"}
    ]


def test_deduplicates_by_url():
    result = {
        "results": [
            {"score": 0.9, "payload": {"source": {"url": "https://a.com"}, "meta": {"title": "A"}}},
            {"score": 0.8, "payload": {"source": {"url": "https://a.com"}, "meta": {"title": "A"}}},
        ]
    }
    assert len(_extract_sources(result)) == 1


def test_skips_results_without_url():
    result = {
        "results": [{
            "score": 0.9,
            "payload": {"doc_id": "d1", "source": {}, "meta": {"title": "T"}},
        }]
    }
    assert _extract_sources(result) == []


def test_empty_results_returns_empty_list():
    assert _extract_sources({"results": []}) == []
