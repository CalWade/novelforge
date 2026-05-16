"""Lock in: Planner generates rich chapter titles ('第 N 章 · <章名>'),
not bare '第 N 章' placeholders.

Why: bootstrap creates blank outline with title='第 N 章' as placeholder;
without explicit instruction, Planner copies this placeholder verbatim into
plan.title, then Generator copies plan.title into chapter.md first line,
producing 30 chapters all titled '第 N 章'. User reported and asked Planner
to enrich titles based on chapter beats / scenes / hooks.

These tests guard the Planner system prompt's title rule (5b clause).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.planner import Planner


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    b.write_yaml(
        "setting.yaml",
        {"genre": "test", "era": "2026"},
    )
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "陈默"}, "supporting": []},
    )
    b.write_text("era.md", "test era facts")
    b.write_text("writing-style-extra.md", "test style extras")
    b.write_text("iron-laws-extra.md", "test extras")
    b.write_json(
        "outline.json",
        {
            "title": "测试书",
            "chapters": [{"ch": i, "title": f"第 {i} 章", "beats": []} for i in range(1, 6)],
        },
    )
    b.write_text("timeline.yaml", "")
    return b


def test_planner_system_prompt_has_title_enrichment_rule(bb):
    """The 5b clause must exist and demand non-placeholder titles."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    assert "5b" in system, "Planner system prompt missing 5b clause for title enrichment"
    assert "title" in system or "章节标题" in system
    # Format directive
    assert "第 N 章 · <章名>" in system or "第 N 章 ·" in system, (
        "missing title format directive '第 N 章 · <章名>'"
    )
    # Length spec
    assert "4-12 字" in system, "missing 章名 4-12 字 length spec"


def test_planner_prompt_warns_against_placeholder_title(bb):
    """The clause must explicitly reject bare '第 N 章' as final output."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    # ❌ examples
    assert "❌" in system
    assert "占位" in system, "must reject bare '第 N 章' as placeholder"
    # Override directive: even if outline has placeholder, Planner must reinvent
    assert "重新起" in system or "重新" in system, (
        "must instruct Planner to override outline placeholder"
    )


def test_planner_prompt_has_concrete_title_examples(bb):
    """Both ✅ and ❌ examples must be present so LLM has concrete anchors."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    assert "✅" in system, "missing ✅ examples"
    # 至少有两个具体正例
    good_count = system.count("✅")
    assert good_count >= 2, f"need at least 2 ✅ examples, found {good_count}"
    # 至少有两个具体反例
    bad_count = system.count("❌")
    assert bad_count >= 2, f"need at least 2 ❌ examples, found {bad_count}"
