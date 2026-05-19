"""PlotArcDrafter: ultimate_goal (one line) → 4-act plot_arc.yaml dict.

Mirrors the test style in test_outline_drafter.py / test_characters_drafter.py.
"""
from __future__ import annotations

import yaml
import pytest


@pytest.fixture
def stub_llm_4acts(monkeypatch):
    """Patch llm.chat to return a canned YAML 4-act skeleton."""
    captured = {}

    def fake_chat(system, user, *, agent_name, **kwargs):
        captured["system"] = system
        captured["user"] = user
        captured["agent_name"] = agent_name
        return yaml.safe_dump({
            "schema_version": 1,
            "total_chapters": 50,
            "ultimate_goal": "find the source",
            "acts": [
                {"name": "暗格觉醒", "range": [1, 12],
                 "goal": "主角发现契书暗面",
                 "must_close_by_end": ["第七个客户失踪", "钢笔套来源"]},
                {"name": "锅炉房真相", "range": [13, 25],
                 "goal": "深入灰烬池",
                 "must_close_by_end": ["灰舌联络网", "右眼代价"]},
                {"name": "灰塔", "range": [26, 37],
                 "goal": "对抗灰烬贵族",
                 "must_close_by_end": ["第七日机制", "贵族身份"]},
                {"name": "解契约", "range": [38, 50],
                 "goal": "破解自身契约",
                 "must_close_by_end": ["契书源头", "终极代价"]},
            ],
        }, allow_unicode=True, sort_keys=False)

    monkeypatch.setattr("src.llm.chat", fake_chat)
    return captured


def test_drafter_run_returns_4_acts(stub_llm_4acts):
    from src.agents.plot_arc_drafter import run
    out = run(
        ultimate_goal="苏烬要找出灰烬契书源头",
        chapter_count_target=50,
    )
    assert out["schema_version"] == 1
    assert out["total_chapters"] == 50
    assert len(out["acts"]) == 4
    # ultimate_goal 必须用用户传入的（不是 LLM 返回的，user-typed wins）
    assert out["ultimate_goal"] == "苏烬要找出灰烬契书源头"


def test_drafter_acts_cover_all_chapters(stub_llm_4acts):
    """50 章 acts.range 必须连续覆盖 1..50 无空隙无重叠。"""
    from src.agents.plot_arc_drafter import run
    out = run(ultimate_goal="x", chapter_count_target=50)
    expected_start = 1
    for act in out["acts"]:
        s, e = act["range"]
        assert s == expected_start, f"act {act['name']} starts at {s}, expected {expected_start}"
        assert e >= s
        expected_start = e + 1
    assert expected_start - 1 == 50


def test_drafter_each_act_has_goal_and_must_close(stub_llm_4acts):
    """每卷必含 goal 字段 + must_close_by_end 列表。"""
    from src.agents.plot_arc_drafter import run
    out = run(ultimate_goal="x", chapter_count_target=50)
    for act in out["acts"]:
        assert "goal" in act
        assert isinstance(act["goal"], str)
        assert "must_close_by_end" in act
        assert isinstance(act["must_close_by_end"], list)


def test_drafter_milestones_left_empty(stub_llm_4acts):
    """milestones / anchor_quota 不应出现（让作者后续打磨）。"""
    from src.agents.plot_arc_drafter import run
    out = run(ultimate_goal="x", chapter_count_target=50)
    for act in out["acts"]:
        assert "milestones" not in act
        assert "anchor_quota" not in act


def test_drafter_uses_era_excerpt_in_prompt(stub_llm_4acts):
    """era_md_excerpt 必须出现在 user prompt 里（让 LLM 命名时能用题材词汇）。"""
    from src.agents.plot_arc_drafter import run
    excerpt = "灰烬纪年第三年深秋，G22 服务区，灰烬契书"
    run(
        ultimate_goal="x",
        chapter_count_target=50,
        era_md_excerpt=excerpt,
    )
    assert excerpt in stub_llm_4acts["user"]


def test_drafter_empty_goal_returns_shell():
    """空 ultimate_goal → equipartition shell，不调 LLM。"""
    from src.agents.plot_arc_drafter import run
    out = run(ultimate_goal="", chapter_count_target=50)
    assert len(out["acts"]) == 4
    # 等分 50 = 13 + 13 + 12 + 12
    assert out["acts"][0]["range"] == [1, 13]
    assert out["acts"][-1]["range"][1] == 50


def test_drafter_bad_yaml_falls_back_to_shell(monkeypatch):
    """LLM 返回非 YAML 时，用 shell 兜底（不抛异常）。"""
    def bad_chat(system, user, *, agent_name, **kwargs):
        return ":::not yaml at all\n\t- bad indent"
    monkeypatch.setattr("src.llm.chat", bad_chat)
    from src.agents.plot_arc_drafter import run
    out = run(ultimate_goal="x", chapter_count_target=20)
    assert out["schema_version"] == 1
    assert out["total_chapters"] == 20
    assert len(out["acts"]) == 4
    # range 必须仍然覆盖 1..20
    assert out["acts"][0]["range"][0] == 1
    assert out["acts"][-1]["range"][1] == 20


def test_drafter_output_passes_plot_arc_validation(stub_llm_4acts, tmp_path, monkeypatch):
    """drafter 输出 dump 成 yaml 后必须能被 read_plot_arc 解析（schema 一致性）。"""
    from src.agents.plot_arc_drafter import run
    from src.tools.plot_arc import read_plot_arc

    out = run(ultimate_goal="x", chapter_count_target=50)
    plot_arc_yaml = tmp_path / "plot_arc.yaml"
    plot_arc_yaml.write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    arc = read_plot_arc(tmp_path)
    assert arc is not None
    assert arc.total_chapters == 50
    assert len(arc.acts) == 4
