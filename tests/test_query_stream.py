# tests/test_query_stream.py
from unittest.mock import MagicMock, patch
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))


def _make_chunk(text):
    chunk = MagicMock()
    chunk.choices[0].delta.content = text
    return chunk


def test_generate_answer_stream_yields_text_chunks():
    """Yields non-empty text chunks from OpenAI streaming response."""
    from query import generate_answer_stream

    chunks_to_return = [_make_chunk("안녕"), _make_chunk("하세요"), _make_chunk(None)]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(chunks_to_return)

    with patch("query.OpenAI", return_value=mock_client):
        rag_result = {
            "source": "documents",
            "results": [{"score": 0.8, "payload": {"raw_text": "context text"}}],
        }
        result = list(generate_answer_stream("질문", rag_result))

    assert result == ["안녕", "하세요"]


def test_generate_answer_stream_skips_empty_chunks():
    """Empty string and None deltas are not yielded."""
    from query import generate_answer_stream

    chunks_to_return = [_make_chunk(""), _make_chunk("텍스트"), _make_chunk(None)]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(chunks_to_return)

    with patch("query.OpenAI", return_value=mock_client):
        rag_result = {"source": "documents", "results": []}
        result = list(generate_answer_stream("질문", rag_result))

    assert result == ["텍스트"]


def test_generate_answer_stream_raises_without_model(monkeypatch):
    """Raises ValueError when LM_STUDIO_MODEL is not set."""
    import config
    from query import generate_answer_stream

    monkeypatch.setattr(config, "LM_STUDIO_MODEL", "")

    rag_result = {"source": "documents", "results": []}
    with pytest.raises(ValueError, match="LM_STUDIO_MODEL"):
        list(generate_answer_stream("질문", rag_result))
