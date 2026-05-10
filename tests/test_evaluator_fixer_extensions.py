"""Tests for Fixer + Evaluator prompt extensions:
- Fixer loads prohibited_styles block (C-32) and references info-priority (B-1)
- Fixer reads setting.yaml (new dependency)
- Evaluator loads rules/00-information-priority.md (B-1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.agents.fixer import Fixer
from src.agents.evaluator import Evaluator


@pytest.fixture
def seeded_bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    b.write_yaml(
        "setting.yaml",
        {
            "genre": "港综同人",
            "era": "1983",
            "tone": "暴力美学",
            "prohibited_styles": ["玄幻修仙腔", "霸总腔"],
        },
    )
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "林家耀"}, "supporting": []},
    )
    b.write_text("timeline.yaml", "1983: []\n")
    b.write_text("era.md", "港岛事实。")
    b.write_text("writing-style-extra.md", "港综风格补充。")
    b.write_text(
        "iron-laws-extra.md", "## iron_law_extra_1 洋人不跪舔\n"
    )
    (tmp_path / "chapters").mkdir(exist_ok=True)
    b.write_text("chapters/ch001.md", "# 第一章\n正文")
    b.write_json(
        "chapters/ch001.verdict.json",
        {
            "overall_pass": False,
            "landmines": {},
            "top_3_fixes": [
                {"where": "第二段『X 说』", "what": "改为展示动作，不直接白描情绪"}
            ],
        },
    )
    return b


# -------- Fixer: C-32 prohibited_styles + B-1 info-priority reference --------

def test_fixer_reads_setting_yaml(seeded_bb):
    _, _, inputs = Fixer()._build_prompts(seeded_bb, chapter=1)
    assert "state/setting.yaml" in inputs


def test_fixer_system_has_prohibited_styles_block(seeded_bb):
    system, _, _ = Fixer()._build_prompts(seeded_bb, chapter=1)
    assert "风格锁定" in system
    assert "玄幻修仙腔" in system
    assert "霸总腔" in system


def test_fixer_system_mentions_info_priority_protocol(seeded_bb):
    system, _, _ = Fixer()._build_prompts(seeded_bb, chapter=1)
    # B-1: Fixer should mention conflict arbitration referring to the rule file
    assert "00-information-priority.md" in system or "冲突仲裁" in system


def test_fixer_system_has_root_cause_language(seeded_bb):
    system, _, _ = Fixer()._build_prompts(seeded_bb, chapter=1)
    # Root-cause vs. surface-polish language
    assert "根因" in system


def test_fixer_handles_missing_prohibited_styles(seeded_bb):
    setting = seeded_bb.read_yaml("setting.yaml")
    setting.pop("prohibited_styles", None)
    seeded_bb.write_yaml("setting.yaml", setting)
    system, _, _ = Fixer()._build_prompts(seeded_bb, chapter=1)
    assert "未声明风格禁止清单" in system


# -------- Evaluator: B-1 info-priority loaded --------

def test_evaluator_loads_information_priority_rule(seeded_bb):
    system, _, inputs = Evaluator()._build_prompts(seeded_bb, chapter=1)
    assert "rules/00-information-priority.md" in inputs
    # The rule content (or at least its heading) must appear in the system prompt
    assert "信息源优先级" in system


def test_evaluator_still_loads_landmines_and_iron_laws(seeded_bb):
    _, _, inputs = Evaluator()._build_prompts(seeded_bb, chapter=1)
    assert "rules/18-landmines.md" in inputs
    assert "rules/24-iron-laws.md" in inputs
    assert "state/iron-laws-extra.md" in inputs
