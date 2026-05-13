"""Regression guard: ``pipeline.run_phase(preset_id, phase="draft")``
must really render the blueprint to disk, not silently no-op.

Historical bug: ``_run_draft`` delegated to ``_render_files_from_blueprint``,
a stub-only helper that skips any file that already exists. Users running
``--draft-only`` got ``{"ok": true}`` back but era.md was never updated
from the freshly-produced blueprint. Fixed to call
``core.render_files_from_blueprint`` instead.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def test_run_phase_draft_overwrites_era_with_blueprint_content(fake_repo, monkeypatch):
    from src import config
    from src.genre_extractor import pipeline, schemas
    from src.genre_extractor.agents import drafter as dm

    preset_id = "p_draft"
    preset_dir = config.PRESETS_DIR / preset_id
    preset_dir.mkdir()
    # Pre-existing era.md with "OLD" content — a passing draft phase
    # must replace this with the blueprint's content.
    (preset_dir / "era.md").write_text("OLD ERA CONTENT\n", encoding="utf-8")
    (preset_dir / "writing-style-extra.md").write_text("OLD STYLE\n", encoding="utf-8")
    (preset_dir / "iron-laws-extra.md").write_text("OLD LAWS\n", encoding="utf-8")

    # Seed build_status.yaml and genre_blueprint.yaml inside .build/.
    build_dir = preset_dir / ".build"
    build_dir.mkdir()
    from src.core.blackboard import Blackboard
    bb = Blackboard(root=build_dir)
    bb.write_yaml("build_status.yaml", schemas.make_initial_build_status(
        genre_id=preset_id, entry="run-phase-test", novel_sources=[],
    ))
    # Note: core.run_draft unconditionally resets genre_blueprint.yaml to
    # an empty skeleton before calling GenreDrafter.run. So the drafter
    # stub must write the "NEW" content itself — exactly what the real
    # drafter does.

    def _stub_drafter_populates_blueprint(self, bb, **kw):
        bp = bb.read_yaml("genre_blueprint.yaml") or {}
        bp["era"] = {"content": "NEW ERA CONTENT\n"}
        bp["writing_style_extra"] = {"content": "NEW STYLE\n"}
        bp["iron_laws_extra"] = {"content": "NEW LAWS\n"}
        bp["resource_schema"] = None
        bb.write_yaml("genre_blueprint.yaml", bp)

    monkeypatch.setattr(dm.GenreDrafter, "run", _stub_drafter_populates_blueprint)

    result = pipeline.run_phase(preset_id, phase="draft")
    assert result == {"ok": True, "preset_id": preset_id, "phase": "draft"}

    # The critical assertion: era.md is no longer "OLD", it's "NEW".
    era = (preset_dir / "era.md").read_text(encoding="utf-8")
    assert "NEW ERA CONTENT" in era, (
        f"draft phase did not render blueprint to era.md; got:\n{era!r}"
    )
    assert "OLD ERA CONTENT" not in era, (
        "draft phase kept the OLD content — _run_draft still no-ops"
    )
    # And the other two files also got updated (proves the whole
    # render_files_from_blueprint loop ran, not just era).
    assert "NEW STYLE" in (preset_dir / "writing-style-extra.md").read_text(encoding="utf-8")
    assert "NEW LAWS" in (preset_dir / "iron-laws-extra.md").read_text(encoding="utf-8")


def test_audit_preset_raises_on_unknown_preset(fake_repo):
    """Bug 3 guard: audit_preset must fail fast on nonexistent preset."""
    from src.genre_extractor import pipeline
    with pytest.raises(FileNotFoundError, match="preset not found"):
        pipeline.audit_preset("does-not-exist")


def test_run_phase_raises_on_unknown_preset(fake_repo):
    """Bug 3 guard: run_phase must fail fast on nonexistent preset."""
    from src.genre_extractor import pipeline
    with pytest.raises(FileNotFoundError, match="preset not found"):
        pipeline.run_phase("does-not-exist", phase="merge")


def test_run_phase_extract_raises_when_novel_sources_empty(fake_repo, monkeypatch):
    """Bug 4 guard: run_phase(phase='extract') with no resolvable novel_sources
    must raise ValueError, not silently succeed."""
    from src import config
    from src.genre_extractor import pipeline, schemas
    from src.core.blackboard import Blackboard

    preset_id = "p_empty"
    preset_dir = config.PRESETS_DIR / preset_id
    preset_dir.mkdir()
    build_dir = preset_dir / ".build"
    build_dir.mkdir()
    bb = Blackboard(root=build_dir)
    # build_status.yaml exists but has zero novel_sources.
    bb.write_yaml("build_status.yaml", schemas.make_initial_build_status(
        genre_id=preset_id, entry="test", novel_sources=[],
    ))

    with pytest.raises(ValueError, match="novel_sources"):
        pipeline.run_phase(preset_id, phase="extract")
