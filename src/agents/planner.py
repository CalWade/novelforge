"""Planner — produces the beat sheet for a given chapter.

Reads:
  - state/outline.json (this chapter's entry + 1 prior + 1 next for context)
  - state/progress.json (for progress awareness, not for context accumulation)
  - state/summaries/ch{N-1}.md and ch{N-2}.md (at most, if exist)

Writes:
  - state/chapters/ch{N:03d}.plan.json

The Planner does NOT write prose. It takes the outline's high-level beats
and turns them into a fine-grained scene-by-scene plan the Generator can
execute faithfully.
"""
from __future__ import annotations

import json
import re

from ._base import BaseAgent
from ..blackboard import Blackboard


class Planner(BaseAgent):
    name = "planner"
    temperature = 0.4
    response_format = "json"
    max_tokens = 3000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        outline = bb.read_json("outline.json")
        chapters = outline["chapters"]
        # Find the current chapter entry
        cur = next((c for c in chapters if c["ch"] == chapter), None)
        if cur is None:
            raise ValueError(f"Chapter {chapter} not in outline")

        # Setting metadata for the persona line
        try:
            setting = bb.read_yaml("setting.yaml")
        except (OSError, Exception):
            setting = {}
        genre = setting.get("genre", "通用小说")
        era_label = setting.get("era", "")

        # Multi-level summary context (L1 last-2 + L2 most-recent-arc +
        # L3 most-recent-volume if applicable). This scales to 50+ chapters
        # without context overflow.
        from .multi_level_summarizer import assemble_long_chain_context
        from .status_card_updater import read_current_status_card
        from .hook_keeper import read_pending_hooks

        prior_summary_block, summary_inputs = assemble_long_chain_context(bb, chapter)
        status_card_text, status_card_inputs = read_current_status_card(bb)
        pending_hooks_text, pending_hooks_inputs = read_pending_hooks(bb)
        inputs_read: list[str] = (
            ["state/outline.json", "state/setting.yaml"]
            + summary_inputs
            + status_card_inputs
            + pending_hooks_inputs
        )

        system = (
            f"你是拥有 20 年经验的网络小说责编。当前题材：{genre}；时代/世界观：{era_label}。\n"
            "你的任务：把一章的『大纲条目』细化为 Generator 可以直接下笔的『节拍表』。\n"
            "绝对铁律：\n"
            "1. 严格输出 JSON，不写任何散文或解释。\n"
            "2. 每个 scene（场景）必须包含：scene_id、场景地点、出场人物、冲突或张力、"
            "目的（推进主线/塑造人物/埋伏笔）、预估字数。\n"
            "3. 一章拆成 3-5 个 scene，总字数目标 ~3000 字。\n"
            "4. 每个 scene 必须提供至少 2 处『具体感官细节』的写作提示（视觉/听觉/触觉/气味/味觉）。\n"
            "5. 必须给出开篇钩子（opening_hook，≤30 字）和章末钩子（closing_hook，≤40 字）。\n"
            "6. 必须列出 3-5 个 landmines_to_avoid（写作时要回避的具体雷点）。\n"
            "7. 不编造大纲里没有的情节，但可以为大纲的 beats 补充细节与过渡。\n"
            "8. **必读『当前状态卡』**：如果存在，它是当前时间点的权威状态覆盖文件——\n"
            "   时间锚点、敌我关系、资源、已知真相、活跃伏笔、建议的下一章任务都以它为准。\n"
            "   计划中的 scene 必须与状态卡一致；状态卡的『下一章任务卡』是你写本章 plan 的**种子建议**。\n"
            "   如果大纲和状态卡冲突（如主角已在状态卡中死亡但大纲仍让他出场），以**最新正文+状态卡**为准。\n"
        )

        cur_json = json.dumps(cur, ensure_ascii=False, indent=2)
        user = (
            f"# 本章（第 {chapter} 章）大纲条目\n\n```json\n{cur_json}\n```\n\n"
            f"# 当前状态卡（当前时间点的权威状态，优先于摘要；冲突以正文+状态卡为准）\n\n"
            f"{status_card_text}\n\n"
            f"# 待回收伏笔池（优先安排回收旧钩子，不要只埋新坑）\n\n"
            f"{pending_hooks_text}\n\n"
            f"# 前情摘要（Context Reset，只有这一点上下文）\n\n{prior_summary_block}\n\n"
            f"# 输出 JSON 结构\n\n"
            "```json\n"
            "{\n"
            '  "ch": <int>,\n'
            '  "title": "<str>",\n'
            '  "opening_hook": "<≤30字>",\n'
            '  "scenes": [\n'
            "    {\n"
            '      "scene_id": 1,\n'
            '      "location": "<str>",\n'
            '      "cast": ["<人名>", ...],\n'
            '      "conflict": "<一句话冲突/张力>",\n'
            '      "purpose": "推进主线|塑造人物|埋伏笔",\n'
            '      "sensory_prompts": ["<细节1>", "<细节2>"],\n'
            '      "word_target": <int>\n'
            "    }, ...\n"
            "  ],\n"
            '  "closing_hook": "<≤40字>",\n'
            '  "landmines_to_avoid": ["<具体雷点>", ...]\n'
            "}\n"
            "```"
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        # Parse JSON, be forgiving of common LLM quirks
        plan = _parse_json(raw)
        plan["ch"] = chapter  # enforce consistency
        bb.write_json(f"chapters/ch{chapter:03d}.plan.json", plan)


def _parse_json(raw: str):
    """Strip ```json fences if present, then json.loads."""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    return json.loads(s)
