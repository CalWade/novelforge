"""Generator — writes the actual chapter prose in Chinese.

Reads:
  - state/chapters/ch{N:03d}.plan.json   (Planner's beat sheet)
  - state/characters.yaml                (character canon, yaml)
  - rules/writing-style.md               (style canon)
  - rules/era-1983-hk.md                 (setting fact sheet, excerpted)
  - state/summaries/ch{N-1}.md           (continuity from prior chapter)

Writes:
  - state/chapters/ch{N:03d}.md   (~3000 Chinese characters)

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

        writing_style = self._read_rule("writing-style.md")
        era = self._read_rule("era-1983-hk.md")

        inputs_read = [
            f"state/{plan_path}",
            "state/characters.yaml",
            "rules/writing-style.md",
            "rules/era-1983-hk.md",
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

        system = (
            "你是一名职业网文作家，专精 1980s 港综同人小说。\n"
            "你现在要把下面这份节拍表写成 3000 字左右的中文章节正文。\n"
            "\n"
            "# 绝对铁律\n"
            "1. Show-Don't-Tell：不直接宣告情绪（❌他很愤怒），用行动细节展示（✅他捏碎了茶杯）。\n"
            "2. 严禁 AI 味：\n"
            "   - 少用『了』字\n"
            "   - 避免『虽然...但是...』这类转折词堆砌\n"
            "   - 避免四字成语堆砌，避免固定句式\n"
            "   - 段落长短错落，每段 1 个核心信息点，3-5 行\n"
            "3. 港味：1983 年的香港。街道、物价、粤语俚语（咪郁/扑街/靓仔/睇场）、茶餐厅、\n"
            "   公屋、九龙城寨等细节要真实具体。必要时直接用粤语对白，普通话读者能看懂即可。\n"
            "4. 人物动机必须利益化：主角救人必须有算计；反派不能降智；配角不是工具人。\n"
            "5. 严格按节拍表的 scene 顺序写，不遗漏也不擅自新增情节。\n"
            "6. 开篇必须用 opening_hook 的精神（不是一字不改地抄），结尾必须留下 closing_hook。\n"
            "7. 不写任何元注释、不加章节小标题以外的任何 meta 内容。\n"
            "8. 输出格式：第一行是章节标题（用 Markdown # 号），然后正文。\n"
            "\n"
            "# 写作风格规范（节选）\n\n"
            + writing_style
            + "\n\n# 1983 香港背景参考（节选，按需调用）\n\n"
            + era
        )

        user = (
            f"# 本章节拍表\n\n```json\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n```\n\n"
            f"# 本章出场人物档案\n\n```yaml\n{cast_block}\n```\n\n"
            f"# 上一章摘要（连续性用，不是复述）\n\n"
            + (prior_summary if prior_summary else "（这是首章）")
            + "\n\n"
            f"# 任务\n\n"
            f"严格按节拍表把本章（第 {chapter} 章）写成 3000 字左右的中文小说正文。"
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
