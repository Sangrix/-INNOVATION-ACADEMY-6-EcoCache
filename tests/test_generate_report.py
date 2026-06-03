import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch, mock_open
import json

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
