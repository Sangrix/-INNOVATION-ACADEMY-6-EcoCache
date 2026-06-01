import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))

def test_db_config_imported_from_config():
    """collector must NOT define its own DB_CONFIG."""
    import collector
    import config
    assert collector.DB_CONFIG is config.DB_CONFIG


from unittest.mock import patch, MagicMock

def test_get_latest_ci_from_db_returns_float_on_success():
    import collector
    mock_conn = MagicMock()
    mock_cur  = MagicMock()
    mock_cur.fetchone.return_value = (412.5,)
    mock_conn.cursor.return_value  = mock_cur
    with patch("collector.psycopg2.connect", return_value=mock_conn):
        result = collector.get_latest_ci_from_db()
    assert result == 412.5

def test_get_latest_ci_from_db_returns_none_when_empty():
    import collector
    mock_conn = MagicMock()
    mock_cur  = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value  = mock_cur
    with patch("collector.psycopg2.connect", return_value=mock_conn):
        result = collector.get_latest_ci_from_db()
    assert result is None

def test_get_latest_ci_from_db_returns_none_on_db_error():
    import collector
    with patch("collector.psycopg2.connect", side_effect=Exception("conn failed")):
        result = collector.get_latest_ci_from_db()
    assert result is None


import asyncio
import inspect

def test_save_to_db_async_is_coroutine():
    import collector
    assert inspect.iscoroutinefunction(collector.save_to_db)

def test_save_to_db_async_runs_without_error():
    import collector
    mock_conn = MagicMock()
    mock_cur  = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    with patch("collector.psycopg2.connect", return_value=mock_conn):
        asyncio.run(collector.save_to_db(380.0, "API"))
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
