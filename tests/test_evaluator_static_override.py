"""Tests for Patch 1: Evaluator's _handle_output forces landmine_18 hit when
the static AI-rhythm scanner reports severe (or 2+ moderate) findings,
overriding any LLM verdict that claims the chapter is clean.

Why this matters (Oracle diagnosis): Generator + Evaluator + AISlopGuard share
the same training preferences. They collectively misread "AI rhythm" as
"polished prose". A pure-Python regex scanner can count 42 em-dashes and
38 short paragraphs deterministically, but the LLM looks at the same text
and shrugs. Patch 1 wires the static scanner's output directly into the
verdict so the LLM's subjective judgment can no longer override it.

Also tests that the static metrics are surfaced in the user prompt so the
LLM has the numbers in front of it (not strictly needed for correctness
under Patch 1, but makes the LLM's failure mode less likely).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.evaluator import Evaluator
from src.agents._verdict_schema import LANDMINE_IDS


# ---------------- shared fixture ----------------


def _seed_minimum(tmp_path: Path) -> Blackboard:
    """Mirror tests/test_evaluator_reads_bookkeeping.py::_seed_minimum."""
    b = Blackboard(root=tmp_path)
    b.write_yaml("setting.yaml", {"genre": "港综同人", "era": "1983"})
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "林家耀"}, "supporting": []},
    )
    b.write_text("timeline.yaml", "1983: []\n")
    b.write_text("iron-laws-extra.md", "## iron_law_extra_1 洋人不跪舔\n")
    (tmp_path / "chapters").mkdir(exist_ok=True)
    return b


def _all_false_landmines() -> dict:
    """Build a 19-key landmines dict, all hit=false. The shape matches what
    a clean LLM verdict would produce."""
    return {
        mid: {"hit": False, "evidence": None, "severity": None}
        for mid in LANDMINE_IDS
    }


def _llm_response(landmines: dict, overall_pass: bool, top_3_fixes=None) -> str:
    """Serialize a fake LLM JSON response."""
    return json.dumps(
        {
            "overall_pass": overall_pass,
            "landmines": landmines,
            "top_3_fixes": top_3_fixes or [],
        },
        ensure_ascii=False,
    )


# ---------------- corpus builders for static scanner ----------------
#
# SLOP_THRESHOLDS in src/auditors/ai_slop_guard.py:
#   neg_contrast: moderate=5, severe=10
#   emdash:       moderate=20, severe=30
#   short_para:   moderate=0.35, severe=0.50
#   simile:       moderate=25, severe=40


def _severe_chapter() -> str:
    """Build a chapter that triggers severe on neg_contrast AND emdash.

    - 12 instances of "不是X，是Y" (severe ≥ 10)
    - 32 em-dashes outside dialogue (severe ≥ 30)
    """
    lines = ["# 第一章\n"]
    # 12 neg-contrast lines (each line is its own paragraph). Keep them long
    # enough (≥30 chars) so they don't *also* trigger short_para severe by
    # accident — we want the test to isolate neg_contrast + emdash.
    for i in range(12):
        lines.append(
            f"林家耀缓缓走过码头，他不是港岛的过客，是这片湾仔暗流真正的主人之一。第{i}段叙述补全。"
        )
    # 32 em-dashes spread across long descriptive paragraphs (no dialogue).
    long_para = "霓虹灯下的湾仔像一只巨兽——它喘息——它颤抖——它低吼——它沉默——它窥伺——"
    long_para += "——".join([f"灯火{i}" for i in range(28)])  # adds 27 more "——"
    lines.append(long_para)
    return "\n\n".join(lines) + "\n"


def _two_moderate_chapter() -> str:
    """Build a chapter that triggers EXACTLY 2 moderate (no severe).

    - 6 neg-contrast (moderate ≥ 5, severe ≥ 10)
    - 22 em-dashes (moderate ≥ 20, severe ≥ 30)
    Below moderate on short_para and simile.
    """
    lines = ["# 第二章\n"]
    for i in range(6):
        lines.append(
            f"她不是寻常茶餐厅的伙计，是九龙城寨真正的眼线。第{i}段交代背景，足够长不算短段。"
        )
    long_para = "雨水砸在霓虹招牌上"
    # 22 em-dashes
    long_para += "——".join([f"段{i}" for i in range(23)])
    lines.append(long_para)
    return "\n\n".join(lines) + "\n"


def _clean_chapter() -> str:
    """Build a chapter that triggers NO static hits (all 4 metrics healthy)."""
    lines = ["# 第三章\n"]
    # 1 neg-contrast (≤2 healthy)
    lines.append("他不是孤身一人，是带着整条街的眼睛走进茶餐厅。叙述继续推进，足够长不算短段。")
    # ~5 em-dashes (≤8 healthy)
    long_para = "湾仔的傍晚，霓虹刚刚亮起。林家耀走过茶餐厅门口——脚步没停。"
    long_para += "他抬头看了一眼天空——云压得很低——空气湿热。"
    long_para += "码头方向传来汽笛声——他知道那是货轮在靠岸。这是他熟悉的港岛节奏。"
    lines.append(long_para)
    # Add a few normal-length narrative paragraphs to keep short_para ratio low
    for i in range(5):
        lines.append(
            f"接下来的一个小时他在街角观察来往的人流，记下几张面孔。第{i}段稳定推进剧情，无明显节奏问题。"
        )
    return "\n\n".join(lines) + "\n"


# ---------------- LLM mock helper ----------------


def _patch_llm(monkeypatch, response: str) -> list:
    """Patch llm.chat to return `response`. Returns a list that captures the
    (system, user) pair for prompt inspection."""
    captured: list = []

    def fake_chat(*, system, user, agent_name, **_):
        captured.append((system, user))
        return response

    monkeypatch.setattr("src.agents._base.llm.chat", fake_chat)
    return captured


# =============================================================
# Case 1: severe static hit forces landmine_18 = high + pass=false
# =============================================================


def test_severe_static_hit_forces_landmine_18_high(tmp_path, monkeypatch):
    b = _seed_minimum(tmp_path)
    b.write_text("chapters/ch001.md", _severe_chapter())

    # LLM lies and says "all clean, pass"
    fake = _llm_response(_all_false_landmines(), overall_pass=True, top_3_fixes=[])
    _patch_llm(monkeypatch, fake)

    Evaluator().run(b, chapter=1)

    verdict = b.read_json("chapters/ch001.verdict.json")
    lm18 = verdict["landmines"]["landmine_18"]
    assert lm18["hit"] is True
    assert lm18["severity"] == "high"
    assert lm18.get("_source") == "static_scan"
    assert verdict["overall_pass"] is False
    # at least one fix carries _source=static_scan
    static_fixes = [f for f in verdict["top_3_fixes"] if f.get("_source") == "static_scan"]
    assert len(static_fixes) >= 1


# =============================================================
# Case 2: 2 moderate static hits → medium, overall_pass preserved
# =============================================================


def test_two_moderate_static_hits_forces_medium(tmp_path, monkeypatch):
    b = _seed_minimum(tmp_path)
    b.write_text("chapters/ch001.md", _two_moderate_chapter())

    fake = _llm_response(_all_false_landmines(), overall_pass=True, top_3_fixes=[])
    _patch_llm(monkeypatch, fake)

    Evaluator().run(b, chapter=1)

    verdict = b.read_json("chapters/ch001.verdict.json")
    lm18 = verdict["landmines"]["landmine_18"]
    assert lm18["hit"] is True, "2 moderate hits should still force landmine_18 to hit"
    assert lm18["severity"] == "medium"
    assert lm18.get("_source") == "static_scan"
    # overall_pass: only 1 medium hit total → stays True (LLM said pass=true and
    # validate_verdict recomputes pass from severity counts: 0 high, 1 medium → pass=true)
    assert verdict["overall_pass"] is True


# =============================================================
# Case 3: clean text → no static override (LLM verdict respected)
# =============================================================


def test_clean_text_no_static_override(tmp_path, monkeypatch):
    b = _seed_minimum(tmp_path)
    b.write_text("chapters/ch001.md", _clean_chapter())

    fake = _llm_response(_all_false_landmines(), overall_pass=True, top_3_fixes=[])
    _patch_llm(monkeypatch, fake)

    Evaluator().run(b, chapter=1)

    verdict = b.read_json("chapters/ch001.verdict.json")
    lm18 = verdict["landmines"]["landmine_18"]
    assert lm18["hit"] is False, "clean text should leave landmine_18 unhit"
    assert "_source" not in lm18, "static_scan _source flag must not be set on clean text"
    assert verdict["overall_pass"] is True
    # No static-sourced fixes injected
    static_fixes = [
        f for f in verdict["top_3_fixes"] if f.get("_source") == "static_scan"
    ]
    assert static_fixes == []


# =============================================================
# Case 4: static hit does not clobber other LLM landmine hits
# =============================================================


def test_static_hit_does_not_clobber_other_landmines(tmp_path, monkeypatch):
    b = _seed_minimum(tmp_path)
    b.write_text("chapters/ch001.md", _severe_chapter())

    # LLM hits landmine_3 (with substantive evidence) but says all others clean.
    landmines = _all_false_landmines()
    landmines["landmine_3"] = {
        "hit": True,
        "evidence": "林家耀缓缓走过码头，他不是港岛的过客（原文重复了两遍背景）",
        "severity": "medium",
    }
    fake = _llm_response(
        landmines,
        overall_pass=False,
        top_3_fixes=[
            {
                "where": "林家耀缓缓走过码头",
                "what": "压缩重复背景，避免叙述节奏拖沓",
            }
        ],
    )
    _patch_llm(monkeypatch, fake)

    Evaluator().run(b, chapter=1)

    verdict = b.read_json("chapters/ch001.verdict.json")
    # LLM's landmine_3 hit must survive the post-process unchanged
    lm3 = verdict["landmines"]["landmine_3"]
    assert lm3["hit"] is True
    assert lm3["severity"] == "medium"
    assert "原文重复了两遍背景" in (lm3.get("evidence") or "")
    assert lm3.get("_source") is None, "LLM-sourced hit must not be tagged static_scan"

    # Static-scan landmine_18 still injected as high
    lm18 = verdict["landmines"]["landmine_18"]
    assert lm18["hit"] is True
    assert lm18["severity"] == "high"
    assert lm18.get("_source") == "static_scan"
    assert verdict["overall_pass"] is False


# =============================================================
# Case 5: user prompt embeds the mechanical-scan metrics block
# =============================================================


def test_user_prompt_includes_metrics_block(tmp_path):
    b = _seed_minimum(tmp_path)
    b.write_text("chapters/ch001.md", _severe_chapter())

    _system, user, _inputs = Evaluator()._build_prompts(b, chapter=1)

    assert "机械扫描结果" in user, "user prompt must surface the mechanical scan section"
    # Each of the 4 metric labels must be present with concrete numbers nearby
    for label in ["否定对比", "破折号", "短段", "明喻"]:
        assert label in user
    # Sanity check: actual neg_contrast count for the severe chapter is ≥ 10
    # and the prompt must show that number (not a placeholder).
    from src.auditors.ai_slop_guard import static_scan_ai_rhythm
    metrics = static_scan_ai_rhythm(_severe_chapter())["metrics"]
    assert f"**{metrics['neg_contrast']}**" in user
    assert f"**{metrics['emdash']}**" in user
