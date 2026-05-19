"""Lock in: Planner system prompt limits 数字量化 to system-layer data only.

Why: 用户报告 ch1 一直在堆砌科学化数字（"右眼灰斑扩张 8% / 侵蚀速度
每眨眼 10.2% / 频率约 2.3 赫兹 / 0.3 厘米 / 0.5 秒"），读起来像
科学论文不像网文。

根因三层叠加：
1. preset/2 writing-style-extra.md 招式 #2 写"数字量化生存状态"
   被 LLM 理解为"任意场景全数字化"
2. dna_structured.yaml universal.writing_style 也说"数据外化一切"
3. Planner 系统 prompt 没有约束 — Planner 可能在 plan.scenes
   .sensory_prompts 写"右眼侵蚀速度从 10.2%→12%"等亚秒/亚毫米精度
   指令，Generator 看到自然照搬

修复方向：把"数字量化"语义收窄到「灰烬契书系统层」（条款数 /
担保链节点 / 灰烬点 / 整秒倒计时），明确禁止生活/感官层的科学化精度
（亚秒 / 毫米 / 赫兹 / 生理百分比）。

本测试守 Planner system prompt 的新约束：
1. writing_self_check 必须含 numeric_drift_risk 字段
2. 必须显式说"数字量化只用于灰烬契书系统层"
3. 必须禁亚秒精度 / 毫米级生理指标
4. 必须警告 scene.sensory_prompts 不要出现这种数字（避免污染 Generator）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.planner import Planner


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    b.write_yaml("setting.yaml", {"genre": "test", "era": "2026"})
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "苏烬"}, "supporting": []},
    )
    b.write_text("era.md", "苏烬 G22 灰烬契书 末世第三年")
    b.write_text("writing-style-extra.md", "")
    b.write_text("iron-laws-extra.md", "")
    b.write_text("timeline.yaml", "")
    b.write_json(
        "outline.json",
        {"title": "灰烬契约", "chapters": [{"ch": i, "title": f"第 {i} 章", "beats": []} for i in range(1, 6)]},
    )
    return b


def test_planner_system_prompt_has_numeric_drift_risk_field(bb):
    """writing_self_check schema must include numeric_drift_risk."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    assert "numeric_drift_risk" in system, (
        "Planner system prompt missing numeric_drift_risk field. "
        "Without it, Planner may put scientific-grade numbers in "
        "scene.sensory_prompts which Generator copies into prose."
    )


def test_planner_prompt_restricts_numeric_to_system_layer(bb):
    """The 'system layer only' rule must be explicit."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    assert "数字量化只用于" in system or "系统层" in system, (
        "Planner missing 'numbers only for system-layer data' rule. "
        "Letting Planner think any场景都该数字化 leads to "
        "'eyelid speed 0.6mm / heart rate 75 / hertz' science writing."
    )


def test_planner_prompt_forbids_sub_second_and_sub_mm_precision(bb):
    """Must explicitly forbid 0.3秒 / 0.6毫米 type sci-fi precision."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    # 至少有一个用语明确禁止
    has_subsecond_ban = any(kw in system for kw in [
        "亚秒精度", "0.3 秒", "0.5 秒", "亚秒",
    ])
    has_submm_ban = any(kw in system for kw in [
        "毫米级生理", "毫米", "赫兹",
    ])
    assert has_subsecond_ban, "Planner must forbid sub-second precision (0.3秒等)"
    assert has_submm_ban, "Planner must forbid sub-millimeter生理 / 赫兹 precision"


def test_planner_prompt_warns_about_sensory_prompts_pollution(bb):
    """The most critical part: warn Planner that bad numbers in sensory_prompts
    will get copied verbatim into Generator's prose."""
    system, _, _ = Planner()._build_prompts(bb, chapter=1)
    assert "sensory_prompts" in system or "Generator" in system, (
        "Planner must warn that numbers in scene.sensory_prompts get "
        "copied verbatim by Generator. Without this warning, Planner "
        "writes '右眼侵蚀速度从 10.2%→12%' in sensory_prompts and "
        "Generator faithfully renders it as scientific论文 prose."
    )
