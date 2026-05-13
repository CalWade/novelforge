"""Preset management API: list / detail / delete."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app_with_presets(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    for gid in ("gangster-hk-1983", "xianxia-ascension", "my-custom"):
        pd = tmp_path / "presets" / gid
        pd.mkdir()
        (pd / "genre.yaml").write_text(
            f"id: {gid}\ndisplay_name: {gid}\ntone: test\n", encoding="utf-8",
        )
        (pd / "era.md").write_text(f"era {gid}\n", encoding="utf-8")
        (pd / "novels").mkdir()

    (tmp_path / "projects").mkdir()
    (tmp_path / "novels").mkdir()

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")

    from web import app as web_app
    return web_app.app.test_client()


def test_get_api_presets_lists_all(app_with_presets):
    r = app_with_presets.get("/api/presets")
    assert r.status_code == 200
    data = r.get_json()
    ids = [p["id"] for p in data["presets"]]
    assert set(ids) >= {"gangster-hk-1983", "xianxia-ascension", "my-custom"}


def test_get_api_preset_detail(app_with_presets):
    r = app_with_presets.get("/api/presets/my-custom")
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == "my-custom"
    assert "era.md" in data["files"]
    # builtin flag
    r2 = app_with_presets.get("/api/presets/gangster-hk-1983")
    assert r2.get_json()["builtin"] is True
    assert r.get_json()["builtin"] is False


def test_delete_preset_builtin_refused(app_with_presets):
    r = app_with_presets.delete("/api/presets/gangster-hk-1983")
    assert r.status_code == 403
    reason = (r.get_json() or {}).get("reason", "").lower()
    assert "built" in reason


def test_delete_preset_custom_works(app_with_presets):
    r = app_with_presets.delete("/api/presets/my-custom")
    assert r.status_code == 200
    r2 = app_with_presets.get("/api/presets/my-custom")
    assert r2.status_code == 404


def test_get_preset_404(app_with_presets):
    r = app_with_presets.get("/api/presets/doesnotexist")
    assert r.status_code == 404


def test_view_presets_index_html(app_with_presets):
    r = app_with_presets.get("/presets")
    assert r.status_code == 200
    # page should at least render — content comes via /api/presets JS
    assert b"<html" in r.data.lower() or b"<!doctype" in r.data.lower()


def test_old_genres_routes_gone(app_with_presets):
    """Old /genres* routes must return 404."""
    for path in ("/genres", "/genres/new", "/genres/gangster-hk-1983", "/api/genres"):
        r = app_with_presets.get(path)
        assert r.status_code == 404, f"old route {path} still serves"


# NOTE: Previous tests for POST /api/presets/new-from-novel and
# GET /api/presets/<pid>/status were removed — those endpoints were
# deleted. Extract-to-preset is now dispatched via POST /api/jobs.
