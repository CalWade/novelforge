"""Tests for rules + AGENTS.md consistency (the "documentation is code" contract)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src import config


# -------- rules/00-information-priority.md (B-1) --------

def test_information_priority_rule_exists():
    p = config.RULES_DIR / "00-information-priority.md"
    assert p.exists(), f"missing {p}"


def test_information_priority_rule_has_key_sections():
    text = (config.RULES_DIR / "00-information-priority.md").read_text(encoding="utf-8")
    for needle in (
        "信息源优先级",
        "优先级",  # the priority table must be called out
        "state/current_status_card.md",
        "state/chapters/",
        "outline.json",
        "rules/24-iron-laws.md",
    ):
        assert needle in text, f"missing: {needle}"


def test_information_priority_has_arbitration_rules():
    text = (config.RULES_DIR / "00-information-priority.md").read_text(encoding="utf-8")
    # R1..R5 arbitration rules should all be present
    for rule_id in ("R1", "R2", "R3", "R4", "R5"):
        assert f"{rule_id} ·" in text or f"{rule_id}\n" in text or f"{rule_id} " in text


# -------- AGENTS.md inventory must be in sync with code --------

def test_agents_md_lists_all_new_agents():
    text = (config.PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # All bookkeeping agents mentioned in state-map + agent-roster
    for agent_marker in (
        "StatusCardUpdater",
        "HookKeeper",
        "ResourceLedger",
    ):
        assert agent_marker in text, f"AGENTS.md missing {agent_marker}"


def test_agents_md_lists_all_new_state_files():
    text = (config.PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for filepath in (
        "state/current_status_card.md",
        "state/pending_hooks.md",
        "state/resource_schema.yaml",
        "state/resource_ledger.md",
    ):
        assert filepath in text, f"AGENTS.md missing {filepath}"


def test_agents_md_state_map_mentions_optional_resource_schema():
    """The state map row for resource_schema.yaml should call out 可选/optional."""
    text = (config.PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # Look for optional/可选 near resource_schema in the state-map table
    idx = text.find("state/resource_schema.yaml")
    assert idx >= 0
    window = text[idx:idx + 300]
    assert "可选" in window or "optional" in window.lower()


# -------- setting lint still passes on all real settings --------

@pytest.mark.parametrize(
    "setting_name",
    ["gangster-hk-1983", "xianxia-ascension", "urban-romance-contemporary"],
)
def test_real_settings_pass_lint(setting_name):
    from src.tools.setting_lint import lint_setting
    r = lint_setting(config.PROJECT_ROOT / "settings" / setting_name)
    assert r.n_errors == 0, f"{setting_name} lint errors: {[i.message for i in r.issues if i.level == 'ERROR']}"


# -------- README / settings/README / AGENTS.md doc freshness --------

def test_readme_lists_all_three_settings():
    """Top-level README must mention all 3 real settings."""
    text = (config.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for setting in ("gangster-hk-1983", "xianxia-ascension", "urban-romance-contemporary"):
        assert setting in text, f"README.md missing mention of {setting}"


def test_readme_mentions_bookkeeping_agents():
    """Top-level README should advertise the three bookkeeping agents and
    the Intent Router CLI flags so users know the feature exists."""
    text = (config.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for marker in (
        "StatusCardUpdater",
        "HookKeeper",
        "ResourceLedger",
        "--plan-only",
        "--bookkeeping-only",
        "current_status_card.md",
        "pending_hooks.md",
    ):
        assert marker in text, f"README.md missing feature advertisement: {marker}"


def test_readme_does_not_claim_two_settings_anymore():
    """Guards against regressions like 'tested 2 settings' when we have 3."""
    text = (config.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    # These regressions existed until this commit; keep them from coming back.
    bad_phrases = [
        "2 个题材 × 各 3 章",
        "内置两个示例",
        "6 个黑板 I/O 测试",
    ]
    for phrase in bad_phrases:
        assert phrase not in text, (
            f"README.md contains outdated phrase '{phrase}' — "
            "doc is now out of sync with the code"
        )


def test_settings_readme_mentions_optional_resource_schema():
    """settings/README.md should explain the 7-required + 1-optional file layout."""
    text = (config.PROJECT_ROOT / "settings" / "README.md").read_text(encoding="utf-8")
    assert "resource_schema.yaml" in text
    assert "可选" in text or "optional" in text.lower()
    # Table row for urban-romance
    assert "urban-romance-contemporary" in text


def test_agents_md_mentions_optional_resource_schema():
    text = (config.PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # Setting section explains 7 + 1 optional
    assert "7 个必需文件" in text or "7 个文件" in text
    # Must also call out the optional flag so readers don't assume 8 are required
    idx = text.find("resource_schema.yaml")
    assert idx >= 0
    window = text[max(0, idx - 200):idx + 200]
    assert "可选" in window or "optional" in window.lower()
