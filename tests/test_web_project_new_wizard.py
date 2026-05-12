"""POST /api/projects/new: 4-step wizard fields."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app_(tmp_path: Path, monkeypatch):
    from src import config
    preset = tmp_path / "presets" / "alpha"
    preset.mkdir(parents=True)
    (preset / "genre.yaml").write_text("id: alpha\n", encoding="utf-8")
    for f in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        (preset / f).write_text("x\n", encoding="utf-8")
    (preset / "novels").mkdir()

    (tmp_path / "projects").mkdir()
    (tmp_path / "novels").mkdir()

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")
    from web import app as web_app
    return web_app.app.test_client()


def test_wizard_blank_all(app_):
    r = app_.post("/api/projects/new", json={
        "id": "b1", "display_name": "B1", "protagonist_name": "H",
        "chapter_count_target": 10, "blank_genre": True,
        "blank_outline": True, "blank_characters": True,
    })
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["project_id"] == "b1"


def test_wizard_from_preset(app_):
    r = app_.post("/api/projects/new", json={
        "id": "b2", "display_name": "B2", "protagonist_name": "H",
        "chapter_count_target": 5, "from_preset": "alpha",
        "blank_outline": True, "blank_characters": True,
    })
    assert r.status_code == 200, r.get_json()


def test_wizard_with_synopsis_and_brief(app_, monkeypatch):
    monkeypatch.setattr(
        "src.agents.outline_drafter.OutlineDrafter.run",
        lambda self, *, synopsis, chapter_count_target, display_name: {
            "title": display_name,
            "chapters": [{"index": 1, "title": "c1", "beats": ["x"]}],
        },
    )
    monkeypatch.setattr(
        "src.agents.characters_drafter.CharactersDrafter.run",
        lambda self, *, brief, protagonist_name: {
            "protagonist": {"name": protagonist_name, "description": "d"},
            "supporting": [],
        },
    )
    r = app_.post("/api/projects/new", json={
        "id": "b3", "display_name": "B3", "protagonist_name": "H",
        "chapter_count_target": 3, "from_preset": "alpha",
        "outline_synopsis": "some story",
        "characters_brief": "some people",
    })
    assert r.status_code == 200, r.get_json()


def test_wizard_with_extract_runs_in_background(app_, monkeypatch):
    from src import config
    (config.PROJECT_ROOT / "novels" / "seed.txt").write_text("x", encoding="utf-8")

    called = {}
    def fake_extract(book_id, *, sources, with_trial):
        called.update(book_id=book_id, sources=list(sources))
    monkeypatch.setattr("src.genre_extractor.to_project.extract_to_project", fake_extract)

    r = app_.post("/api/projects/new", json={
        "id": "b4", "display_name": "B4", "protagonist_name": "H",
        "chapter_count_target": 3,
        "from_extract": {"sources": ["seed.txt"], "with_trial": False},
        "blank_outline": True, "blank_characters": True,
    })
    assert r.status_code == 202, r.get_json()

    import time
    for _ in range(40):
        s = app_.get("/api/projects/b4/extract-genre/progress").get_json()
        if s.get("state") in ("done", "failed"):
            break
        time.sleep(0.05)
    assert called.get("book_id") == "b4"


def test_wizard_missing_required_fields(app_):
    r = app_.post("/api/projects/new", json={"id": "nodash"})
    assert r.status_code == 400


def test_wizard_mutually_exclusive_genre_flags(app_):
    r = app_.post("/api/projects/new", json={
        "id": "bad", "display_name": "d", "protagonist_name": "h",
        "chapter_count_target": 3,
        "from_preset": "alpha", "blank_genre": True,
        "blank_outline": True, "blank_characters": True,
    })
    assert r.status_code == 400


def test_wizard_duplicate_project_409(app_):
    r1 = app_.post("/api/projects/new", json={
        "id": "dup", "display_name": "D", "protagonist_name": "H",
        "chapter_count_target": 3, "blank_genre": True,
        "blank_outline": True, "blank_characters": True,
    })
    assert r1.status_code == 200
    r2 = app_.post("/api/projects/new", json={
        "id": "dup", "display_name": "D", "protagonist_name": "H",
        "chapter_count_target": 3, "blank_genre": True,
        "blank_outline": True, "blank_characters": True,
    })
    assert r2.status_code == 409
