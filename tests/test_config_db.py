import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

def test_db_config_keys_present():
    import config
    required = {"dbname", "user", "password", "host", "port"}
    assert required.issubset(config.DB_CONFIG.keys())

def test_db_config_port_is_int():
    import config
    assert isinstance(config.DB_CONFIG["port"], int)
