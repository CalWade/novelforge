"""extract_from_description — single LLM call, no novels."""
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


@pytest.fixture
def stub_llm_valid(monkeypatch):
    """LLM returns a valid blueprint YAML."""
    canned = yaml.safe_dump({
        "era": "# 港综 1983\n\n1983 年香港，经济起飞前夜……",
        "writing_style_extra": "# Style\n粤语俚语 / 冷硬快切",
        "iron_laws_extra": "# Laws\n- 不许出现智能手机",
        "resource_schema": None,
    }, allow_unicode=True)

    def fake_chat(system, user, *, agent_name, **kwargs):
        return canned
    monkeypatch.setattr("src.llm.chat", fake_chat)


@pytest.fixture
def stub_llm_with_schema(monkeypatch):
    """LLM returns blueprint including resource_schema."""
    canned = yaml.safe_dump({
        "era": "# Xianxia era",
        "writing_style_extra": "# style",
        "iron_laws_extra": "# laws",
        "resource_schema": {
            "resources": [
                {"name": "spirit_stone", "unit": "颗", "visibility": "public"},
            ]
        },
    }, allow_unicode=True)
    def fake_chat(system, user, *, agent_name, **kwargs):
        return canned
    monkeypatch.setattr("src.llm.chat", fake_chat)


@pytest.fixture
def stub_llm_bad(monkeypatch):
    def fake_chat(system, user, *, agent_name, **kwargs):
        return "not valid yaml at all {[}"
    monkeypatch.setattr("src.llm.chat", fake_chat)


def test_extract_from_description_writes_three_md(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    result = extract_from_description(
        "port", display_name="Port HK", tone="hard-boiled",
        description="港综 1983 冷硬…",
    )
    preset_dir = fake_repo / "presets" / "port"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md", "genre.yaml"):
        assert (preset_dir / fname).exists()
    assert not (preset_dir / "resource_schema.yaml").exists()
    assert result["preset_id"] == "port"


def test_extract_from_description_produces_schema_when_llm_says_so(fake_repo, stub_llm_with_schema):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description(
        "xianxia", display_name="Xianxia", tone="仙侠",
        description="仙侠，有灵石可追踪",
    )
    preset_dir = fake_repo / "presets" / "xianxia"
    assert (preset_dir / "resource_schema.yaml").exists()
    schema = yaml.safe_load((preset_dir / "resource_schema.yaml").read_text(encoding="utf-8"))
    assert "resources" in schema


def test_extract_from_description_genre_yaml_source_field(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description(
        "p", display_name="P", tone="", description="…",
    )
    data = yaml.safe_load((fake_repo / "presets" / "p" / "genre.yaml").read_text(encoding="utf-8"))
    assert data["source"] == "description"


def test_extract_from_description_refuses_existing(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description("dup", display_name="D", tone="", description="a")
    with pytest.raises(FileExistsError):
        extract_from_description("dup", display_name="D2", tone="", description="b")


def test_extract_from_description_empty_desc_rejects(fake_repo):
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="description"):
        extract_from_description("p", display_name="P", tone="", description="")


def test_extract_from_description_validates_id(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="id"):
        extract_from_description("Bad Id", display_name="X", tone="", description="…")


def test_extract_from_description_llm_bad_output_raises(fake_repo, stub_llm_bad):
    """Bad LLM output must raise, not silently produce garbage."""
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="LLM output"):
        extract_from_description("p", display_name="P", tone="", description="…")
    # preset dir should NOT exist after failed call
    assert not (fake_repo / "presets" / "p").exists()


def test_extract_from_description_creates_empty_novels(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description("p", display_name="P", tone="", description="…")
    assert (fake_repo / "presets" / "p" / "novels" / ".gitkeep").exists()
