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
1. 「了」字泛滥 — 每段 ≥5 个「了」或整段都是「VV 了」式的机械时态；单个「了」不算
2. 固定句式连续 — 同一结构（主谓宾、动宾式）连续 3 句以上完全相同
3. 形容词堆砌 — 单个名词前挂 2 个以上修饰词（❌「那道温柔的、悠长的、宛如微风的叹息」）
4. 四字成语串烧 — 连续 3 个或更多的四字词组（❌「气势汹汹、杀气腾腾、怒不可遏」）
5. 机械排比 — 「一VO，一VO，一VO」三连、「不X，不Y，不Z」三连
6. 转折词滥用 — 虽然/但是/然而 在一段内出现 2 次以上
7. 空泛抒情 — 「内心如同翻江倒海」「心头涌起万千思绪」等套话
8. 模板化开篇 — 「夜深了」「阳光洒在」「时光流逝」等
9. AI 式说教 — 段末或章末的「这个故事告诉我们...」/「每个人都...」
10. 过度完美逻辑 — 段内每句之间都用「因为...所以...」链接，没有呼吸
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
            "hits（每条：criterion_id、severity、snippet、suggested_rewrite）。\n"
            "\n"
            "**约束**：\n"
            "1. hits 数组最多 8 条，只报 severity=moderate 或 severe 的；minor 不报\n"
            "2. suggested_rewrite 必须严格 ≤ snippet 字节长度，绝对不允许变长\n"
            "3. suggested_rewrite 必须保留 snippet 中的所有名词、人名、地名、核心意象\n"
            "4. snippet ≤ 60 字\n"
            '5. severity 取值为 "moderate" 或 "severe"（minor 直接删掉不输出）\n'
            "\n"
            "**自拒条款**：如果你想不到明显更好的改写——改完只是换个说法、长度相当、\n"
            "可改可不改——就不要输出该条 hit。每条 hit 都必须有质变。\n"
            "如果某类未命中，不要强行编造。\n"
            "\n"
            "✋ 输出前逐条自查:\n"
            "A. suggested_rewrite 长度是否 ≤ snippet 长度？若否，重写或删除本条。\n"
            "B. 是否保留了所有人名、地名、核心名词？若否，重写。\n"
            "C. 是否确实显著优于原文？若只是换个写法，删除本条 hit。\n"
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
                            "severity": "moderate",
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
            sev = h.get("severity", "moderate")
            md_lines.append(f"## 问题 {i} — 规则 {h.get('criterion_id', '?')} · 严重度 {sev}")
            md_lines.append("")
            md_lines.append(f"**原文**：{h.get('snippet', '')}")
            md_lines.append("")
            md_lines.append(f"**建议改写**：{h.get('suggested_rewrite', '')}")
            md_lines.append("")

        bb.write_text(f"fixes/ch{chapter:03d}.slop-patch.md", "\n".join(md_lines))
