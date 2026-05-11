"""/api/env: masked GET + whitelisted POST + live reload."""
from __future__ import annotations

from pathlib import Path

import pytest

from web.app import app
from src import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect .env to a temp file to avoid touching the real one
    fake_env = tmp_path / ".env"
    fake_env.write_text(
        "DEEPSEEK_API_KEY=dc-sk-aaaabbbbccccdddd\n"
        "DEEPSEEK_MODEL=test-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    config.reload_env()

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_env_masks_sensitive_fields(client):
    resp = client.get("/api/env")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["DEEPSEEK_API_KEY"]["set"] is True
    # masked preview shows only last 4
    assert data["DEEPSEEK_API_KEY"]["preview"].endswith("dddd")
    assert "value" not in data["DEEPSEEK_API_KEY"]
    # non-sensitive field returns value in clear
    assert data["DEEPSEEK_MODEL"]["value"] == "test-model"


def test_post_updates_and_reloads(client):
    resp = client.post("/api/env", json={"DEEPSEEK_API_KEY": "dc-sk-NEWKEY1234"})
    assert resp.status_code == 200
    assert config.LLM_API_KEY == "dc-sk-NEWKEY1234"
    # Other fields preserved
    assert config.LLM_MODEL == "test-model"


def test_post_empty_string_clears(client):
    resp = client.post("/api/env", json={"PERPLEXITY_API_KEY": ""})
    assert resp.status_code == 200
    assert config.PERPLEXITY_API_KEY == ""


def test_post_rejects_unknown_key(client):
    resp = client.post("/api/env", json={"MALICIOUS_KEY": "pwned"})
    assert resp.status_code == 400


def test_post_rejects_nonstring(client):
    resp = client.post("/api/env", json={"DEEPSEEK_API_KEY": 123})
    assert resp.status_code == 400


def test_post_rejects_empty_body(client):
    resp = client.post("/api/env", json={})
    assert resp.status_code == 400


def test_get_reports_missing_key_as_unset(client, monkeypatch, tmp_path):
    # Override to a .env without DEEPSEEK_API_KEY
    fake_env = tmp_path / ".env"
    fake_env.write_text("DEEPSEEK_MODEL=only-model\n", encoding="utf-8")
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config.reload_env()
    resp = client.get("/api/env")
    data = resp.get_json()
    assert data["DEEPSEEK_API_KEY"]["set"] is False
    assert data["DEEPSEEK_API_KEY"]["length"] == 0


def test_post_preserves_user_added_keys(client, tmp_path, monkeypatch):
    """Non-whitelist keys in .env (user's manual additions) must survive writes."""
    fake_env = tmp_path / ".env"
    fake_env.write_text(
        "USER_CUSTOM=hello-world\n"
        "DEEPSEEK_API_KEY=dc-sk-old\n"
        "ZEBRA_FLAG=trailing\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    config.reload_env()

    resp = client.post("/api/env", json={"DEEPSEEK_API_KEY": "dc-sk-new"})
    assert resp.status_code == 200

    new_text = fake_env.read_text(encoding="utf-8")
    assert "USER_CUSTOM=hello-world" in new_text
    assert "ZEBRA_FLAG=trailing" in new_text
    assert "DEEPSEEK_API_KEY=dc-sk-new" in new_text
    assert "DEEPSEEK_API_KEY=dc-sk-old" not in new_text
