"""Planner × era_sensory_kit.yaml 集成：验证"有/无 kit"的 prompt 分支."""
from __future__ import annotations

import json

import pytest


def _mk_bb(tmp_path):
    """Build a minimal blackboard with outline + progress."""
    from src.blackboard import Blackboard
    bb = Blackboard(root=tmp_path)
    bb.write_json("progress.json", {"current_chapter": 1, "completed": []})
    bb.write_json("outline.json", {
        "title": "T", "subtitle": "", "protagonist": "林家耀",
        "chapters": [
            {"ch": 1, "title": "第一章 · 九龙城寨的第一顿饭",
             "beats": ["入城", "遇到 A", "找到 B"]},
        ],
    })
    bb.write_yaml("setting.yaml", {"genre": "黑帮 · 港综", "era": "1983 年香港"})
    return bb


def test_planner_prompt_without_kit_has_no_kit_block(tmp_path):
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    # 不写 era_sensory_kit.yaml
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "感官清单参考" not in user
    assert "era_sensory_kit.yaml" not in " ".join(inputs)


def test_planner_prompt_with_kit_injects_block(tmp_path):
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    bb.write_yaml("era_sensory_kit.yaml", {
        "schema_version": 1,
        "locations": {
            "九龙城寨": {
                "visual": ["铁皮檐锈水痕", "冷气机密密麻麻"],
                "olfactory": ["沟渠腐臭", "大排档镬气"],
                "gustatory": ["柱侯牛腩", "碱水云吞面"],
            },
            "油麻地": {
                "visual": ["果栏灯光黄"],
                "auditory": ["拖板车木轮声"],
            },
        },
    })
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)

    # user prompt 含块头、地名、至少一条词组
    assert "感官清单参考" in user
    assert "九龙城寨" in user
    assert "油麻地" in user
    assert "铁皮檐锈水痕" in user
    assert "大排档镬气" in user

    # system prompt 含"查表优先"的规则
    assert "感官清单参考" in system

    # inputs_read 里记录了这个文件
    assert "state/era_sensory_kit.yaml" in inputs


def test_planner_prompt_with_empty_kit_silent(tmp_path):
    """kit 存在但 locations 空：行为应与无 kit 一致（不插块、不声明 inputs）."""
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    bb.write_yaml("era_sensory_kit.yaml", {
        "schema_version": 1, "locations": {},
    })
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "感官清单参考" not in user
    assert "era_sensory_kit.yaml" not in " ".join(inputs)


def test_planner_prompt_with_malformed_kit_silent(tmp_path):
    """kit YAML 损坏：Planner 不应崩溃，降级为无 kit 行为."""
    from src.agents.planner import Planner
    bb = _mk_bb(tmp_path)
    # 写一份 yaml 顶层是 list 而非 dict
    bb.write_yaml("era_sensory_kit.yaml", ["unexpected shape"])
    system, user, inputs = Planner()._build_prompts(bb, chapter=1)
    assert "感官清单参考" not in user
