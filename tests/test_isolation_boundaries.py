"""Regression tests for Lesson-3 isolation boundaries.

The bookkeeping ledgers (status card, hook ledger, resource ledger) MUST NOT
become inputs to the creative agents beyond what we explicitly designed:
- Planner: reads status_card + pending_hooks (by design — it's what Context
  Reset is for).
- Generator: does NOT read status card / pending hooks / resource ledger
  (it reads only plan.json + characters + era + style).
- Evaluator: reads status_card + pending_hooks (P0-4: needed for
  landmine_10 反派信息越界 / 伏笔回收一致性). Does NOT read resource_ledger
  (Evaluator judges prose vs. rules, not derived numeric ledgers).
- Summarizer: does NOT read plan / verdict / status card / hooks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.generator import Generator
from src.agents.evaluator import Evaluator
from src.agents.summarizer import Summarizer


@pytest.fixture
def fully_seeded_bb(tmp_path: Path) -> Blackboard:
    """A blackboard that has EVERY possible ledger already present —
    the test is that agents still do not list them in their inputs_read."""
    b = Blackboard(root=tmp_path)
    b.write_yaml(
        "setting.yaml",
        {"genre": "g", "era": "e", "tone": "t", "prohibited_styles": ["x"]},
    )
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "A"}, "supporting": []},
    )
    b.write_text("timeline.yaml", "2024: []\n")
    b.write_text("era.md", "era.")
    b.write_text("writing-style-extra.md", "style.")
    b.write_text("iron-laws-extra.md", "## iron_law_extra_1\nfoo\n")
    # All ledgers present
    b.write_text("current_status_card.md", "# 当前状态卡\n")
    b.write_text("pending_hooks.md", "# 待回收伏笔池\n")
    b.write_text("resource_ledger.md", "# 资源账本\n")
    b.write_yaml("resource_schema.yaml", {"resources": [], "validation": {}})
    (tmp_path / "chapters").mkdir(exist_ok=True)
    (tmp_path / "summaries").mkdir(exist_ok=True)
    b.write_json(
        "chapters/ch001.plan.json",
        {
            "ch": 1,
            "title": "t",
            "scenes": [{"scene_id": 1, "cast": ["A"]}],
            "chapter_type": "过渡",
        },
    )
    b.write_text("chapters/ch001.md", "# 第一章\n正文")
    b.write_json(
        "chapters/ch001.verdict.json",
        {"overall_pass": True, "landmines": {}, "top_3_fixes": []},
    )
    return b


def test_generator_does_not_read_ledgers(fully_seeded_bb):
    """Generator must not list bookkeeping ledgers in its inputs_read."""
    _, _, inputs = Generator()._build_prompts(fully_seeded_bb, chapter=1)
    assert "state/current_status_card.md" not in inputs
    assert "state/pending_hooks.md" not in inputs
    assert "state/resource_ledger.md" not in inputs
    assert "state/resource_schema.yaml" not in inputs


def test_evaluator_does_not_read_resource_ledger(fully_seeded_bb):
    """Evaluator cross-checks prose against the authoritative 'who-knows-what'
    snapshots (status_card + pending_hooks — added in P0-4), but must NOT
    read the numeric resource ledger: resource balance is a derived artifact
    and judging prose against it would be a framing leak."""
    _, _, inputs = Evaluator()._build_prompts(fully_seeded_bb, chapter=1)
    assert "state/resource_ledger.md" not in inputs
    assert "state/resource_schema.yaml" not in inputs
    # Positive assertion (P0-4): status card + pending hooks ARE inputs.
    assert "state/current_status_card.md" in inputs
    assert "state/pending_hooks.md" in inputs


def test_summarizer_is_isolated_from_everything_but_prose(fully_seeded_bb):
    """Classic Lesson-3 boundary: Summarizer sees ONLY the final prose."""
    _, _, inputs = Summarizer()._build_prompts(fully_seeded_bb, chapter=1)
    # Exactly one input — the chapter prose
    assert inputs == ["state/chapters/ch001.md"]
