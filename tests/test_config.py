# tests/test_config.py
import pytest
from pinduoduo_ai.config import load_config, get_api_key

def test_load_config_defaults(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "polling:\n  interval_seconds: 5\n"
        "ai:\n  model: deepseek-chat\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    assert cfg["polling"]["interval_seconds"] == 5
    assert cfg["ai"]["model"] == "deepseek-chat"

def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nope.yaml"))

def test_get_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_api_key()
