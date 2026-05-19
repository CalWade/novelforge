"""bootstrap.create_project: ultimate_goal → auto-draft plot_arc.yaml.

Mirrors fake_repo fixture from test_bootstrap_book_centric.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    preset = tmp_path / "presets" / "alpha"
    preset.mkdir(parents=True)
    (preset / "genre.yaml").write_text(
        "id: alpha\ndisplay_name: Alpha\ntone: dark\n", encoding="utf-8"
    )
    (preset / "era.md").write_text(
        "# alpha era\n灰烬纪年，G22 服务区，灰烬契书。", encoding="utf-8"
    )
    (preset / "writing-style-extra.md").write_text("# alpha style\n", encoding="utf-8")
    (preset / "iron-laws-extra.md").write_text("# alpha laws\n", encoding="utf-8")

    (tmp_path / "projects").mkdir()

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")
    return tmp_path


def test_create_project_with_ultimate_goal_auto_drafts(fake_repo, monkeypatch):
    """传 ultimate_goal → 自动调 PlotArcDrafter → plot_arc.yaml 被创建。"""
    captured = {}

    def fake_draft(*, ultimate_goal, chapter_count_target, era_md_excerpt=""):
        captured["ultimate_goal"] = ultimate_goal
        captured["chapter_count_target"] = chapter_count_target
        captured["era_md_excerpt"] = era_md_excerpt
        return {
            "schema_version": 1,
            "total_chapters": chapter_count_target,
            "ultimate_goal": ultimate_goal,
            "acts": [
                {"name": "卷一", "range": [1, 13], "goal": "g1", "must_close_by_end": ["a"]},
                {"name": "卷二", "range": [14, 26], "goal": "g2", "must_close_by_end": ["b"]},
                {"name": "卷三", "range": [27, 38], "goal": "g3", "must_close_by_end": ["c"]},
                {"name": "终卷", "range": [39, 50], "goal": "g4", "must_close_by_end": ["d"]},
            ],
        }

    monkeypatch.setattr("src.agents.plot_arc_drafter.run", fake_draft)

    from src.bootstrap import create_project
    warnings: list = []
    book_dir = create_project(
        "mybook",
        display_name="My Book",
        protagonist_name="Hero",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
        ultimate_goal="苏烬要找出灰烬契书源头",
        warnings_collector=warnings,
    )

    plot_arc_path = book_dir / "plot_arc.yaml"
    assert plot_arc_path.exists()
    data = yaml.safe_load(plot_arc_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["total_chapters"] == 50
    assert data["ultimate_goal"] == "苏烬要找出灰烬契书源头"
    assert len(data["acts"]) == 4

    # drafter 接到的参数透传正确
    assert captured["ultimate_goal"] == "苏烬要找出灰烬契书源头"
    assert captured["chapter_count_target"] == 50
    # era.md 摘录被传入
    assert "灰烬纪年" in captured["era_md_excerpt"]

    # warnings_collector 收到 plot_arc 起草成功标记
    plot_arc_warnings = [w for w in warnings if w.get("field") == "plot_arc"]
    assert len(plot_arc_warnings) == 1
    assert "auto-drafted" in plot_arc_warnings[0]["reason"]


def test_create_project_no_ultimate_goal_no_autodraft(fake_repo, monkeypatch):
    """不传 ultimate_goal → plot_arc.yaml 不被创建（向后兼容）。"""
    # 让 drafter 即使被错误调用也能被检测到
    called = {"count": 0}

    def fake_draft(*args, **kwargs):
        called["count"] += 1
        return {}

    monkeypatch.setattr("src.agents.plot_arc_drafter.run", fake_draft)

    from src.bootstrap import create_project
    book_dir = create_project(
        "mybook2",
        display_name="My Book 2",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
        # ultimate_goal 不传
    )
    assert not (book_dir / "plot_arc.yaml").exists()
    assert called["count"] == 0


def test_create_project_drafter_failure_falls_back_with_warning(fake_repo, monkeypatch):
    """PlotArcDrafter 抛异常 → warnings_collector 收到失败警告 + 不阻断作品创建。"""
    def bad_draft(**kwargs):
        raise RuntimeError("LLM exploded")

    monkeypatch.setattr("src.agents.plot_arc_drafter.run", bad_draft)

    from src.bootstrap import create_project
    warnings: list = []
    book_dir = create_project(
        "mybook3",
        display_name="My Book 3",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
        ultimate_goal="something",
        warnings_collector=warnings,
    )
    # 作品仍创建成功（核心文件都在）
    assert book_dir.exists()
    assert (book_dir / "project.yaml").exists()
    assert (book_dir / "outline.json").exists()
    # plot_arc.yaml 不存在（drafter 失败时不写）
    assert not (book_dir / "plot_arc.yaml").exists()
    # warnings 含 plot_arc 失败
    plot_arc_warnings = [w for w in warnings if w.get("field") == "plot_arc"]
    assert len(plot_arc_warnings) == 1
    assert "RuntimeError" in plot_arc_warnings[0]["reason"]
    assert "LLM exploded" in plot_arc_warnings[0]["reason"]


def test_create_project_blank_ultimate_goal_no_autodraft(fake_repo, monkeypatch):
    """ultimate_goal='' / 全空白字符 → 视同未传，不调 drafter。"""
    called = {"count": 0}

    def fake_draft(*args, **kwargs):
        called["count"] += 1
        return {}

    monkeypatch.setattr("src.agents.plot_arc_drafter.run", fake_draft)

    from src.bootstrap import create_project
    book_dir = create_project(
        "mybook4",
        display_name="My Book 4",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
        ultimate_goal="   ",  # 全空白
    )
    assert not (book_dir / "plot_arc.yaml").exists()
    assert called["count"] == 0
