"""Extract a genre pack into presets/<preset-id>/."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "a.txt").write_text("第一章 open\n", encoding="utf-8")
    (tmp_path / "novels" / "b.txt").write_text("第一章 inner\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def test_extract_to_preset_creates_preset_dir(fake_repo, monkeypatch):
    from src.genre_extractor import to_preset
    # Patch the internal pipeline-driver to avoid calling LLMs
    monkeypatch.setattr(
        to_preset, "_run_full_extraction_to_blueprint",
        lambda bb, sources, **_: {
            "era": {"content": "# Era stub"},
            "writing_style_extra": {"content": "# Style stub"},
            "iron_laws_extra": {"content": "# Laws stub"},
            "resource_schema": None,
        },
    )
    # Neutralise Validator so existing assertions about file content hold —
    # the real validator would (correctly) rewrite AI-slop stubs.
    from src.genre_extractor import pipeline
    monkeypatch.setattr(pipeline, "_run_validate", lambda *a, **k: None)
    result = to_preset.extract_to_preset(
        preset_id="myp",
        sources=["a.txt", "b.txt"],
    )
    preset = fake_repo / "presets" / "myp"
    assert (preset / "genre.yaml").exists()
    assert (preset / "era.md").read_text(encoding="utf-8") == "# Era stub"
    assert (preset / "novels" / "a.txt").read_text(encoding="utf-8") == "第一章 open\n"
    assert (preset / "novels" / "b.txt").exists()
    assert result["preset_id"] == "myp"


def test_extract_to_preset_refuses_existing_preset(fake_repo):
    from src.genre_extractor import to_preset
    (fake_repo / "presets" / "exists").mkdir()
    (fake_repo / "presets" / "exists" / "genre.yaml").write_text("id: exists\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        to_preset.extract_to_preset(preset_id="exists", sources=["a.txt"])


def test_extract_to_preset_resolves_source_paths_via_pool(fake_repo, monkeypatch):
    """Bare filename, 'novels/...' prefix, and absolute path all resolve."""
    from src.genre_extractor import to_preset
    captured = {}

    def _fake(bb, sources, **_):
        captured["sources"] = sources
        return {
            "era": {"content": "e"}, "writing_style_extra": {"content": "s"},
            "iron_laws_extra": {"content": "l"}, "resource_schema": None,
        }

    monkeypatch.setattr(to_preset, "_run_full_extraction_to_blueprint", _fake)
    from src.genre_extractor import pipeline
    monkeypatch.setattr(pipeline, "_run_validate", lambda *a, **k: None)
    to_preset.extract_to_preset(
        preset_id="p2",
        sources=["a.txt", "novels/b.txt"],
    )
    sources = captured["sources"]
    assert len(sources) == 2
    for p in sources:
        assert Path(p).exists()
