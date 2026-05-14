"""Planner / Generator 读 dna_structured.yaml（NovelDNA Stage 2.5 产物）的降级行为."""
from __future__ import annotations

import yaml


def _mk_bb(tmp_path):
    from src.blackboard import Blackboard
    bb = Blackboard(root=tmp_path)
    bb.write_json("progress.json", {"current_chapter": 1, "completed": []})
    bb.write_json("outline.json", {
        "title": "T", "subtitle": "", "protagonist": "H",
        "chapters": [{"ch": 1, "title": "第 1 章", "beats": ["a"]}],
    })
    bb.write_yaml("setting.yaml", {"genre": "末世", "era": "rusty"})
    return bb


def test_planner_without_dna_structured_has_no_block(tmp_path):
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    # 不写 dna_structured.yaml
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "DNA 创作手法样本库" not in user
    assert "dna_structured.yaml" not in " ".join(inputs)


def test_planner_with_dna_structured_injects_block(tmp_path):
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    bb.write_yaml("dna_structured.yaml", {
        "schema_version": 1,
        "tips_by_chapter_type": {
            "战斗": ["用短句连击加具体动作词碾压节奏",
                   "反派必须交代 为什么这么做 的利益"],
            "布局": ["主角通过拒绝小恩小惠来展示立场",
                   "用配角的误读烘托主角真实身份"],
            "过渡": ["场景切换时带一个具体时间锚 点钟或天色变化"],
            "回收": ["回收伏笔前 500 字必须重新提及该伏笔"],
        },
        "tips_by_scene_purpose": {
            "推进主线": ["每场戏至少推一项：信息 / 地位 / 资源"],
            "塑造人物": ["用一个小动作 / 口头禅 / 身体习惯定性"],
            "埋伏笔": ["埋的伏笔必须给出至少一个回收时间预期（3 章内）"],
        },
        "hook_recipes": {
            "opening_hooks": [
                {"pattern": "威胁升级型", "sample": "雨还没停，电话响了第三遍",
                 "applies_to": ["战斗", "布局"]},
            ],
            "closing_hooks": [
                {"pattern": "未完对白", "sample": "他没回头：明天这时候，再谈。",
                 "applies_to": ["过渡", "布局"]},
            ],
        },
        "universal": {
            "writing_style": ["对白 40-50%", "避免四字成语堆砌"],
            "value_anchors": ["生存智慧", "冷幽默"],
            "character_handling": ["每个配角至少一个利益动机"],
        },
    })
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    # 标题在
    assert "DNA 创作手法样本库" in user
    # 几个桶都渲染
    assert "按章节类型 · 战斗" in user
    assert "按场景目的 · 推进主线" in user
    assert "章首钩子配方库" in user
    assert "章末钩子配方库" in user
    assert "通用 · 写作风格" in user
    # 真实 tips 出现
    assert "用短句连击" in user
    assert "生存智慧" in user
    # inputs_read 记录
    assert "state/dna_structured.yaml" in inputs


def test_planner_dna_structured_malformed_silent(tmp_path):
    """顶层不是 dict（如列表）→ 静默降级."""
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    bb.write_yaml("dna_structured.yaml", ["unexpected"])
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "DNA 创作手法样本库" not in user


def test_planner_dna_structured_empty_silent(tmp_path):
    """空字典 / 所有桶都空 → 静默降级."""
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    bb.write_yaml("dna_structured.yaml", {
        "schema_version": 1,
        "tips_by_chapter_type": {},
        "tips_by_scene_purpose": {},
        "hook_recipes": {},
        "universal": {},
    })
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "DNA 创作手法样本库" not in user


def test_read_dna_tips_for_generator_has_generator_usage_hint(tmp_path):
    """Generator 版本的 header 包含 'Generator' 语境的使用说明."""
    from src.agents.planner import _read_dna_tips
    from src.blackboard import Blackboard
    bb = Blackboard(root=tmp_path)
    bb.write_yaml("dna_structured.yaml", {
        "schema_version": 1,
        "tips_by_chapter_type": {"战斗": ["x"]},
    })
    block, inputs = _read_dna_tips(bb, for_agent="generator")
    assert block
    # Generator 用法提示里要提 scene.purpose
    assert "scene.purpose" in block


def test_read_dna_tips_for_planner_has_planner_usage_hint(tmp_path):
    from src.agents.planner import _read_dna_tips
    from src.blackboard import Blackboard
    bb = Blackboard(root=tmp_path)
    bb.write_yaml("dna_structured.yaml", {
        "schema_version": 1,
        "tips_by_chapter_type": {"布局": ["y"]},
    })
    block, inputs = _read_dna_tips(bb, for_agent="planner")
    assert block
    # Planner 用法提示里要提 chapter_type 决策
    assert "决定 chapter_type" in block
