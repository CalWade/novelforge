"""Regression guard: ``with_trial=True`` must not AttributeError.

Historical bug: ``to_preset.extract_to_preset(..., with_trial=True)``
called ``trial.run_trial_against_preset``, and
``to_project.extract_to_project(..., with_trial=True)`` called
``trial.run_trial_against_project`` — neither function exists. Any user
ticking the "run trial book" box crashed with AttributeError 100% of
the time. Fix: use the canonical ``trial.run_trial(genre_id, bb,
chapters=3)`` for presets and skip-with-info for projects.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "novel.txt").write_text(
        "第一章 a\n第二章 b\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def _stub_all_leaf_agents(monkeypatch):
    """Neutralise every LLM caller the extract pipeline touches."""
    from src.genre_extractor.agents import extractor as em, drafter as dm, fixer as fm
    from src.genre_extractor.auditors import (
        GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard,
    )

    def _noop_extract(self, bb, **k):
        bid = k["batch_id"]
        bb.write_yaml(
            f"extraction_notes/batch-{bid:03d}.yaml",
            {"batch_id": bid, "chapters_covered": [1, 1],
             "novel_source": "novel.txt", "extracted_at": "2026-01-01T00:00:00",
             "era_observations": [], "iron_law_candidates": [],
             "style_markers": [], "resource_candidates": [], "open_questions": []},
        )

    def _noop_draft(self, bb, **k):
        bp = bb.read_yaml("genre_blueprint.yaml") or {}
        bp.update({"era": {"content": "# e"}, "writing_style_extra": {"content": "# s"},
                   "iron_laws_extra": {"content": "# l"}, "resource_schema": None})
        bb.write_yaml("genre_blueprint.yaml", bp)

    monkeypatch.setattr(em.GenreExtractor, "run", _noop_extract)
    monkeypatch.setattr(dm.GenreDrafter, "run", _noop_draft)
    monkeypatch.setattr(fm.GenreFixer, "run", lambda self, bb, **k: None)
    for cls in (GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard):
        monkeypatch.setattr(cls, "run", lambda self, bb, **k: None)


def test_extract_to_preset_with_trial_does_not_crash(fake_repo, monkeypatch):
    _stub_all_leaf_agents(monkeypatch)

    # Keep trial.run_trial inert (it has its own bootstrap/LLM machinery
    # we don't want to exercise here — this test is about the call
    # plumbing, not about the trial itself).
    from src.genre_extractor import trial
    called = {}
    def fake_run_trial(genre_id, bb, chapters=3, **kw):
        called["genre_id"] = genre_id
        called["chapters"] = chapters
    monkeypatch.setattr(trial, "run_trial", fake_run_trial)

    from src.genre_extractor import to_preset
    # Must NOT raise AttributeError — that was the whole historical bug.
    result = to_preset.extract_to_preset(
        preset_id="wp", sources=["novel.txt"], with_trial=True,
    )
    assert result["preset_id"] == "wp"
    # Canonical trial.run_trial(preset_id, bb, chapters=3) was invoked.
    assert called == {"genre_id": "wp", "chapters": 3}


def test_extract_to_project_with_trial_produces_skip_info(fake_repo, monkeypatch):
    """Book path can't host a trial (trial requires PRESETS_DIR); we skip
    with an info record instead of crashing or silently dropping it."""
    # Seed a book dir the way test_extract_to_project does.
    book = fake_repo / "projects" / "pb"
    book.mkdir()
    for fname, body in (
        ("project.yaml", "id: pb\nprotagonist_name: x\n"),
        ("outline.json", "{}"), ("characters.yaml", "{}"),
        ("timeline.yaml", "{}"), ("era.md", "e\n"),
        ("writing-style-extra.md", "s\n"), ("iron-laws-extra.md", "l\n"),
    ):
        (book / fname).write_text(body, encoding="utf-8")
    (book / "state").mkdir()

    _stub_all_leaf_agents(monkeypatch)

    from src.genre_extractor import to_project
    result = to_project.extract_to_project(
        book_id="pb", sources=["novel.txt"], with_trial=True,
    )
    assert result["book_id"] == "pb"

    # Info record written to genre_issues.jsonl inside the build dir.
    issues_path = book / "state" / ".extract_build" / "genre_issues.jsonl"
    assert issues_path.exists()
    lines = [ln for ln in issues_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    import json
    records = [json.loads(ln) for ln in lines]
    trial_notes = [r for r in records if r.get("file") == "(trial)"]
    assert trial_notes, "no (trial) record written for skipped trial"
    assert any(r.get("severity") == "info" and "暂不支持" in r.get("message", "")
               for r in trial_notes)
