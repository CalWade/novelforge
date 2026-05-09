"""AISlopGuard — background auditor for AI-flavored writing.

Scans finalized chapter for AI-slop patterns only (not the full landmine list).
Fresh window, runs independently of the main plan/gen/eval/fix cycle.

Reads:
  - state/chapters/ch{N:03d}.md

Writes:
  - state/fixes/ch{N:03d}.slop-patch.md  (human-readable patch proposal)

This is the Lesson-4 artifact: a separate file users can inspect / apply
as if it were a PR from a background agent.
"""
from __future__ import annotations

import json

from ..agents._base import BaseAgent
from ..blackboard import Blackboard

# Subset of 18-landmines relevant to AI-slop only. Kept as inline text so
# the auditor's prompt stays small & focused.
AI_SLOP_CRITERIA = """
1. 「了」字过多（每段超过 4-5 个「了」就算）
2. 固定句式重复（连续 3 句以上相同结构）
3. 形容词堆砌（一个名词前挂 2+ 形容词）
4. 四字成语堆砌（连续 3 个以上四字词组）
5. 机械排比（"一X，一X，一X" 三连）
6. 转折词滥用（虽然...但是... / 然而... 过度）
7. 空泛抒情（"他的内心如同翻江倒海"）
8. 模板化开篇（"夜深了"/"阳光洒在"/"时光流逝"）
9. AI 式说教句（"这个故事告诉我们..." "每个人都..."）
10. 过度完美逻辑（情节过渡全用因为所以，没有呼吸）
"""


class AISlopGuard(BaseAgent):
    name = "ai_slop_guard"
    temperature = 0.2
    response_format = "json"
    max_tokens = 8192

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        text = bb.read_text(chapter_path)
        inputs_read = [f"state/{chapter_path}"]

        system = (
            "你是专门扫描 AI 味的独立审计员。\n"
            "你的职责范围只有 AI 味——人设、时间线、剧情主线等问题不归你管。\n"
            "\n"
            "# AI 味判据（你只看这些）\n"
            + AI_SLOP_CRITERIA
            + "\n\n"
            "# 输出要求\n"
            "严格 JSON。包含：slop_score（0 无 AI 味 — 10 满屏 AI 味）、\n"
            "hits（每条：criterion_id、snippet（原文片段，≤60 字）、suggested_rewrite）。\n"
            "**hits 数组最多 8 条**，只报最严重的。每一条 suggested_rewrite ≤60 字。\n"
            "如果某类未命中，不要强行编造。\n"
        )

        user = (
            f"# 待审章节（第 {chapter} 章）\n\n{text}\n\n"
            f"# 输出 JSON 结构示例\n"
            + json.dumps(
                {
                    "slop_score": 3,
                    "hits": [
                        {
                            "criterion_id": 1,
                            "snippet": "……",
                            "suggested_rewrite": "……",
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
            # Likely truncated JSON — record the failure transparently rather
            # than silently returning 0 hits. User sees a patch file with a
            # note to re-run the auditor.
            obj = {
                "slop_score": -1,
                "hits": [],
                "_parse_error": str(e),
                "_raw_excerpt": raw[-500:],
            }

        # Render as a human-readable patch file (Lesson 4: visible artifact)
        md_lines = [
            f"# AISlopGuard 补丁 · 第 {chapter} 章",
            "",
            f"**AI 味分数**：{obj.get('slop_score', 'N/A')} / 10",
            "",
            f"**命中数**：{len(obj.get('hits', []))}",
            "",
        ]
        for i, h in enumerate(obj.get("hits", []), 1):
            md_lines.append(f"## 问题 {i} — 规则 {h.get('criterion_id', '?')}")
            md_lines.append("")
            md_lines.append(f"**原文**：{h.get('snippet', '')}")
            md_lines.append("")
            md_lines.append(f"**建议改写**：{h.get('suggested_rewrite', '')}")
            md_lines.append("")

        bb.write_text(f"fixes/ch{chapter:03d}.slop-patch.md", "\n".join(md_lines))
