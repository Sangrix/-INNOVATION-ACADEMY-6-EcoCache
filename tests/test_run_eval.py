import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "carbon"))

from unittest.mock import patch


def test_get_ciasc_threshold_uses_db_when_available():
    """_get_ciasc_threshold must prefer DB over live API."""
    import run_eval
    with patch("run_eval.get_latest_ci_from_db", return_value=400.0) as mock_db:
        with patch("run_eval.get_optimizer") as mock_opt:
            result = run_eval._get_ciasc_threshold(alpha=0.15)
    mock_db.assert_called_once()
    mock_opt.assert_not_called()
    assert isinstance(result, float)


def test_get_ciasc_threshold_falls_back_to_optimizer_when_db_empty():
    import run_eval
    with patch("run_eval.get_latest_ci_from_db", return_value=None):
        with patch("run_eval.get_optimizer") as mock_opt:
            mock_opt.return_value.get_current_ci.return_value = 415.0
            mock_opt.return_value.get_adaptive_threshold.return_value = 0.7375
            result = run_eval._get_ciasc_threshold(alpha=0.15)
    mock_opt.assert_called()
    assert result == 0.7375
