"""Tests for the decoupled extraction core. Exercises functions that operate
purely on a Blackboard, without caring whether the artifacts land in a project
or in a preset.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_count_chapters_in_text_simple():
    from src.genre_extractor.core import count_chapters_in_text
    text = "第一章 abc\n第二章 def\n第三章 ghi\n"
    assert count_chapters_in_text(text) == 3


def test_split_text_into_batches_respects_adaptive(tmp_path: Path):
    from src.genre_extractor.core import split_text_into_batches
    text = "\n".join(f"第{i}章 content" for i in range(1, 31))
    batches = split_text_into_batches(text, batch_size=10)
    assert len(batches) == 3


def test_render_files_from_blueprint_writes_to_custom_dir(tmp_path: Path):
    """render_files_from_blueprint must use the out_dir we pass, not a hard-coded path."""
    from src.genre_extractor.core import render_files_from_blueprint

    blueprint = {
        "era": {"content": "# Era\nyear 1983"},
        "writing_style_extra": {"content": "# Style\nshort sentences"},
        "iron_laws_extra": {"content": "# Laws\n- obey"},
        "resource_schema": None,
    }
    out_dir = tmp_path / "target"
    out_dir.mkdir()
    render_files_from_blueprint(blueprint, out_dir=out_dir)

    assert (out_dir / "era.md").read_text(encoding="utf-8").startswith("# Era")
    assert (out_dir / "writing-style-extra.md").exists()
    assert (out_dir / "iron-laws-extra.md").exists()
    assert not (out_dir / "resource_schema.yaml").exists()


def test_render_files_writes_resource_schema_when_present(tmp_path: Path):
    from src.genre_extractor.core import render_files_from_blueprint
    blueprint = {
        "era": {"content": "# E"},
        "writing_style_extra": {"content": "# S"},
        "iron_laws_extra": {"content": "# L"},
        "resource_schema": {"resources": [{"name": "gold", "unit": "coin"}]},
    }
    render_files_from_blueprint(blueprint, out_dir=tmp_path)
    schema_text = (tmp_path / "resource_schema.yaml").read_text(encoding="utf-8")
    assert "gold" in schema_text


def test_render_files_purges_stale_schema(tmp_path: Path):
    """If out_dir already has resource_schema.yaml but new blueprint has none, remove it."""
    from src.genre_extractor.core import render_files_from_blueprint
    (tmp_path / "resource_schema.yaml").write_text("stale: true\n", encoding="utf-8")
    blueprint = {
        "era": {"content": "#"}, "writing_style_extra": {"content": "#"},
        "iron_laws_extra": {"content": "#"}, "resource_schema": None,
    }
    render_files_from_blueprint(blueprint, out_dir=tmp_path)
    assert not (tmp_path / "resource_schema.yaml").exists()
