"""pytest-style tests for HookKeeper (C-25)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.hook_keeper import (
    HookKeeper,
    read_pending_hooks,
    PENDING_HOOKS_SKELETON,
)


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    b.write_yaml("setting.yaml", {"genre": "g", "era": "e"})
    b.write_yaml("characters.yaml", {"protagonist": {"name": "A"}})
    (tmp_path / "chapters").mkdir(exist_ok=True)
    return b


# -------- prompt-building branches --------

def test_prompt_ch1_empty_state(bb):
    bb.write_text("chapters/ch001.md", "ch1 text. 黑衣人跑了。")
    system, user, inputs = HookKeeper()._build_prompts(bb, chapter=1)
    assert "伏笔登记员" in system
    assert "pending_hooks.md" in system
    assert "首章" in user or "首次生成" in user
    assert "state/chapters/ch001.md" in inputs
    assert "state/pending_hooks.md" not in inputs


def test_prompt_ch2_with_prior_ledger_and_status_card(bb):
    bb.write_text("pending_hooks.md", "# 待回收伏笔池\n\n| hook_id | state |")
    bb.write_text("current_status_card.md", "# 当前状态卡\n\n| x | y |")
    bb.write_text("chapters/ch002.md", "ch2 text. 黑衣人再次现身。")
    _, user, inputs = HookKeeper()._build_prompts(bb, chapter=2)
    assert "state/pending_hooks.md" in inputs
    assert "state/current_status_card.md" in inputs
    assert "保留仍活跃" in user or "删除本章回收" in user


def test_prompt_three_hook_priority_types_declared(bb):
    bb.write_text("chapters/ch001.md", "text")
    system, _, _ = HookKeeper()._build_prompts(bb, chapter=1)
    # Skill #7's three priority types must be explicitly called out
    assert "逃敌" in system
    assert "宝物" in system
    assert "耳语" in system


def test_prompt_lesson3_boundary_no_plan_verdict(bb):
    bb.write_text("chapters/ch001.md", "text")
    system, _, _ = HookKeeper()._build_prompts(bb, chapter=1)
    assert "不读" in system
    assert "plan" in system or "verdict" in system


def test_skeleton_has_both_tables():
    for heading in ("当前活跃伏笔", "已回收伏笔"):
        assert heading in PENDING_HOOKS_SKELETON
    # Table schemas
    assert "hook_id" in PENDING_HOOKS_SKELETON
    assert "起始章" in PENDING_HOOKS_SKELETON


# -------- output handling --------

def test_handle_output_strips_fence(bb):
    fenced = "```markdown\n# 待回收伏笔池 (pending_hooks.md)\n\n| a | b |\n```"
    HookKeeper()._handle_output(bb, fenced, chapter=1)
    text = bb.read_text("pending_hooks.md")
    assert text.startswith("# 待回收伏笔池")
    assert "```" not in text


def test_handle_output_overwrites(bb):
    bb.write_text("pending_hooks.md", "OLD CONTENT")
    HookKeeper()._handle_output(bb, "# 待回收伏笔池 (pending_hooks.md)\n\nNEW", chapter=5)
    text = bb.read_text("pending_hooks.md")
    assert "OLD CONTENT" not in text
    assert "NEW" in text


# -------- read_pending_hooks helper --------

def test_read_helper_exists_branch(bb):
    bb.write_text("pending_hooks.md", "# 待回收伏笔池")
    text, inputs = read_pending_hooks(bb)
    assert "待回收伏笔池" in text
    assert inputs == ["state/pending_hooks.md"]


def test_read_helper_missing_branch(bb):
    text, inputs = read_pending_hooks(bb)
    assert "尚无伏笔池" in text
    assert inputs == []
