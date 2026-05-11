"""pytest-style tests for ResourceLedger (C-24)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.resource_ledger import (
    ResourceLedger,
    read_resource_ledger,
    setting_has_resource_schema,
)


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    (tmp_path / "chapters").mkdir(exist_ok=True)
    return b


# -------- setting_has_resource_schema --------

def test_setting_has_schema_false_when_missing(bb):
    assert setting_has_resource_schema(bb) is False


def test_setting_has_schema_true_when_present(bb):
    bb.write_yaml("resource_schema.yaml", {"resources": []})
    assert setting_has_resource_schema(bb) is True


# -------- prompt building --------

def test_build_prompts_raises_when_schema_missing(bb):
    bb.write_text("chapters/ch001.md", "text")
    with pytest.raises(RuntimeError, match="resource_schema"):
        ResourceLedger()._build_prompts(bb, chapter=1)


def test_build_prompts_ch1_without_prior_ledger(bb):
    bb.write_yaml(
        "resource_schema.yaml",
        {
            "resources": [
                {"id": "lingshi", "display_name": "灵石", "unit": "颗"},
            ],
            "validation": {
                "increment_rules": [{"threshold_3x": "rule"}],
                "forbidden_fuzzy_terms": ["暴涨"],
            },
        },
    )
    bb.write_text("chapters/ch001.md", "裴长宁得到了 10 颗灵石。")
    system, user, inputs = ResourceLedger()._build_prompts(bb, chapter=1)
    assert "资源账本员" in system
    assert "灵石" in system
    assert "首次生成" in user or "首章" in user
    assert "state/resource_schema.yaml" in inputs
    assert "state/resource_ledger.md" not in inputs


def test_build_prompts_ch2_with_prior_ledger(bb):
    bb.write_yaml("resource_schema.yaml", {"resources": [], "validation": {}})
    bb.write_text("resource_ledger.md", "# 资源账本 (resource_ledger.md)\n\n| x | y |")
    bb.write_text("chapters/ch002.md", "又得到 5 颗。")
    _, user, inputs = ResourceLedger()._build_prompts(bb, chapter=2)
    assert "state/resource_ledger.md" in inputs
    assert "上一版" in user


def test_build_prompts_forbids_plan_verdict_reads(bb):
    bb.write_yaml("resource_schema.yaml", {"resources": [], "validation": {}})
    bb.write_text("chapters/ch001.md", "text")
    system, _, _ = ResourceLedger()._build_prompts(bb, chapter=1)
    assert "不读" in system
    assert "plan" in system or "verdict" in system


def test_build_prompts_warns_about_fuzzy_terms(bb):
    bb.write_yaml(
        "resource_schema.yaml",
        {
            "resources": [],
            "validation": {
                "increment_rules": [],
                "forbidden_fuzzy_terms": ["暴涨", "海量"],
            },
        },
    )
    bb.write_text("chapters/ch001.md", "text")
    system, _, _ = ResourceLedger()._build_prompts(bb, chapter=1)
    assert "forbidden_fuzzy_terms" in system or "模糊" in system


# -------- output handling --------

def test_handle_output_strips_fence(bb):
    fenced = "```markdown\n# 资源账本 (resource_ledger.md)\n\n| x | y |\n```"
    ResourceLedger()._handle_output(bb, fenced, chapter=1)
    text = bb.read_text("resource_ledger.md")
    assert text.startswith("# 资源账本")
    assert "```" not in text


def test_handle_output_overwrites(bb):
    bb.write_text("resource_ledger.md", "OLD")
    ResourceLedger()._handle_output(bb, "# 资源账本 (resource_ledger.md)\n\nNEW", chapter=1)
    text = bb.read_text("resource_ledger.md")
    assert "OLD" not in text
    assert "NEW" in text


# -------- read_resource_ledger helper --------

def test_read_helper_exists_branch(bb):
    bb.write_text("resource_ledger.md", "# 资源账本")
    text, inputs = read_resource_ledger(bb)
    assert "资源账本" in text
    assert inputs == ["state/resource_ledger.md"]


def test_read_helper_missing_branch(bb):
    text, inputs = read_resource_ledger(bb)
    assert "未启用" in text or "尚未产出" in text
    assert inputs == []


# -------- real setting integration --------

@pytest.mark.parametrize(
    "setting_name",
    ["gangster-hk-1983", "xianxia-ascension"],
)
def test_real_genres_resource_schema_is_valid_yaml(setting_name):
    """Genres that declare resource schemas must have valid YAML with required structure."""
    import yaml
    from src import config
    schema_path = config.GENRES_DIR / setting_name / "resource_schema.yaml"
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "resources" in data
    assert isinstance(data["resources"], list)
    assert len(data["resources"]) >= 2, f"{setting_name} should declare ≥2 resources"
    # Each resource has id + display_name + unit + description
    for r in data["resources"]:
        for key in ("id", "display_name", "unit", "description"):
            assert key in r, f"{setting_name} resource missing {key}: {r}"
    assert "validation" in data
    assert "forbidden_fuzzy_terms" in data["validation"]
