"""CharacterGuard — background auditor for character drift / OOC behavior.

Reads:
  - state/chapters/ch{N:03d}.md
  - state/characters.yaml
  - state/summaries/ch*.md   (all prior summaries, for consistency checks)

Writes:
  - state/fixes/ch{N:03d}.char-patch.md

Independent Fan-Out partner to AISlopGuard. Both run per chapter on
separate threads via pipeline.py.
"""
from __future__ import annotations

import json

from ..agents._base import BaseAgent
from ..blackboard import Blackboard


class CharacterGuard(BaseAgent):
    name = "character_guard"
    temperature = 0.2
    response_format = "json"
    max_tokens = 3000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        text = bb.read_text(chapter_path)
        characters = bb.read_text("characters.yaml")
        inputs_read = [f"state/{chapter_path}", "state/characters.yaml"]

        # Gather all prior summaries for consistency check
        prior_summaries_parts = []
        for n in range(1, chapter):
            p = f"summaries/ch{n:03d}.md"
            if bb.exists(p):
                prior_summaries_parts.append(f"### 第 {n} 章摘要\n" + bb.read_text(p))
                inputs_read.append(f"state/{p}")
        prior_block = (
            "\n\n".join(prior_summaries_parts)
            if prior_summaries_parts
            else "（这是首章，无前情）"
        )

        system = (
            "你是专门扫描人设偏移（OOC）的独立审计员。\n"
            "你的职责范围只有人设一致性——AI 味、剧情 pacing 等问题不归你管。\n"
            "\n"
            "# 你的判据\n"
            "\n"
            "1. 主角行为是否违反 characters.yaml 中的 traits 或 redlines？\n"
            "   - 比如『极致利己』的主角突然圣母心发作？\n"
            "   - 比如『不碰毒品生意』被越界？\n"
            "2. 配角行为是否与该配角的 motivation 或 loyalty_source 一致？\n"
            "3. 角色之间的关系发展是否有前文铺垫支撑（不看大纲，只看前情摘要）？\n"
            "4. 口头禅、说话风格是否与角色标签一致？\n"
            "\n"
            "# 输出要求\n"
            "\n"
            "严格 JSON。包含 ooc_score（0 零偏移 — 10 严重崩坏）、hits（每条：character、\n"
            "deviation（如何偏移）、prior_baseline（依据）、suggested_fix）。\n"
            "宁可漏判也不要强行编造。\n"
        )

        user = (
            f"# 人物档案 (characters.yaml)\n\n```yaml\n{characters}\n```\n\n"
            f"# 前情摘要\n\n{prior_block}\n\n"
            f"# 待审章节（第 {chapter} 章）\n\n{text}\n\n"
            f"# 输出 JSON 结构示例\n"
            + json.dumps(
                {
                    "ooc_score": 2,
                    "hits": [
                        {
                            "character": "<角色名>",
                            "deviation": "<具体说明本章哪里违反了该角色的 trait/redline/motivation>",
                            "prior_baseline": "<引用 characters.yaml 或前情摘要作为依据>",
                            "suggested_fix": "<具体的修改方向>",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        import re

        s = raw.strip()
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
        if m:
            s = m.group(1)
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            obj = {
                "ooc_score": -1,
                "hits": [],
                "_parse_error": str(e),
                "_raw_excerpt": raw[-500:],
            }

        md = [
            f"# CharacterGuard 补丁 · 第 {chapter} 章",
            "",
            f"**OOC 偏移分数**：{obj.get('ooc_score', 'N/A')} / 10",
            "",
            f"**命中数**：{len(obj.get('hits', []))}",
            "",
        ]
        for i, h in enumerate(obj.get("hits", []), 1):
            md += [
                f"## 问题 {i} — {h.get('character', '?')}",
                "",
                f"**偏移**：{h.get('deviation', '')}",
                "",
                f"**基线依据**：{h.get('prior_baseline', '')}",
                "",
                f"**建议修复**：{h.get('suggested_fix', '')}",
                "",
            ]
        bb.write_text(f"fixes/ch{chapter:03d}.char-patch.md", "\n".join(md))
