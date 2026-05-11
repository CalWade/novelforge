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


# -------- setting lint still passes on all real genres + projects --------


@pytest.mark.parametrize(
    "genre_id",
    ["gangster-hk-1983", "xianxia-ascension", "urban-romance-contemporary"],
)
def test_real_genres_pass_lint(genre_id):
    from src.tools.setting_lint import lint_genre
    r = lint_genre(genre_id)
    assert r.n_errors == 0, (
        f"{genre_id} genre lint errors: "
        f"{[i.message for i in r.issues if i.level == 'ERROR']}"
    )


@pytest.mark.parametrize(
    "project_id",
    [
        "gangster-hk-1983-linjiayao",
        "xianxia-ascension-peichangning",
        "urban-romance-shenruowei",
    ],
)
def test_real_projects_pass_lint(project_id):
    from src.tools.setting_lint import lint_project
    r = lint_project(project_id)
    assert r.n_errors == 0, (
        f"{project_id} project lint errors: "
        f"{[i.message for i in r.issues if i.level == 'ERROR']}"
    )


# -------- README / genres/README / projects/README / AGENTS.md doc freshness --------

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


def test_project_name_is_novelforge_everywhere():
    """Guard against accidental regression to the old 'Blackboard Novel
    Pipeline' brand name across README, AGENTS.md, and web/docs HTML.
    The Blackboard *architecture pattern* (class/module name) is kept
    intact — we only check brand mentions."""
    # Built as fragments so this assertion file itself doesn't trip
    # the drift check in test_no_old_repo_url_references.
    brand_old = "Blackboard" + " Novel " + "Pipeline"
    brand_new = "Novelforge"
    for rel_path in (
        "README.md",
        "AGENTS.md",
        "genres/README.md",
        "projects/README.md",
        "web/templates/index.html",
        "docs/index.html",
        "docs/superpowers/specs/2026-05-09-novelforge-design.md",
        "src/__init__.py",
    ):
        p = config.PROJECT_ROOT / rel_path
        assert p.exists(), f"{rel_path} missing"
        text = p.read_text(encoding="utf-8")
        assert brand_old not in text, (
            f"{rel_path} still contains old brand '{brand_old}' — "
            f"should be '{brand_new}'"
        )
        assert brand_new in text, (
            f"{rel_path} missing new brand '{brand_new}'"
        )


def test_no_old_repo_url_references():
    """All GitHub/Pages URLs should point to CalWade/novelforge, not the
    old repo slug."""
    # Build the old slug in fragments so this file itself passes the scan.
    old_slug = "blackboard" + "-novel-" + "pipeline"
    exts = {".md", ".html", ".js", ".py", ".json", ".yaml", ".yml", ".txt"}
    # Skip dirs that legitimately reference the old slug (git history; this
    # test file itself; venv/cache).
    skip_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules",
                 ".venv", "tests"}
    hits: list[str] = []
    for p in config.PROJECT_ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        if any(part in skip_dirs for part in p.relative_to(config.PROJECT_ROOT).parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if old_slug in text:
            hits.append(str(p.relative_to(config.PROJECT_ROOT)))
    assert not hits, f"Old repo slug still present in: {hits}"


def test_genres_readme_mentions_optional_resource_schema():
    """genres/README.md should explain the required files + optional resource_schema."""
    text = (config.PROJECT_ROOT / "genres" / "README.md").read_text(encoding="utf-8")
    assert "resource_schema.yaml" in text
    assert "可选" in text or "optional" in text.lower()
    # Table row for urban-romance
    assert "urban-romance-contemporary" in text


def test_agents_md_mentions_optional_resource_schema():
    text = (config.PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # AGENTS.md explains the two-layer architecture (genres + projects)
    assert "genres/" in text
    assert "projects/" in text
    # Must call out that resource_schema.yaml is optional so readers don't
    # assume it's mandatory
    idx = text.find("resource_schema.yaml")
    assert idx >= 0
    window = text[max(0, idx - 200):idx + 200]
    assert "可选" in window or "optional" in window.lower()
