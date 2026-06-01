import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from unittest.mock import patch, MagicMock
import asyncio
import inspect

def test_get_current_ci_is_async():
    import main
    assert inspect.iscoroutinefunction(main._get_current_ci)

def test_get_current_ci_reads_db_first():
    import main
    with patch("main.get_latest_ci_from_db", return_value=390.0) as mock_db:
        with patch("main.get_optimizer") as mock_opt:
            result = asyncio.run(main._get_current_ci())
    mock_db.assert_called_once()
    mock_opt.assert_not_called()
    assert result == 390.0

def test_get_current_ci_falls_back_when_db_returns_none():
    import main
    with patch("main.get_latest_ci_from_db", return_value=None):
        with patch("main.get_optimizer") as mock_opt:
            mock_opt.return_value.get_current_ci.return_value = 415.0
            result = asyncio.run(main._get_current_ci())
    assert result == 415.0
