import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch, mock_open, MagicMock
import json
import urllib.request
import urllib.error

MOCK_QA = [
    {
        "qa_id": f"qa_{i:03d}",
        "source_doc_id": f"doc_{i:03d}",
        "question": {"text": f"질문 {i}"},
        "answer": {"text": f"답변 {i}", "reference_url": "https://example.com"},
    }
    for i in range(10)
]


def test_load_qa_batches_returns_20_items():
    import generate_report
    mock_data = json.dumps(MOCK_QA)
    with patch("builtins.open", mock_open(read_data=mock_data)):
        batches = generate_report.load_qa_batches()
    assert len(batches) == 20


def test_load_qa_batches_each_item_has_required_fields():
    import generate_report
    mock_data = json.dumps(MOCK_QA)
    with patch("builtins.open", mock_open(read_data=mock_data)):
        batches = generate_report.load_qa_batches()
    for item in batches:
        assert "query" in item
        assert "expected_answer" in item
        assert "batch" in item
        assert item["type"] == "qa_pair"


def test_novel_questions_count():
    import generate_report
    assert len(generate_report.NOVEL_QUESTIONS) == 10


def test_novel_questions_are_strings():
    import generate_report
    for q in generate_report.NOVEL_QUESTIONS:
        assert isinstance(q, str)
        assert len(q) > 5


API_RESPONSE = {
    "success": True,
    "error": None,
    "result": {
        "response": "테스트 답변입니다.",
        "similarity": 0.8821,
        "cache_hit": True,
        "latency": 342.1,
        "co2_grams": 0.000021,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_001", "inha_notice_002"],
        "timings": [],
    },
}


def _make_mock_urlopen(response_dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_dict).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_query_chat_api_returns_flat_dict():
    import generate_report
    mock_resp = _make_mock_urlopen(API_RESPONSE)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = generate_report.query_chat_api("테스트 질문", api_url="http://localhost:8000")
    assert result["query"] == "테스트 질문"
    assert result["response"] == "테스트 답변입니다."
    assert result["cache_hit"] is True
    assert result["similarity"] == 0.8821
    assert result["latency_ms"] == 342.1
    assert result["co2_grams"] == 0.000021
    assert result["ci_g_per_kwh"] == 395.5
    assert result["sources"] == ["inha_notice_001", "inha_notice_002"]
    assert "wall_time_ms" in result


def test_query_chat_api_handles_api_error():
    import generate_report
    error_response = {"success": False, "error": "Retriever not initialized", "result": None}
    mock_resp = _make_mock_urlopen(error_response)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = generate_report.query_chat_api("질문", api_url="http://localhost:8000")
    assert result["success"] is False
    assert result["error"] == "Retriever not initialized"
    assert result["response"] is None


def test_query_chat_api_handles_connection_error():
    import generate_report
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        result = generate_report.query_chat_api("질문", api_url="http://localhost:8000")
    assert result["success"] is False
    assert "refused" in result["error"]


SAMPLE_RECORDS = [
    {
        "query": "신청 기간은 언제인가요?",
        "expected_answer": "4월 1일~28일",
        "batch": "sw_upstage_output (공지사항 2026)",
        "type": "qa_pair",
        "success": True,
        "error": None,
        "response": "신청 기간은 4월 1일부터 28일까지입니다.",
        "cache_hit": True,
        "similarity": 0.8821,
        "latency_ms": 342.1,
        "wall_time_ms": 355.0,
        "co2_grams": 0.000021,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_001"],
    },
    {
        "query": "SW중심대학 사업단 소개 및 주요 목표는 무엇인가요?",
        "expected_answer": None,
        "batch": None,
        "type": "novel",
        "success": True,
        "error": None,
        "response": "인하대학교 SW중심대학 사업단은...",
        "cache_hit": False,
        "similarity": 0.6123,
        "latency_ms": 5200.0,
        "wall_time_ms": 5215.0,
        "co2_grams": 0.000089,
        "ci_g_per_kwh": 395.5,
        "sources": ["inha_notice_012", "inha_pr_001"],
    },
]


def test_format_report_contains_summary_table():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Summary" in md
    assert "Cache Hit" in md
    assert "Similarity" in md
    assert "Latency" in md
    assert "CO₂" in md


def test_format_report_contains_qa_section():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## QA Pair Questions" in md
    assert "신청 기간은 언제인가요?" in md
    assert "4월 1일부터 28일까지" in md


def test_format_report_contains_novel_section():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Novel Questions" in md
    assert "SW중심대학 사업단 소개" in md


def test_format_report_contains_observations():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "## Observations" in md
    assert "cache hit" in md.lower() or "Cache Hit" in md


def test_format_report_cache_hit_symbols():
    import generate_report
    md = generate_report.format_report(SAMPLE_RECORDS, generated_at="2026-06-03 12:00")
    assert "✓" in md
    assert "✗" in md
