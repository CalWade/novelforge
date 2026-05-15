"""CharacterGuard dual-source tests (基线 + cast).

After the 2026-05-15 重构 CharacterGuard 同时读 characters.yaml（基线宪法）
和 characters-cast.yaml（运行时演员表），区分两套判据。这些测试验证：
- cast 文件存在时，inputs_read 加上 cast 路径，prompt 同时引用两份档案
- cast 不存在时，向后兼容（不抛错）
- system prompt 在两种模式下分别给出"基线宪法 vs 先例库"两套判据
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.blackboard import Blackboard
from src.auditors.character_guard import CharacterGuard


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    b = Blackboard(root=tmp_path)
    (tmp_path / "chapters").mkdir(exist_ok=True)
    (tmp_path / "summaries").mkdir(exist_ok=True)
    (tmp_path / "fixes").mkdir(exist_ok=True)
    b.write_yaml(
        "characters.yaml",
        {"protagonist": {"name": "林家耀", "traits": ["极致利己"]}},
    )
    return b


def test_character_guard_reads_cast_when_present(bb):
    """cast 存在 → inputs_read 包含它；user prompt 包含 cast 内容（角色名/标签）。"""
    bb.write_yaml(
        "characters-cast.yaml",
        {
            "schema_version": 1,
            "last_updated_chapter": 2,
            "cast": [
                {
                    "name": "老刘",
                    "in_baseline": False,
                    "first_appeared_ch": 1,
                    "last_appeared_ch": 2,
                    "status": "active",
                    "role": "配角",
                    "traits": ["话痨", "贪财"],
                    "voice_tags": ["语尾常带『阿耀啊』"],
                }
            ],
        },
    )
    bb.write_text("chapters/ch003.md", "本章正文。老刘登场。")

    _, user, inputs = CharacterGuard()._build_prompts(bb, chapter=3)
    assert "state/characters-cast.yaml" in inputs
    assert "state/characters.yaml" in inputs
    # cast 中的关键标签出现在 user prompt 里
    assert "老刘" in user
    assert "话痨" in user or "贪财" in user
    assert "voice_tags" in user or "阿耀啊" in user


def test_character_guard_works_without_cast(bb):
    """cast 不存在 → inputs 不含 cast；prompt 不引用 cast；不抛错。"""
    bb.write_text("chapters/ch001.md", "首章正文")

    system, user, inputs = CharacterGuard()._build_prompts(bb, chapter=1)
    assert not any("characters-cast.yaml" in p for p in inputs)
    # prompt 中不出现"档案 B / 演员表"段落（旧模式）
    assert "档案 B" not in user
    assert "档案 B" not in system


def test_character_guard_prompt_distinguishes_baseline_vs_cast(bb):
    """cast 存在 → system prompt 同时含 "基线宪法" 和 "运行时演员表" 两个语义段。"""
    bb.write_yaml(
        "characters-cast.yaml",
        {"schema_version": 1, "last_updated_chapter": 1, "cast": []},
    )
    bb.write_text("chapters/ch002.md", "正文")

    system, user, _ = CharacterGuard()._build_prompts(bb, chapter=2)
    # 两套判据分别出现
    assert "基线宪法" in system
    assert "运行时演员表" in system or "先例库" in system
    # 报警分级语义
    assert "严重 OOC" in system
    assert "中等" in system or "自相矛盾" in system
    # "本章首次出现的全新角色 不报警" 这条规则
    assert "首次出现" in system
    # user prompt 里两个档案标签
    assert "档案 A" in user
    assert "档案 B" in user


def test_character_guard_old_mode_no_baseline_drift_label(bb):
    """旧模式（无 cast）的 system prompt 不应该混入双档术语。"""
    bb.write_text("chapters/ch001.md", "正文")
    system, user, _ = CharacterGuard()._build_prompts(bb, chapter=1)
    assert "档案 A" not in user
    assert "档案 B" not in user
    # 但应该提到 cast tracking 未启用（让用户知道为什么没看到先例判据）
    assert "cast tracking" in system or "characters-cast.yaml" in system
