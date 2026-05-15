"""Lock in: AI rhythm taboos must appear at the TAIL of Generator's system prompt.

Why: ch026 from book-e3f4fc9b shipped with severe AI rhythm病 (否定对比 23x,
破折号 42x, 短段 53%). Investigation showed taboos were at 42% of system prompt,
but dna_tips_block + writing-style-extra at 75-100% reverse-rewards
"短句堆叠/三段式 动作-反应-新动作" — recency bias kills the middle taboo.

Fix: extract taboos to rules/ai-rhythm-taboos.md and append at the very end of
system prompt with a "最终硬规则（冲突仲裁）" header. These tests lock in:
1. The taboo file exists with the expected硬上限 wording
2. Generator's system prompt has it at >80% position
3. writing-style-core.md no longer carries the same content (avoid duplication)
4. inputs_read advertises the new file
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import config
from src.blackboard import Blackboard
from src.agents.generator import Generator


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
    (tmp_path / "chapters").mkdir(exist_ok=True)
    b.write_json(
        "chapters/ch001.plan.json",
        {
            "ch": 1,
            "title": "t",
            "scenes": [{"scene_id": 1, "cast": ["陈默"]}],
            "chapter_type": "战斗",
        },
    )
    return b


# ---------- file existence + content ----------

def test_ai_taboos_file_exists():
    p = config.RULES_DIR / "ai-rhythm-taboos.md"
    assert p.exists(), "rules/ai-rhythm-taboos.md must exist as the single source of truth"


def test_ai_taboos_file_carries_expected_wording():
    text = (config.RULES_DIR / "ai-rhythm-taboos.md").read_text(encoding="utf-8")
    # 关键概念
    assert "最终冲突令" in text or "最终硬规则" in text
    assert "硬上限" in text
    # 4 类节奏病
    assert "不是 X，是 Y" in text or "否定对比" in text
    assert "破折号" in text
    assert "诗歌化" in text or "短段" in text
    assert "明喻" in text
    # 4 个数值阈值
    for cap in ("≤ 2", "≤ 8", "≤ 20%", "≤ 15"):
        assert cap in text, f"missing hard cap '{cap}' in taboos file"


# ---------- Generator system prompt: taboos at TAIL ----------

def test_generator_system_prompt_includes_ai_taboos(bb):
    system, _, _ = Generator()._build_prompts(bb, chapter=1)
    assert "最终硬规则" in system, "Generator system prompt missing 最终硬规则 header"
    assert "硬上限" in system, "Generator system prompt missing taboos硬上限 content"


def test_taboos_appear_in_last_25_percent_of_system_prompt(bb):
    """The whole point of the fix: recency bias means the LLM weights the END.
    Test fixture has empty dna_tips_block; in production with real preset
    DNA the position drifts deeper into the tail. >75% is enough margin."""
    system, _, _ = Generator()._build_prompts(bb, chapter=1)
    idx = system.find("最终硬规则")
    assert idx > 0
    position_pct = idx / len(system)
    assert position_pct > 0.75, (
        f"最终硬规则 sits at {position_pct*100:.1f}% — must be > 75% (after extra/era/dna_tips). "
        f"Without tail placement, taboos lose the recency-bias fight against extra/dna content."
    )


def test_taboos_come_after_extra_and_era(bb):
    """Strict ordering: taboos must come AFTER 题材特有风格补充 and 时代/世界观事实包."""
    system, _, _ = Generator()._build_prompts(bb, chapter=1)
    pos_extra = system.find("题材特有风格补充")
    pos_era = system.find("时代/世界观事实包")
    pos_taboo = system.find("最终硬规则")
    assert 0 < pos_extra < pos_taboo, "taboos must come AFTER 题材特有风格补充"
    assert 0 < pos_era < pos_taboo, "taboos must come AFTER 时代/世界观事实包"


def test_generator_inputs_read_includes_taboos(bb):
    _, _, inputs = Generator()._build_prompts(bb, chapter=1)
    assert "rules/ai-rhythm-taboos.md" in inputs, (
        "Generator must advertise reading rules/ai-rhythm-taboos.md in inputs_read "
        "for Prompt Inspector transparency"
    )


# ---------- writing-style-core no longer carries the taboos ----------

def test_writing_style_core_no_longer_has_ai_taboos():
    """Anti-regression: avoid taboos appearing twice in system prompt
    (once in middle via writing-style-core, once at tail via ai-rhythm-taboos)."""
    text = (config.RULES_DIR / "writing-style-core.md").read_text(encoding="utf-8")
    assert "AI 时代新增禁忌" not in text, (
        "writing-style-core.md still has the AI taboos section. "
        "It was moved to ai-rhythm-taboos.md — delete the old section to avoid duplication."
    )
