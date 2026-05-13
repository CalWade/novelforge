"""End-to-end integration test for extract_to_preset.

This test catches regressions the unit tests miss because they mock
``_run_full_extraction_to_blueprint`` wholesale. Here we mock only the
deepest agent LLM calls, so the real core.run_extract / run_merge /
run_draft orchestration runs — including the critical
``schemas.update_phase_status`` read at the top of run_extract, which
triggered a FileNotFoundError in production when build_status.yaml
wasn't seeded.

Regression guard: see bug fix for missing ``build_status.yaml`` seed
and for passing raw file handles instead of ChapterStream tuples to
``core.run_extract``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config

    (tmp_path / "presets").mkdir()
    (tmp_path / "novels").mkdir()
    # A minimal but chapter-marker-annotated novel so ChapterStream indexes
    # real chapters and run_extract gets work to do.
    (tmp_path / "novels" / "novel.txt").write_text(
        "第一章 序幕\n阿强走进茶餐厅。\n"
        "第二章 风起\n他见了老大。\n"
        "第三章 落幕\n尘埃落定。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def _noop_extractor_run(self, bb, **kwargs):
    """Stand-in for GenreExtractor.run — write a valid empty note, no LLM."""
    batch_id = kwargs["batch_id"]
    bb.write_yaml(
        f"extraction_notes/batch-{batch_id:03d}.yaml",
        {
            "batch_id": batch_id,
            "chapters_covered": [1, 1],
            "novel_source": "novel.txt",
            "extracted_at": "2026-01-01T00:00:00",
            "era_observations": [],
            "iron_law_candidates": [],
            "style_markers": [],
            "resource_candidates": [],
            "open_questions": [],
        },
    )


def _noop_drafter_run(self, bb, **kwargs):
    """Stand-in for GenreDrafter.run — write a minimal valid blueprint."""
    bp = bb.read_yaml("genre_blueprint.yaml") or {}
    bp.setdefault("era", {"content": "# era (stub)"})
    bp.setdefault("writing_style_extra", {"content": "# style (stub)"})
    bp.setdefault("iron_laws_extra", {"content": "# laws (stub)"})
    bp.setdefault("resource_schema", None)
    bb.write_yaml("genre_blueprint.yaml", bp)


def test_extract_to_preset_seeds_build_status_and_passes_streams(
    fake_repo, monkeypatch
):
    """Full pipeline runs without FileNotFoundError; build_status.yaml
    is created and reaches a coherent final state.

    Before the fix:
      - run_extract was called with raw file handles → TypeError on
        ``for stream, bs in source_streams`` unpack.
      - Even if unpack were fixed, schemas.update_phase_status reads
        build_status.yaml first → FileNotFoundError because the file
        was never seeded.
    """
    # Mock only the two LLM-calling agent entry points.
    from src.genre_extractor.agents import extractor as extractor_mod
    from src.genre_extractor.agents import drafter as drafter_mod

    monkeypatch.setattr(
        extractor_mod.GenreExtractor, "run", _noop_extractor_run
    )
    monkeypatch.setattr(
        drafter_mod.GenreDrafter, "run", _noop_drafter_run
    )

    # Neutralise the Validator's LLM auditors + fixer so we don't need real LLMs.
    from src.genre_extractor.auditors import (
        GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard,
    )
    for cls in (GenreConsistencyGuard, GenreFactChecker, GenreStyleGuard):
        monkeypatch.setattr(cls, "run", lambda self, bb, **kw: None)
    from src.genre_extractor.agents import fixer as fixer_mod
    monkeypatch.setattr(fixer_mod.GenreFixer, "run", lambda self, bb, **kw: None)

    from src.genre_extractor import to_preset

    result = to_preset.extract_to_preset(
        preset_id="integration_test",
        sources=["novel.txt"],
    )

    # 1. Did not raise FileNotFoundError — reaching this line is already
    #    a big part of the assertion.
    assert result["preset_id"] == "integration_test"

    # 2. build_status.yaml actually got created under .build/.
    build_status_path = (
        fake_repo / "presets" / "integration_test" / ".build" / "build_status.yaml"
    )
    assert build_status_path.exists(), (
        "build_status.yaml was not created — run_extract likely crashed "
        "before update_phase_status could write it."
    )

    # 3. Its content is coherent: valid YAML with the expected top-level
    #    keys and an ``extract`` phase that reached ``done``.
    status = yaml.safe_load(build_status_path.read_text(encoding="utf-8"))
    assert status["genre_id"] == "integration_test"
    assert status["entry"] == "extract-to-preset"
    assert "phases" in status
    assert "extract" in status["phases"]
    # After a successful run_extract, the extract phase must be done.
    assert status["phases"]["extract"]["status"] == "done"
    # novel_sources was seeded with total_chapters metadata
    assert len(status["novel_sources"]) == 1
    assert status["novel_sources"][0]["total_chapters"] >= 1
    assert status["novel_sources"][0]["batch_size"] == 25
