# tests/test_api_stream.py
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into a list of event dicts. Ignores [DONE]."""
    events = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                raw = line[6:]
                if raw == "[DONE]":
                    break
                events.append(json.loads(raw))
    return events


@pytest.fixture
def mock_retriever_cache_hit():
    m = MagicMock()
    m.retrieve.return_value = {
        "source": "qa_pairs",
        "query": "test",
        "results": [{"score": 0.91, "payload": {"answer": {"text": "캐시 히트 응답"}}}],
    }
    return m


@pytest.fixture
def mock_retriever_cache_miss():
    m = MagicMock()
    m.retrieve.return_value = {
        "source": "documents",
        "query": "test",
        "results": [{"score": 0.78, "payload": {"doc_id": "inha_notice_001", "raw_text": "context"}}],
    }
    return m


def test_chat_stream_cache_hit_returns_sse(mock_retriever_cache_hit):
    """Cache hit: one token event with full answer, then meta event."""
    from fastapi.testclient import TestClient

    mock_state = {"metrics": {"co2_g": 0.0}}
    mock_cm = MagicMock()
    mock_cm.track.return_value.__enter__ = MagicMock(return_value=mock_state)
    mock_cm.track.return_value.__exit__ = MagicMock(return_value=False)

    with patch("main._retriever", mock_retriever_cache_hit), \
         patch("main._get_current_ci_sync", return_value=350.0), \
         patch("main.carbon_monitor", mock_cm):

        import main
        client = TestClient(main.app)
        res = client.post("/chat/stream", json={"query": "test"})

    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = _parse_sse(res.text)
    token_events = [e for e in events if e.get("type") == "token"]
    meta_events  = [e for e in events if e.get("type") == "meta"]

    assert len(token_events) == 1
    assert token_events[0]["text"] == "캐시 히트 응답"
    assert len(meta_events) == 1
    assert meta_events[0]["cache_hit"] is True
    assert meta_events[0]["similarity"] == pytest.approx(0.91)


def test_chat_stream_cache_miss_streams_tokens(mock_retriever_cache_miss):
    """Cache miss: multiple token events from LLM, then meta event."""
    from fastapi.testclient import TestClient

    def fake_generate_stream(query, rag_result):
        yield "첫 번째"
        yield " 두 번째"

    mock_state = {"metrics": {"co2_g": 0.0001}}
    mock_cm = MagicMock()
    mock_cm.track.return_value.__enter__ = MagicMock(return_value=mock_state)
    mock_cm.track.return_value.__exit__ = MagicMock(return_value=False)

    with patch("main._retriever", mock_retriever_cache_miss), \
         patch("main._get_current_ci_sync", return_value=350.0), \
         patch("main.generate_answer_stream", side_effect=fake_generate_stream), \
         patch("main.carbon_monitor", mock_cm):

        import main
        client = TestClient(main.app)
        res = client.post("/chat/stream", json={"query": "test"})

    events = _parse_sse(res.text)
    token_events = [e for e in events if e.get("type") == "token"]
    meta_events  = [e for e in events if e.get("type") == "meta"]

    assert [e["text"] for e in token_events] == ["첫 번째", " 두 번째"]
    assert meta_events[0]["cache_hit"] is False


def test_chat_stream_meta_event_has_required_fields(mock_retriever_cache_hit):
    """Meta event contains all required fields."""
    from fastapi.testclient import TestClient

    mock_state = {"metrics": {"co2_g": 0.0002}}
    mock_cm = MagicMock()
    mock_cm.track.return_value.__enter__ = MagicMock(return_value=mock_state)
    mock_cm.track.return_value.__exit__ = MagicMock(return_value=False)

    with patch("main._retriever", mock_retriever_cache_hit), \
         patch("main._get_current_ci_sync", return_value=412.0), \
         patch("main.carbon_monitor", mock_cm):

        import main
        client = TestClient(main.app)
        res = client.post("/chat/stream", json={"query": "test"})

    meta = [e for e in _parse_sse(res.text) if e.get("type") == "meta"][0]

    for field in ("cache_hit", "similarity", "latency_ms", "co2_grams", "ci_g_per_kwh", "sources"):
        assert field in meta, f"Missing field: {field}"
    assert meta["ci_g_per_kwh"] == 412.0


def test_chat_stream_retriever_none_returns_error_event():
    """When _retriever is None, emits an error SSE event followed by [DONE]."""
    from fastapi.testclient import TestClient

    with patch("main._retriever", None):
        import main
        client = TestClient(main.app)
        res = client.post("/chat/stream", json={"query": "test"})

    assert res.status_code == 200
    events = _parse_sse(res.text)
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert "Retriever" in error_events[0]["message"]
    assert "data: [DONE]" in res.text


def test_chat_stream_llm_error_emits_error_event(mock_retriever_cache_miss):
    """When LLM raises, emits an error SSE event then meta and [DONE] still appear."""
    from fastapi.testclient import TestClient

    mock_state = {"metrics": {"co2_g": 0.0}}
    mock_cm = MagicMock()
    mock_cm.track.return_value.__enter__ = MagicMock(return_value=mock_state)
    mock_cm.track.return_value.__exit__ = MagicMock(return_value=False)

    def failing_stream(query, rag_result):
        raise RuntimeError("LM Studio 연결 실패")
        yield  # make it a generator

    with patch("main._retriever", mock_retriever_cache_miss), \
         patch("main._get_current_ci_sync", return_value=350.0), \
         patch("main.generate_answer_stream", side_effect=failing_stream), \
         patch("main.carbon_monitor", mock_cm):

        import main
        client = TestClient(main.app)
        res = client.post("/chat/stream", json={"query": "test"})

    events = _parse_sse(res.text)
    error_events = [e for e in events if e.get("type") == "error"]
    meta_events  = [e for e in events if e.get("type") == "meta"]
    assert len(error_events) >= 1
    assert len(meta_events) == 1
    assert "data: [DONE]" in res.text
