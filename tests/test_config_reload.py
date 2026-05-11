"""reload_env must pick up new .env values into config.LLM_API_KEY etc. globals."""
from __future__ import annotations

from src import config


def test_reload_env_picks_up_key_changes(tmp_path, monkeypatch):
    fake_env = tmp_path / ".env"
    fake_env.write_text("DEEPSEEK_API_KEY=first-key\nDEEPSEEK_MODEL=first-model\n", encoding="utf-8")

    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    config.reload_env()
    assert config.LLM_API_KEY == "first-key"
    assert config.LLM_MODEL == "first-model"

    fake_env.write_text("DEEPSEEK_API_KEY=second-key\nDEEPSEEK_MODEL=second-model\n", encoding="utf-8")
    config.reload_env()
    assert config.LLM_API_KEY == "second-key"
    assert config.LLM_MODEL == "second-model"


def test_reload_env_covers_perplexity_fields(tmp_path, monkeypatch):
    fake_env = tmp_path / ".env"
    fake_env.write_text("PERPLEXITY_API_KEY=pplx-xyz\n", encoding="utf-8")
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    config.reload_env()
    assert config.PERPLEXITY_API_KEY == "pplx-xyz"
