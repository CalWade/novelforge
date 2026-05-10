"""Tests for bootstrap handling of OPTIONAL_SETTING_FILES (C-24) and real
setting packs (integration: the built-in settings must all bootstrap clean).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src import bootstrap
from src.blackboard import Blackboard


def _seed_minimal_setting(
    setting_dir: Path, *, name: str = "test-setting", with_schema: bool = False
) -> None:
    setting_dir.mkdir(parents=True, exist_ok=True)
    (setting_dir / "setting.yaml").write_text(
        yaml.safe_dump(
            {
                "id": name,
                "display_name": name,
                "genre": "g",
                "era": "e",
                "tone": "t",
                "protagonist_name": "A",
                "chapter_count_target": 10,
                "chapters_in_outline": 1,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (setting_dir / "outline.json").write_text('{"chapters": [{"ch": 1, "title": "t"}]}', encoding="utf-8")
    (setting_dir / "timeline.yaml").write_text("2024: []\n", encoding="utf-8")
    (setting_dir / "characters.yaml").write_text("protagonist:\n  name: A\n", encoding="utf-8")
    (setting_dir / "era.md").write_text("era", encoding="utf-8")
    (setting_dir / "writing-style-extra.md").write_text("style", encoding="utf-8")
    (setting_dir / "iron-laws-extra.md").write_text("extra\n", encoding="utf-8")
    if with_schema:
        (setting_dir / "resource_schema.yaml").write_text(
            "resources: []\nvalidation:\n  increment_rules: []\n  forbidden_fuzzy_terms: []\n",
            encoding="utf-8",
        )


def test_validate_setting_reports_missing_required(tmp_path):
    d = tmp_path / "incomplete"
    d.mkdir()
    missing = bootstrap.validate_setting(d)
    # All 7 required files missing
    assert set(missing) == set(bootstrap.SETTING_FILES)


def test_validate_setting_passes_on_complete(tmp_path):
    _seed_minimal_setting(tmp_path / "s1")
    assert bootstrap.validate_setting(tmp_path / "s1") == []


def test_optional_resource_schema_is_copied_when_present(tmp_path, monkeypatch):
    # Build a fake setting with resource_schema
    src = tmp_path / "settings" / "with-schema"
    _seed_minimal_setting(src, name="with-schema", with_schema=True)

    # Use isolated state dir
    state = tmp_path / "state"
    state.mkdir()
    bb = Blackboard(root=state)

    # Monkey-patch PROJECT_ROOT to our tmp so list_settings sees our setting
    from src import config as cfg
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)

    # Simulate bootstrap inline (without invoking CLI argparse)
    setting_dir = tmp_path / "settings" / "with-schema"
    for fname in bootstrap.SETTING_FILES:
        shutil.copy2(setting_dir / fname, bb.root / fname)
    for fname in bootstrap.OPTIONAL_SETTING_FILES:
        src_f = setting_dir / fname
        dst_f = bb.root / fname
        if src_f.exists():
            shutil.copy2(src_f, dst_f)
        elif dst_f.exists():
            dst_f.unlink()

    assert (state / "resource_schema.yaml").exists()


def test_optional_resource_schema_is_removed_when_switching_setting(tmp_path):
    """Switching from a schema-providing setting to one without must purge old schema."""
    # Seed setting WITH schema
    with_schema = tmp_path / "settings" / "with-schema"
    _seed_minimal_setting(with_schema, name="with-schema", with_schema=True)
    # Seed setting WITHOUT schema
    without_schema = tmp_path / "settings" / "plain"
    _seed_minimal_setting(without_schema, name="plain", with_schema=False)

    state = tmp_path / "state"
    state.mkdir()
    bb = Blackboard(root=state)

    # Bootstrap 1: with schema
    for fname in bootstrap.SETTING_FILES:
        shutil.copy2(with_schema / fname, bb.root / fname)
    for fname in bootstrap.OPTIONAL_SETTING_FILES:
        src_f = with_schema / fname
        if src_f.exists():
            shutil.copy2(src_f, bb.root / fname)
    assert (state / "resource_schema.yaml").exists()

    # Bootstrap 2: switch to without-schema → should purge
    for fname in bootstrap.SETTING_FILES:
        shutil.copy2(without_schema / fname, bb.root / fname)
    for fname in bootstrap.OPTIONAL_SETTING_FILES:
        src_f = without_schema / fname
        dst_f = bb.root / fname
        if src_f.exists():
            shutil.copy2(src_f, dst_f)
        elif dst_f.exists():
            dst_f.unlink()
    assert not (state / "resource_schema.yaml").exists()


# ---- Real setting integration: all built-in settings must validate clean ----

@pytest.mark.parametrize(
    "setting_name",
    ["gangster-hk-1983", "xianxia-ascension", "urban-romance-contemporary"],
)
def test_real_settings_are_complete(setting_name):
    from src import config as cfg
    setting_dir = cfg.PROJECT_ROOT / "settings" / setting_name
    missing = bootstrap.validate_setting(setting_dir)
    assert missing == [], f"{setting_name} missing required files: {missing}"


@pytest.mark.parametrize(
    "setting_name,expected_has_schema",
    [
        ("gangster-hk-1983", True),
        ("xianxia-ascension", True),
        ("urban-romance-contemporary", False),  # romance is non-numeric
    ],
)
def test_real_settings_resource_schema_presence(setting_name, expected_has_schema):
    from src import config as cfg
    schema_path = cfg.PROJECT_ROOT / "settings" / setting_name / "resource_schema.yaml"
    assert schema_path.exists() == expected_has_schema, (
        f"{setting_name}: expected resource_schema.yaml present={expected_has_schema}, "
        f"got {schema_path.exists()}"
    )


# ---- prohibited_styles: all three real settings declare one ----

@pytest.mark.parametrize(
    "setting_name",
    ["gangster-hk-1983", "xianxia-ascension", "urban-romance-contemporary"],
)
def test_real_settings_declare_prohibited_styles(setting_name):
    from src import config as cfg
    setting_yaml = cfg.PROJECT_ROOT / "settings" / setting_name / "setting.yaml"
    data = yaml.safe_load(setting_yaml.read_text(encoding="utf-8"))
    styles = data.get("prohibited_styles", [])
    assert isinstance(styles, list)
    assert len(styles) >= 3, f"{setting_name} should declare at least 3 prohibited styles, got {styles}"
