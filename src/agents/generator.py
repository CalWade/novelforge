"""Generator — writes the actual chapter prose.

Reads (all genre content comes from the active setting pack via state/):
  - state/chapters/ch{N:03d}.plan.json     — Planner's beat sheet
  - state/characters.yaml                  — character canon (setting-specific)
  - state/setting.yaml                     — active setting metadata
  - state/era.md                           — setting's world/era facts
  - state/writing-style-extra.md           — setting-specific style quirks
  - rules/writing-style-core.md            — universal style rules
  - state/summaries/ch{N-1}.md             — continuity from prior chapter

Writes:
  - state/chapters/ch{N:03d}.md   (~3000 characters)

Temperature 0.85 — prose should have voice.
"""
from __future__ import annotations

import json

from ._base import BaseAgent
from ..blackboard import Blackboard


class Generator(BaseAgent):
    name = "generator"
    temperature = 0.85
    response_format = "text"
    max_tokens = 8000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        plan_path = f"chapters/ch{chapter:03d}.plan.json"
        plan = bb.read_json(plan_path)
        characters = bb.read_yaml("characters.yaml")
        setting = bb.read_yaml("setting.yaml")

        writing_style_core = self._read_rule("writing-style-core.md")
        writing_style_extra = bb.read_text("writing-style-extra.md")
        era = bb.read_text("era.md")

        inputs_read = [
            f"state/{plan_path}",
            "state/characters.yaml",
            "state/setting.yaml",
            "state/era.md",
            "state/writing-style-extra.md",
            "rules/writing-style-core.md",
        ]

        prior_summary = ""
        if chapter >= 2:
            p = f"summaries/ch{chapter-1:03d}.md"
            if bb.exists(p):
                prior_summary = bb.read_text(p)
                inputs_read.append(f"state/{p}")

        # Excerpt character canon — keep only protagonist + cast of this chapter
        cast_names = set()
        for scene in plan.get("scenes", []):
            for c in scene.get("cast", []):
                cast_names.add(c)
        cast_block = _extract_relevant_characters(characters, cast_names)

        # Setting-driven persona lines (keep it short)
        persona_lines = setting.get("author_persona_hints", []) or []
        persona_block = (
            "\n".join(f"- {h}" for h in persona_lines)
            if persona_lines
            else "- （本 setting 未提供作者画像提示）"
        )
        genre = setting.get("genre", "通用小说")
        era_label = setting.get("era", "")
        tone = setting.get("tone", "")

        system = (
            f"你是一名职业网文作家。本次创作的题材与基调由下方 setting 决定，\n"
            f"你的任务：把节拍表写成约 3000 字的中文章节正文。\n"
            f"\n"
            f"# 当前 Setting\n"
            f"- 题材：{genre}\n"
            f"- 时代/世界观：{era_label}\n"
            f"- 基调：{tone}\n"
            f"- 作者画像提示：\n{persona_block}\n"
            f"\n"
            f"# 通用铁律\n"
            f"1. Show-Don't-Tell：不直接宣告情绪（❌他很愤怒），用行动细节展示（✅他捏碎了茶杯）。\n"
            f"2. 严禁 AI 味：少用『了』字；避免『虽然...但是...』转折词堆砌；\n"
            f"   避免四字成语堆砌与固定句式；段落长短错落，每段 1 个核心信息点，3-5 行。\n"
            f"   群像反应禁止写成『全场震惊』『众人倒吸凉气』；改为 1-2 个**具体角色**的身体反应、判断偏差或利益震荡。\n"
            f"3. 人物动机必须利益化：主角行动必须有算计；反派不能降智；配角不是工具人。\n"
            f"   留人/钓鱼/示弱/借刀可以，**前提只能是利益更大，绝不能是心软**。\n"
            f"4. 严格按节拍表的 scene 顺序写，不遗漏也不擅自新增情节。\n"
            f"5. 开篇要承接 opening_hook 的精神（不是照抄），结尾要留下 closing_hook。\n"
            f"6. 不写任何元注释、不加章节小标题以外的 meta 内容。\n"
            f"7. 输出格式：第一行章节标题（用 Markdown `# ` 前缀），然后正文。\n"
            f"8. **禁止百科式堆砌设定**。下方 era.md 是参考资料，它的事实必须**融入场景的感官/动作/对白**；\n"
            f"   严禁以解说性段落形式复述世界观、制度、时代背景。\n"
            f"9. **每个场景至少推进一项**：信息 / 地位 / 资源 / 伤亡 / 仇恨 / 境界。\n"
            f"   小冲突尽快兑现反馈，不要把爽点无限后置。\n"
            f"10. 收益必须**具体化**。不得用『更强了』『暴涨』『海量』『难以估量』掩盖数值跳变；\n"
            f"    具体落到道具名、资源单位、地位变化或已回收伏笔。\n"
            f"\n"
            f"# 动笔前自问 7 问（必须在心里过一遍，答不上的重审节拍表）\n"
            f"\n"
            f"1. 此刻主角利益最大化的选择是什么？为什么必须做这个动作？\n"
            f"2. 这场冲突是谁先动手，为什么非打不可？\n"
            f"3. 配角/反派是否有明确诉求、恐惧和反制，而不是站着等死？\n"
            f"4. 反派当前掌握了哪些已知信息、误判、盲区？哪些信息只有读者知道、反派不知道？\n"
            f"5. 反派的每一步关键动作，能否都追溯到其已知信息、资源约束、性格习惯或上一轮误判？\n"
            f"   如果不能——**重写动作链**，不是放过。\n"
            f"6. 本段剧情解决问题靠的是前文已铺垫的能力/底牌/信息，还是凭空掉设定？\n"
            f"7. 本章收益是否能落到**具体资源 / 数值增量 / 地位变化 / 已回收伏笔**，而不是抽象『更强了』？\n"
            f"\n"
            f"如果任何一个问题答不上来，先补动机链或找 Planner 重改节拍表，再写正文。\n"
            f"\n"
            f"# 通用写作风格规范\n\n"
            + writing_style_core
            + f"\n\n# 题材特有风格补充（由 setting 注入）\n\n"
            + writing_style_extra
            + f"\n\n# 时代/世界观事实包（仅供融入场景，严禁整段复述）\n\n"
            + era
        )

        user = (
            f"# 本章节拍表\n\n```json\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n```\n\n"
            f"# 本章出场人物档案\n\n```yaml\n{cast_block}\n```\n\n"
            f"# 上一章摘要（连续性用，不是复述）\n\n"
            + (prior_summary if prior_summary else "（这是首章）")
            + "\n\n"
            f"# 任务\n\n"
            f"严格按节拍表把本章（第 {chapter} 章）写成约 3000 字的中文小说正文。"
            f"第一行是章节标题（用 `# ` 前缀），接下来是正文。不要任何其他输出。"
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        bb.write_text(f"chapters/ch{chapter:03d}.md", raw.strip() + "\n")


def _extract_relevant_characters(characters: dict, names: set[str]) -> str:
    """Return a YAML-like snippet with only the relevant protagonist + supporting."""
    import yaml

    out = {}
    proto = characters.get("protagonist", {})
    if proto.get("name") in names or not names:
        out["protagonist"] = proto

    supporting = []
    for c in characters.get("supporting", []):
        if not names or c.get("name") in names or any(
            n in c.get("name", "") for n in names
        ):
            supporting.append(c)
    if supporting:
        out["supporting"] = supporting

    # Fallback: if no match, return everything (don't leave Generator blind)
    if not out or not supporting:
        out = characters

    return yaml.safe_dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False)
