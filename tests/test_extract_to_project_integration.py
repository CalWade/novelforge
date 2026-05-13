"""End-to-end integration test for extract_to_project.

Symmetric to ``test_extract_to_preset_integration.py``: mocks only the
deepest LLM-calling agents, letting ``core.run_extract`` /
``core.run_merge`` / ``core.render_files_from_blueprint`` /
``_run_validate`` all run for real. Catches the class of bugs the
wholesale-mock unit tests miss (e.g. FileNotFoundError on missing
build_status.yaml, AttributeError on phantom trial functions,
silent-no-op draft phase).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config

    # Minimal book directory: has the 4 project-layer files + old genre
    # files that extract_to_project should back up then overwrite.
    book = tmp_path / "projects" / "mybook"
    book.mkdir(parents=True)
    (book / "project.yaml").write_text(
        "id: mybook\nprotagonist_name: hero\n", encoding="utf-8"
    )
    (book / "outline.json").write_text("{}", encoding="utf-8")
    (book / "characters.yaml").write_text("{}", encoding="utf-8")
    (book / "timeline.yaml").write_text("{}", encoding="utf-8")
    (book / "era.md").write_text("OLD ERA\n", encoding="utf-8")
    (book / "writing-style-extra.md").write_text("OLD STYLE\n", encoding="utf-8")
    (book / "iron-laws-extra.md").write_text("OLD LAWS\n", encoding="utf-8")
    (book / "state").mkdir()

    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "novel.txt").write_text(
        "第一章 序幕\n阿强走进茶餐厅。\n"
        "第二章 风起\n他见了老大。\n"
        "第三章 落幕\n尘埃落定。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def _noop_extractor(self, bb, **kwargs):
    bid = kwargs["batch_id"]
    bb.write_yaml(
        f"extraction_notes/batch-{bid:03d}.yaml",
        {
            "batch_id": bid, "chapters_covered": [1, 1],
            "novel_source": "novel.txt",
            "extracted_at": "2026-01-01T00:00:00",
            "era_observations": [], "iron_law_candidates": [],
            "style_markers": [], "resource_candidates": [], "open_questions": [],
        },
    )


def _noop_drafter(self, bb, **kwargs):
    bp = bb.read_yaml("genre_blueprint.yaml") or {}
    bp["era"] = {"content": "# NEW ERA (from blueprint)\n"}
    bp["writing_style_extra"] = {"content": "# NEW STYLE (from blueprint)\n"}
    bp["iron_laws_extra"] = {"content": "# NEW LAWS (from blueprint)\n"}
    bp["resource_schema"] = None
    bb.write_yaml("genre_blueprint.yaml", bp)


def test_extract_to_project_real_pipeline(fake_repo, monkeypatch):
    """Full pipeline runs; era.md gets overwritten; old files backed up."""
    from src.genre_extractor.agents import extractor as em
    from src.genre_extractor.agents import drafter as dm
    from src.genre_extractor.agents import fixer as fm
    from src.genre_extractor.auditors import (
        GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard,
    )
    monkeypatch.setattr(em.GenreExtractor, "run", _noop_extractor)
    monkeypatch.setattr(dm.GenreDrafter, "run", _noop_drafter)
    monkeypatch.setattr(fm.GenreFixer, "run", lambda self, bb, **k: None)
    for cls in (GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard):
        monkeypatch.setattr(cls, "run", lambda self, bb, **k: None)

    from src.genre_extractor import to_project
    result = to_project.extract_to_project(book_id="mybook", sources=["novel.txt"])

    book = fake_repo / "projects" / "mybook"

    # 1. build_status.yaml seeded and reached 'done' for extract phase.
    bs_path = book / "state" / ".extract_build" / "build_status.yaml"
    assert bs_path.exists(), "build_status.yaml not created"
    status = yaml.safe_load(bs_path.read_text(encoding="utf-8"))
    assert status["phases"]["extract"]["status"] == "done"

    # 2. era.md was overwritten with blueprint content (not stub, not OLD).
    era = (book / "era.md").read_text(encoding="utf-8")
    assert "NEW ERA" in era
    assert "OLD ERA" not in era

    # 3. Old file got backed up before overwrite.
    backups = list((book / "state" / ".backup").glob("era*"))
    assert backups, "no era backup created"
    assert any("OLD ERA" in p.read_text(encoding="utf-8") for p in backups)

    # 4. Return shape is as documented.
    assert result["book_id"] == "mybook"
