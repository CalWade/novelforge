"""create_blank_preset — sync scaffolding, no LLM."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def test_create_blank_preset_writes_four_files(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    out = create_blank_preset("myblank", display_name="My Blank", tone="dry")
    preset_dir = fake_repo / "presets" / "myblank"
    assert out == preset_dir
    for fname in ("genre.yaml", "era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        assert (preset_dir / fname).exists(), f"{fname} missing"


def test_create_blank_preset_genre_yaml_shape(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("myblank", display_name="My Blank", tone="冷硬")
    data = yaml.safe_load(
        (fake_repo / "presets" / "myblank" / "genre.yaml").read_text(encoding="utf-8")
    )
    assert data["id"] == "myblank"
    assert data["display_name"] == "My Blank"
    assert data["tone"] == "冷硬"
    assert data["source"] == "blank"


def test_create_blank_preset_md_files_have_todo_placeholder(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        content = (fake_repo / "presets" / "p" / fname).read_text(encoding="utf-8")
        assert "TODO" in content or "待填写" in content


def test_create_blank_preset_creates_empty_novels_dir(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    novels = fake_repo / "presets" / "p" / "novels"
    assert novels.exists()
    assert (novels / ".gitkeep").exists()


def test_create_blank_preset_refuses_existing(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("dup", display_name="D", tone="")
    with pytest.raises(FileExistsError, match="already exists"):
        create_blank_preset("dup", display_name="D2", tone="")


def test_create_blank_preset_validates_id(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    with pytest.raises(ValueError, match="id"):
        create_blank_preset("Bad Id", display_name="X", tone="")
    with pytest.raises(ValueError, match="id"):
        create_blank_preset("", display_name="X", tone="")


def test_create_blank_preset_no_resource_schema(fake_repo):
    """Blank preset deliberately omits resource_schema — user adds if needed."""
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    assert not (fake_repo / "presets" / "p" / "resource_schema.yaml").exists()
