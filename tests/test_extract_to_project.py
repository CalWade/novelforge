"""Extract a genre pack into projects/<book-id>/ (overwriting that book's 4 genre files)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    book = tmp_path / "projects" / "mybook"
    book.mkdir(parents=True)
    (book / "project.yaml").write_text("id: mybook\nprotagonist_name: hero\n", encoding="utf-8")
    (book / "outline.json").write_text("{}", encoding="utf-8")
    (book / "characters.yaml").write_text("{}", encoding="utf-8")
    (book / "timeline.yaml").write_text("{}", encoding="utf-8")
    (book / "era.md").write_text("old era\n", encoding="utf-8")
    (book / "writing-style-extra.md").write_text("old style\n", encoding="utf-8")
    (book / "iron-laws-extra.md").write_text("old laws\n", encoding="utf-8")
    (book / "state").mkdir()

    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "a.txt").write_text("第一章 a\n", encoding="utf-8")

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def test_extract_to_project_overwrites_genre_files(fake_repo, monkeypatch):
    from src.genre_extractor import to_project

    def fake_run(bb, sources, **_):
        return {
            "era": {"content": "# new era"},
            "writing_style_extra": {"content": "# new style"},
            "iron_laws_extra": {"content": "# new laws"},
            "resource_schema": None,
        }
    monkeypatch.setattr(to_project, "_run_full_extraction_to_blueprint", fake_run)
    # Neutralise Validator — real validator would rewrite AI-slop stubs.
    from src.genre_extractor import pipeline
    monkeypatch.setattr(pipeline, "_run_validate", lambda *a, **k: None)

    result = to_project.extract_to_project(book_id="mybook", sources=["a.txt"])
    book = fake_repo / "projects" / "mybook"
    assert (book / "era.md").read_text(encoding="utf-8") == "# new era"
    assert (book / "writing-style-extra.md").read_text(encoding="utf-8") == "# new style"
    assert result["book_id"] == "mybook"


def test_extract_to_project_backs_up_previous_files(fake_repo, monkeypatch):
    from src.genre_extractor import to_project

    def fake_run(bb, sources, **_):
        return {
            "era": {"content": "# new"}, "writing_style_extra": {"content": "s"},
            "iron_laws_extra": {"content": "l"}, "resource_schema": None,
        }
    monkeypatch.setattr(to_project, "_run_full_extraction_to_blueprint", fake_run)
    from src.genre_extractor import pipeline
    monkeypatch.setattr(pipeline, "_run_validate", lambda *a, **k: None)

    to_project.extract_to_project(book_id="mybook", sources=["a.txt"])
    backup_dir = fake_repo / "projects" / "mybook" / "state" / ".backup"
    backups = list(backup_dir.glob("era*"))
    assert backups, "no backup file for era.md created"
    assert any("old era" in p.read_text(encoding="utf-8") for p in backups)


def test_extract_to_project_missing_book_raises(fake_repo):
    from src.genre_extractor import to_project
    with pytest.raises(FileNotFoundError, match="Project not found"):
        to_project.extract_to_project(book_id="does-not-exist", sources=["a.txt"])
