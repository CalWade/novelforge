"""/api/novels: used_by_presets + confirm-before-delete."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app_(tmp_path: Path, monkeypatch):
    from src import config
    # preset alpha uses a.txt; beta uses nothing
    for gid in ("alpha", "beta"):
        pd = tmp_path / "presets" / gid
        pd.mkdir(parents=True)
        (pd / "genre.yaml").write_text(f"id: {gid}\n", encoding="utf-8")
        (pd / "era.md").write_text("x\n", encoding="utf-8")
        (pd / "novels").mkdir()
    (tmp_path / "presets" / "alpha" / "novels" / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "novels" / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "projects").mkdir()

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")
    from web import app as web_app
    # NOVELS_DIR is captured at import time; force it to the tmp location.
    monkeypatch.setattr(web_app, "NOVELS_DIR", tmp_path / "novels")
    return web_app.app.test_client()


def test_novels_list_has_used_by_presets(app_):
    data = app_.get("/api/novels").get_json()
    by_name = {n["name"]: n for n in data["novels"]}
    assert by_name["a.txt"]["used_by_presets"] == ["alpha"]
    assert by_name["b.txt"]["used_by_presets"] == []


def test_novels_delete_unused_straight(app_):
    r = app_.delete("/api/novels/b.txt")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_novels_delete_used_warns_then_force(app_):
    r1 = app_.delete("/api/novels/a.txt")
    assert r1.status_code == 409
    data = r1.get_json()
    assert data["ok"] is False
    assert data["used_by_presets"] == ["alpha"]

    r2 = app_.delete("/api/novels/a.txt?force=true")
    assert r2.status_code == 200
    assert r2.get_json()["ok"] is True
