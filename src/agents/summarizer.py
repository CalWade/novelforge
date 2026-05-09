"""Summarizer — produces a tight factual summary of a finalized chapter.

CRITICAL Lesson-3 boundary:
  Summarizer reads ONLY chapters/ch{N:03d}.md (the final prose).
  It does NOT read the plan.json, verdict.json, or any issues.
  This prevents Generator's framing from leaking into future Planner calls.

Reads:
  - state/chapters/ch{N:03d}.md

Writes:
  - state/summaries/ch{N:03d}.md  (≤ 300 Chinese chars)
"""
from __future__ import annotations

from ._base import BaseAgent
from ..blackboard import Blackboard


class Summarizer(BaseAgent):
    name = "summarizer"
    temperature = 0.2
    response_format = "text"
    max_tokens = 600

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        chapter_text = bb.read_text(chapter_path)
        inputs_read = [f"state/{chapter_path}"]

        system = (
            "你是一个客观的摘要员。任务：把一章小说正文浓缩为 ≤300 字的中文摘要。\n"
            "\n"
            "硬规则：\n"
            "1. 只写事实：谁、在哪、做了什么、结果如何。\n"
            "2. 不写任何评价、感受、修辞、伏笔说明。\n"
            "3. 不复述对白，只写对白承载的信息。\n"
            "4. 严格 ≤300 字。\n"
            "5. 使用简体中文。\n"
            "6. 不要用『主角』这种代称，直接用人名。\n"
            "7. 不要加任何标题或 Markdown 结构。\n"
        )
        user = f"# 原文\n\n{chapter_text}\n\n# 任务\n\n请输出本章摘要（≤300 字）。"
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        bb.write_text(f"summaries/ch{chapter:03d}.md", raw.strip() + "\n")
