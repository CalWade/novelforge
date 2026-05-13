"""P0-2 regression: extract_to_project must now run Validator → Fixer retry
loop against the book's own directory (not PRESETS_DIR).

We mock the LLM-driven extract/merge/draft steps so no LLM is called, and
deliberately render an era.md containing a Tier-1 deny phrase. After
extract_to_project returns, the build blackboard (``projects/<id>/state/.extract_build/``)
must contain a ``genre_issues.jsonl`` with at least one deny-phrase hit
tagged ``source=tier1-deny-scan``. That proves the Validator actually
walked the project directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config

    book = tmp_path / "projects" / "mybook"
    book.mkdir(parents=True)
    (book / "project.yaml").write_text(
        "id: mybook\ndisplay_name: Mine\nprotagonist_name: hero\nchapter_count_target: 3\n",
        encoding="utf-8",
    )
    (book / "outline.json").write_text("{}", encoding="utf-8")
    (book / "characters.yaml").write_text("{}", encoding="utf-8")
    (book / "timeline.yaml").write_text("{}", encoding="utf-8")
    (book / "era.md").write_text("old era\n", encoding="utf-8")
    (book / "writing-style-extra.md").write_text("old style\n", encoding="utf-8")
    (book / "iron-laws-extra.md").write_text("old laws\n", encoding="utf-8")
    (book / "state").mkdir()

    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "a.txt").write_text("第一章 a\n", encoding="utf-8")

    # Disable any real fixer LLM call while keeping the validator real.
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def test_extract_to_project_runs_validator_on_book_dir(fake_repo, monkeypatch):
    from src.genre_extractor import to_project

    # Render a blueprint whose era.md contains a deny phrase from
    # rules/deny-phrases-zh.txt. ``render_files_from_blueprint`` will write it
    # into projects/mybook/era.md; the Validator's Tier-1 scan must see it.
    def fake_blueprint(bb, sources, **_):
        return {
            "era": {"content": "时代背景：总而言之，这是一段占位文字。\n"},
            "writing_style_extra": {"content": "# style clean\n"},
            "iron_laws_extra": {"content": "# laws clean\n"},
            "resource_schema": None,
        }
    monkeypatch.setattr(to_project, "_run_full_extraction_to_blueprint", fake_blueprint)

    # Neutralise the 3 LLM auditors so only Tier-1 + setting_lint run.
    from src.genre_extractor.auditors import (
        GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard,
    )
    for cls in (GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard):
        monkeypatch.setattr(cls, "run", lambda self, bb, **kw: None)

    # Neutralise GenreFixer so ship_with_debt path doesn't need an LLM either.
    from src.genre_extractor.agents import fixer as fixer_mod
    monkeypatch.setattr(fixer_mod.GenreFixer, "run", lambda self, bb, **kw: None)

    to_project.extract_to_project(book_id="mybook", sources=["a.txt"])

    build_dir = fake_repo / "projects" / "mybook" / "state" / ".extract_build"
    issues_path = build_dir / "genre_issues.jsonl"
    assert issues_path.exists(), "Validator never wrote genre_issues.jsonl"

    # At least one Tier-1 deny-phrase issue must have been recorded — that's
    # proof the Validator read the project directory (not PRESETS_DIR, which
    # doesn't even exist in this fake repo).
    hits = []
    for raw in issues_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        hits.append(json.loads(raw))

    tier1 = [h for h in hits if h.get("source") == "tier1-deny-scan"]
    assert tier1, f"no Tier-1 deny-phrase hits in issues: {hits}"
    # Our planted phrase "总而言之" must be the one that tripped it.
    assert any("总而言之" in h.get("quote", "") for h in tier1)
    # scope id must be threaded through correctly
    assert all(h.get("genre_id") == "mybook" for h in tier1)


def test_extract_to_project_validator_does_not_touch_presets_dir(fake_repo, monkeypatch):
    """When files_dir is a project dir, PRESETS_DIR must not be read.

    We set PRESETS_DIR to a nonexistent path; if Validator still hardcoded it,
    we'd get a swallowed FileNotFoundError and no tier-1 issues.
    """
    from src import config
    from src.genre_extractor import to_project

    monkeypatch.setattr(config, "PRESETS_DIR", fake_repo / "does-not-exist")

    def fake_blueprint(bb, sources, **_):
        return {
            "era": {"content": "值得注意的是这里全是套话。\n"},
            "writing_style_extra": {"content": "# clean\n"},
            "iron_laws_extra": {"content": "# clean\n"},
            "resource_schema": None,
        }
    monkeypatch.setattr(to_project, "_run_full_extraction_to_blueprint", fake_blueprint)

    from src.genre_extractor.auditors import (
        GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard,
    )
    for cls in (GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard):
        monkeypatch.setattr(cls, "run", lambda self, bb, **kw: None)
    from src.genre_extractor.agents import fixer as fixer_mod
    monkeypatch.setattr(fixer_mod.GenreFixer, "run", lambda self, bb, **kw: None)

    to_project.extract_to_project(book_id="mybook", sources=["a.txt"])

    issues_path = (
        fake_repo / "projects" / "mybook" / "state" / ".extract_build" / "genre_issues.jsonl"
    )
    assert issues_path.exists()
    lines = [
        json.loads(l) for l in issues_path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    tier1 = [h for h in lines if h.get("source") == "tier1-deny-scan"]
    assert tier1, "Validator didn't find the deny phrase in project era.md"
