"""Tests for pipeline Intent Router (C-22) and lifecycle orchestration.

All real LLM calls are monkey-patched out. We verify:
- CLI argparse accepts all --intent flags and dispatches to the right fn.
- run_bookkeeping_only re-runs the right sequence of agents.
- The full run_chapter pipeline executes stages in the expected order.
- ResourceLedger stage is skipped when setting has no resource_schema.yaml.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from src import pipeline
from src.blackboard import Blackboard


# ---- Test helpers: build a minimal blackboard and mock out every LLM call ---

def _seed_bb(tmp_path: Path, *, with_schema: bool = False) -> Blackboard:
    b = Blackboard(root=tmp_path)
    b.write_yaml(
        "setting.yaml",
        {
            "genre": "g",
            "era": "e",
            "tone": "t",
            "prohibited_styles": ["x"],
            "author_persona_hints": ["hint"],
        },
    )
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "主角"}, "supporting": []},
    )
    b.write_text("timeline.yaml", "2024: []\n")
    b.write_text("era.md", "era facts")
    b.write_text("writing-style-extra.md", "style extra")
    b.write_text("iron-laws-extra.md", "## iron_law_extra_1\nfoo\n")
    b.write_json(
        "outline.json",
        {
            "chapters": [
                {"ch": 1, "title": "第一章", "beats": ["b1"]},
            ],
        },
    )
    b.write_json("progress.json", {"current_chapter": 0, "completed_chapters": []})
    (tmp_path / "chapters").mkdir(exist_ok=True)
    (tmp_path / "summaries").mkdir(exist_ok=True)
    (tmp_path / "fixes").mkdir(exist_ok=True)
    if with_schema:
        b.write_yaml(
            "resource_schema.yaml",
            {
                "resources": [{"id": "r1", "display_name": "R1", "unit": "u"}],
                "validation": {"increment_rules": [], "forbidden_fuzzy_terms": []},
            },
        )
    return b


def _fake_llm_factory(responses: dict[str, str]):
    """Return a fake llm.chat that routes responses by agent_name."""

    def _fake(*, system, user, agent_name, temperature, max_tokens, response_format, inputs_read):
        if agent_name in responses:
            return responses[agent_name]
        # sensible defaults per response_format
        if response_format == "json":
            return '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}'
        return "# 第一章 标题\n\n正文内容。"

    return _fake


# ---------------------- Intent Router tests -----------------------

def test_run_plan_only_invokes_planner_only(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path)
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return '{"ch": 1, "title": "t", "scenes": [], "chapter_type": "布局", "opening_hook": "o", "closing_hook": "c", "landmines_to_avoid": [], "writing_self_check": {}}'
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_plan_only(bb, 1)
    assert result["stage"] == "plan"
    assert calls == ["planner"]
    assert bb.exists("chapters/ch001.plan.json")


def test_run_write_only_invokes_generator_only(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path)
    bb.write_json(
        "chapters/ch001.plan.json",
        {
            "ch": 1,
            "title": "t",
            "scenes": [{"scene_id": 1, "cast": ["主角"]}],
            "chapter_type": "过渡",
        },
    )
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return "# t\n\n正文"
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_write_only(bb, 1)
    assert result["stage"] == "write"
    assert calls == ["generator"]
    assert bb.exists("chapters/ch001.md")


def test_run_evaluate_only_invokes_evaluator_only(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path)
    bb.write_text("chapters/ch001.md", "# t\n正文")
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}'
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_evaluate_only(bb, 1)
    assert result["stage"] == "evaluate"
    assert calls == ["evaluator"]
    assert result["overall_pass"] is True


def test_run_fix_only_invokes_fixer_only(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path)
    bb.write_text("chapters/ch001.md", "# t\n正文")
    bb.write_json(
        "chapters/ch001.verdict.json",
        {"overall_pass": False, "landmines": {}, "top_3_fixes": [{"where": "xx", "what": "yy"}]},
    )
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return "# t\n修过的正文"
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_fix_only(bb, 1)
    assert result["stage"] == "fix"
    assert calls == ["fixer"]


def test_run_bookkeeping_only_invokes_all_ledgers_no_schema(tmp_path, monkeypatch):
    """Without resource_schema.yaml, ResourceLedger must NOT run."""
    bb = _seed_bb(tmp_path, with_schema=False)
    bb.write_text("chapters/ch001.md", "# t\n正文")
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return "stub output" if agent_name != "evaluator" else '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}'
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_bookkeeping_only(bb, 1)
    assert result["stage"] == "bookkeeping"
    # Order: summarize → update_status_card → update_hook_ledger
    assert calls == ["summarizer", "status_card_updater", "hook_keeper"]
    assert "update_resource_ledger" not in result["stages"]


def test_run_bookkeeping_only_invokes_resource_ledger_when_schema_present(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path, with_schema=True)
    bb.write_text("chapters/ch001.md", "# t\n正文")
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return "stub output"
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_bookkeeping_only(bb, 1)
    assert "update_resource_ledger" in result["stages"]
    assert "resource_ledger" in calls


def test_run_bookkeeping_only_runs_arc_at_boundary(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path)
    # Fake L1 summaries for ch1..ch5 so ArcSummarizer can read them
    for n in range(1, 6):
        bb.write_text(f"chapters/ch{n:03d}.md", f"# 第{n}章\n正文")
        bb.write_text(f"summaries/ch{n:03d}.md", f"ch{n} summary")
    calls = []
    def fake_chat(*, agent_name, **_):
        calls.append(agent_name)
        return "stub"
    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    result = pipeline.run_bookkeeping_only(bb, 5)  # arc boundary
    assert "arc_summarize" in result["stages"]
    assert "arc_summarizer" in calls


# ---------------------- Full run_chapter orchestration tests -----------------------

def test_run_chapter_full_flow_invokes_all_stages(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path, with_schema=False)

    # Canned responses per agent — make evaluator pass first try so no Fixer needed
    responses = {
        "planner": json.dumps(
            {
                "ch": 1,
                "title": "t",
                "chapter_type": "过渡",
                "opening_hook": "o",
                "scenes": [{"scene_id": 1, "cast": ["主角"], "advances": ["地位"]}],
                "closing_hook": "c",
                "landmines_to_avoid": [],
                "writing_self_check": {},
            }
        ),
        "generator": "# 第一章 标题\n\n主角走进了办公室。",
        "evaluator": '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}',
        "summarizer": "主角上班了。",
        "status_card_updater": "# 当前状态卡\n\n| 当前章 | ch1 |",
        "hook_keeper": "# 待回收伏笔池 (pending_hooks.md)\n\n| a | b |",
        "ai_slop_guard": "(no issues)",
        "character_guard": "(no issues)",
    }
    monkeypatch.setattr("src.agents._base.llm.chat", _fake_llm_factory(responses))

    status = pipeline.run_chapter(bb, 1)
    assert status["evaluation"]["passed"] is True
    stages = status["stages"]
    for name in ("plan", "generate", "evaluate", "summarize", "update_status_card",
                 "update_hook_ledger", "audit_fanout"):
        assert name in stages, f"missing stage {name} in {list(stages)}"
    # Artifacts exist
    for p in (
        "chapters/ch001.plan.json",
        "chapters/ch001.md",
        "chapters/ch001.verdict.json",
        "summaries/ch001.md",
        "current_status_card.md",
        "pending_hooks.md",
    ):
        assert bb.exists(p), f"artifact {p} should exist"


def test_run_chapter_skips_resource_ledger_when_no_schema(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path, with_schema=False)
    responses = {
        "planner": json.dumps(
            {
                "ch": 1, "title": "t", "chapter_type": "过渡",
                "opening_hook": "o",
                "scenes": [{"scene_id": 1, "cast": ["主角"], "advances": ["地位"]}],
                "closing_hook": "c", "landmines_to_avoid": [], "writing_self_check": {},
            }
        ),
        "evaluator": '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}',
    }
    monkeypatch.setattr("src.agents._base.llm.chat", _fake_llm_factory(responses))
    status = pipeline.run_chapter(bb, 1)
    assert "update_resource_ledger" not in status["stages"]


def test_run_chapter_runs_resource_ledger_when_schema_present(tmp_path, monkeypatch):
    bb = _seed_bb(tmp_path, with_schema=True)
    responses = {
        "planner": json.dumps(
            {
                "ch": 1, "title": "t", "chapter_type": "过渡",
                "opening_hook": "o",
                "scenes": [{"scene_id": 1, "cast": ["主角"], "advances": ["地位"]}],
                "closing_hook": "c", "landmines_to_avoid": [], "writing_self_check": {},
            }
        ),
        "evaluator": '{"overall_pass": true, "landmines": {}, "top_3_fixes": []}',
    }
    monkeypatch.setattr("src.agents._base.llm.chat", _fake_llm_factory(responses))
    status = pipeline.run_chapter(bb, 1)
    assert "update_resource_ledger" in status["stages"]
    assert bb.exists("resource_ledger.md")


# ---------------------- CLI help + mutual exclusion -----------------------

def test_cli_help_lists_all_intent_flags():
    """Run the CLI with --help and check all new flags are advertised."""
    result = subprocess.run(
        [sys.executable, "-m", "src.pipeline", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0
    out = result.stdout
    for flag in (
        "--chapter", "--range", "--audit-only", "--packaging",
        "--plan-only", "--write-only", "--evaluate-only",
        "--fix-only", "--bookkeeping-only",
    ):
        assert flag in out, f"CLI help missing {flag}"


def test_cli_requires_one_of_the_intent_flags():
    result = subprocess.run(
        [sys.executable, "-m", "src.pipeline"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode != 0
    assert "one of the arguments" in result.stderr or "required" in result.stderr.lower()


def test_cli_rejects_conflicting_intents():
    """--chapter and --plan-only are mutually exclusive."""
    result = subprocess.run(
        [sys.executable, "-m", "src.pipeline", "--chapter", "1", "--plan-only", "1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode != 0
    assert "not allowed with" in result.stderr
