"""Single-layer bootstrap + create_project(from_preset=...)."""
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
    (preset / "era.md").write_text("# alpha era\n", encoding="utf-8")
    (preset / "writing-style-extra.md").write_text("# alpha style\n", encoding="utf-8")
    (preset / "iron-laws-extra.md").write_text("# alpha laws\n", encoding="utf-8")
    (preset / "resource_schema.yaml").write_text("resources: []\n", encoding="utf-8")
    (preset / "novels").mkdir()

    (tmp_path / "projects").mkdir()
    (tmp_path / "novels").mkdir()

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")
    return tmp_path


def test_create_project_from_preset_copies_4_genre_files(fake_repo):
    from src.bootstrap import create_project
    book_dir = create_project(
        "mybook",
        display_name="My Book",
        protagonist_name="Hero",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
    )
    for fname in (
        "era.md", "writing-style-extra.md", "iron-laws-extra.md", "resource_schema.yaml",
    ):
        assert (book_dir / fname).exists()
    data = yaml.safe_load((book_dir / "project.yaml").read_text(encoding="utf-8"))
    assert data["source_preset"] == "alpha"
    assert data["protagonist_name"] == "Hero"


def test_create_project_blank_genre(fake_repo):
    from src.bootstrap import create_project
    book_dir = create_project(
        "blankbook",
        display_name="Blank",
        protagonist_name="H",
        chapter_count_target=10,
        blank_genre=True,
        blank_outline=True,
        blank_characters=True,
    )
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        p = book_dir / fname
        assert p.exists()
        assert len(p.read_text(encoding="utf-8")) < 200
    assert not (book_dir / "resource_schema.yaml").exists()


def test_bootstrap_project_single_layer(fake_repo):
    from src.bootstrap import create_project, bootstrap_project
    create_project(
        "mybook",
        display_name="My Book",
        protagonist_name="Hero",
        chapter_count_target=50,
        from_preset="alpha",
        blank_outline=True,
        blank_characters=True,
    )
    result = bootstrap_project("mybook")
    state = fake_repo / "projects" / "mybook" / "state"
    for fname in (
        "era.md", "writing-style-extra.md", "iron-laws-extra.md", "setting.yaml",
        "outline.json", "characters.yaml", "timeline.yaml",
    ):
        assert (state / fname).exists(), f"{fname} missing"
    setting = yaml.safe_load((state / "setting.yaml").read_text(encoding="utf-8"))
    assert setting["id"] == "mybook"
    assert setting["active_project"] == "mybook"
    assert "active_genre" not in setting


def test_bootstrap_refuses_missing_preset(fake_repo):
    from src.bootstrap import create_project
    with pytest.raises(FileNotFoundError, match="preset"):
        create_project(
            "x",
            display_name="X",
            protagonist_name="H",
            chapter_count_target=10,
            from_preset="nonexistent",
            blank_outline=True,
            blank_characters=True,
        )


def test_create_project_rejects_duplicate_preset_and_blank(fake_repo):
    from src.bootstrap import create_project
    with pytest.raises(ValueError, match="mutually exclusive"):
        create_project(
            "dup",
            display_name="D",
            protagonist_name="H",
            chapter_count_target=10,
            from_preset="alpha",
            blank_genre=True,
            blank_outline=True,
            blank_characters=True,
        )
