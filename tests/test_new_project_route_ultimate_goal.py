"""POST /api/projects/new: ultimate_goal field plumbing."""
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


def test_route_accepts_ultimate_goal(app_, monkeypatch):
    """POST /api/projects/new 带 ultimate_goal → create_project 收到该字段。"""
    captured = {}

    # spy on create_project (replace with one that records kwargs and short-circuits)
    real_create = None
    from src import bootstrap as _bootstrap
    real_create = _bootstrap.create_project

    def spy_create_project(project_id, **kwargs):
        captured["kwargs"] = kwargs
        captured["project_id"] = project_id
        return real_create(project_id, **kwargs)

    monkeypatch.setattr(_bootstrap, "create_project", spy_create_project)
    # also patch the import inside web.routes.projects (imports inside route fn)
    import web.routes.projects as projects_route
    monkeypatch.setattr(projects_route, "READONLY_MODE", False, raising=False)

    # mock the plot_arc drafter so we don't hit LLM
    monkeypatch.setattr(
        "src.agents.plot_arc_drafter.run",
        lambda **kw: {
            "schema_version": 1,
            "total_chapters": kw["chapter_count_target"],
            "ultimate_goal": kw["ultimate_goal"],
            "acts": [
                {"name": "卷一", "range": [1, 3], "goal": "g", "must_close_by_end": ["a"]},
                {"name": "卷二", "range": [4, 5], "goal": "g", "must_close_by_end": ["b"]},
                {"name": "卷三", "range": [6, 8], "goal": "g", "must_close_by_end": ["c"]},
                {"name": "终卷", "range": [9, 10], "goal": "g", "must_close_by_end": ["d"]},
            ],
        },
    )

    r = app_.post("/api/projects/new", json={
        "id": "ug1", "display_name": "UG1", "protagonist_name": "H",
        "chapter_count_target": 10, "from_preset": "alpha",
        "blank_outline": True, "blank_characters": True,
        "ultimate_goal": "苏烬要找出灰烬契书源头",
    })
    assert r.status_code == 200, r.get_json()
    assert captured["kwargs"].get("ultimate_goal") == "苏烬要找出灰烬契书源头"


def test_route_works_without_ultimate_goal(app_):
    """不带 ultimate_goal → 不报错（向后兼容已有客户端）。"""
    r = app_.post("/api/projects/new", json={
        "id": "ug2", "display_name": "UG2", "protagonist_name": "H",
        "chapter_count_target": 5, "from_preset": "alpha",
        "blank_outline": True, "blank_characters": True,
        # ultimate_goal 不传
    })
    assert r.status_code == 200, r.get_json()
