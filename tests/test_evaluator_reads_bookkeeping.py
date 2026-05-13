"""Tests for P0-4: Evaluator reads Lesson-3 bookkeeping files
(state/current_status_card.md + state/pending_hooks.md).

Why: status_card_updater.py documents that the "已知真相" table is the
Evaluator's primary basis for judging "反派信息越界". If Evaluator doesn't
actually read those files, the Lesson-3 three-tier bookkeeping ROI is wasted.
This test suite locks in the reader behavior.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.evaluator import Evaluator


def _seed_minimum(tmp_path: Path) -> Blackboard:
    """Seed a Blackboard with the minimum files Evaluator._build_prompts requires."""
    b = Blackboard(root=tmp_path)
    b.write_yaml(
        "setting.yaml",
        {"genre": "港综同人", "era": "1983"},
    )
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "林家耀"}, "supporting": []},
    )
    b.write_text("timeline.yaml", "1983: []\n")
    b.write_text("iron-laws-extra.md", "## iron_law_extra_1 洋人不跪舔\n")
    (tmp_path / "chapters").mkdir(exist_ok=True)
    b.write_text(
        "chapters/ch001.md",
        "# 第一章\n林家耀走出茶餐厅，心里想着那笔黑金交易。\n",
    )
    return b


# ---------------- Case A: bookkeeping files present ----------------


def test_evaluator_reads_status_card_when_present(tmp_path):
    b = _seed_minimum(tmp_path)
    status_card_content = (
        "# 当前状态卡\n\n"
        "## 当前已知真相（谁知道什么）\n\n"
        "| 信息项 | 主角知否 | 反派知否 | 读者知否 | 其他关键人知否 |\n"
        "|---|---|---|---|---|\n"
        "| 黑金交易地点 | 是 | 否 | 是 | 否 |\n"
    )
    b.write_text("current_status_card.md", status_card_content)

    _, user, inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "state/current_status_card.md" in inputs
    # Content must actually appear in the user prompt (not just a placeholder)
    assert "当前已知真相" in user
    assert "黑金交易地点" in user


def test_evaluator_reads_pending_hooks_when_present(tmp_path):
    b = _seed_minimum(tmp_path)
    hooks_content = (
        "# 活跃伏笔池\n\n"
        "| hook_id | 起始章 | 类型 | 当前状态 |\n"
        "|---|---|---|---|\n"
        "| hook_001_洋人警司暗线 | 1 | 暗线身份 | 待推进 |\n"
    )
    b.write_text("pending_hooks.md", hooks_content)

    _, user, inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "state/pending_hooks.md" in inputs
    assert "活跃伏笔池" in user
    assert "hook_001_洋人警司暗线" in user


def test_evaluator_reads_both_bookkeeping_files_in_independent_sections(tmp_path):
    b = _seed_minimum(tmp_path)
    b.write_text(
        "current_status_card.md",
        "# 当前状态卡\n\n## 主角当前状态\n姓名: 林家耀\n",
    )
    b.write_text(
        "pending_hooks.md",
        "# 活跃伏笔池\n\n| hook_id |\n|---|\n| hook_A |\n",
    )

    _, user, inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "state/current_status_card.md" in inputs
    assert "state/pending_hooks.md" in inputs

    # Both content strings present and in separate sections (not merged into
    # characters.yaml block).
    status_idx = user.find("current_status_card.md")
    hooks_idx = user.find("pending_hooks.md")
    chars_idx = user.find("characters.yaml")
    assert status_idx != -1 and hooks_idx != -1 and chars_idx != -1
    # The bookkeeping sections must come AFTER characters.yaml (i.e. their own block)
    assert status_idx > chars_idx
    assert hooks_idx > chars_idx


def test_evaluator_system_prompt_references_bookkeeping_rules(tmp_path):
    """When bookkeeping is present, the system prompt's cross-validation
    section must instruct the LLM on how to use it."""
    b = _seed_minimum(tmp_path)
    b.write_text("current_status_card.md", "# 当前状态卡\n")
    b.write_text("pending_hooks.md", "# 活跃伏笔池\n")

    system, _, _ = Evaluator()._build_prompts(b, chapter=1)

    assert "current_status_card.md" in system
    assert "pending_hooks.md" in system
    # Key guidance: villain-info-overreach must hit landmine_10
    assert "landmine_10" in system
    assert "反派" in system


# ---------------- Case B: bookkeeping files absent ----------------


def test_evaluator_does_not_crash_when_status_card_missing(tmp_path):
    b = _seed_minimum(tmp_path)
    # Nothing written. Must not raise.
    system, user, inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "state/current_status_card.md" not in inputs
    assert "state/pending_hooks.md" not in inputs
    # The user prompt should NOT embed an empty bookkeeping section header —
    # otherwise the LLM sees a ghost section and may fabricate violations.
    assert "当前时间点权威状态卡" not in user
    assert "活跃伏笔池" not in user


def test_evaluator_does_not_crash_when_status_card_is_empty_file(tmp_path):
    """An empty (whitespace-only) file should behave like a missing file."""
    b = _seed_minimum(tmp_path)
    b.write_text("current_status_card.md", "   \n\n")
    b.write_text("pending_hooks.md", "")

    _, user, inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "state/current_status_card.md" not in inputs
    assert "state/pending_hooks.md" not in inputs
    assert "当前时间点权威状态卡" not in user


def test_evaluator_inputs_read_stays_minimal_without_bookkeeping(tmp_path):
    """Regression: without bookkeeping, inputs_read should match the pre-P0-4 baseline."""
    b = _seed_minimum(tmp_path)
    _, _, inputs = Evaluator()._build_prompts(b, chapter=1)

    expected_baseline = {
        "state/chapters/ch001.md",
        "state/characters.yaml",
        "state/timeline.yaml",
        "state/iron-laws-extra.md",
        "rules/18-landmines.md",
        "rules/24-iron-laws.md",
        "rules/00-information-priority.md",
    }
    assert set(inputs) == expected_baseline
