"""ResourceLedger — maintain state/resource_ledger.md based on resource_schema.yaml.

Motivation (skill #6):
  Numerical resources drift without a ledger. `particle_ledger.md` in the
  skill is specifically for 万粒 (million-particle system), but the general
  principle is: any setting with trackable resources (灵石 / 情报值 / 黑金 /
  人情) needs a per-chapter ledger so we can detect when prose says "暴涨"
  or jumps scale without justification.

This agent is OPTIONAL. It only runs if the setting pack provides
`resource_schema.yaml`. Urban-romance and other non-numeric settings simply
skip this step.

Lesson 3 boundary:
  ResourceLedger reads CHAPTER PROSE + schema + prior ledger. It does NOT
  read plan / verdict / issues. Numbers come from what the prose actually
  says, not from what was planned.

Reads:
  - state/resource_schema.yaml          — which resources to track (required)
  - state/chapters/ch{N:03d}.md
  - state/resource_ledger.md            — previous ledger (may not exist)

Writes:
  - state/resource_ledger.md            — Markdown table, overwritten each time
"""
from __future__ import annotations

import yaml

from ._base import BaseAgent
from ..blackboard import Blackboard


RESOURCE_LEDGER_SKELETON_HEADER = """\
# 资源账本 (resource_ledger.md)

> 本文件根据 `resource_schema.yaml` 自动维护。每章末尾由 ResourceLedger
> 从正文抽取资源变动，覆盖式更新。
> **正文是 ground truth**——如果正文与本账本冲突，以正文为准（下一次刷新修正）。

"""


def setting_has_resource_schema(bb: Blackboard) -> bool:
    """True if the active setting provides resource_schema.yaml."""
    return bb.exists("resource_schema.yaml")


class ResourceLedger(BaseAgent):
    name = "resource_ledger"
    temperature = 0.2
    response_format = "text"
    max_tokens = 3000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        schema_path = "resource_schema.yaml"
        if not bb.exists(schema_path):
            raise RuntimeError(
                "ResourceLedger called but setting has no resource_schema.yaml. "
                "Pipeline should skip this agent for such settings."
            )
        schema = bb.read_yaml(schema_path)
        schema_text = yaml.safe_dump(
            schema, allow_unicode=True, sort_keys=False, default_flow_style=False
        )

        chapter_path = f"chapters/ch{chapter:03d}.md"
        chapter_text = bb.read_text(chapter_path)

        if bb.exists("resource_ledger.md"):
            prior_ledger = bb.read_text("resource_ledger.md")
            prior_note = "（下方是上一版资源账本。请增量更新对应资源的当前值。）"
        else:
            prior_ledger = RESOURCE_LEDGER_SKELETON_HEADER + (
                "\n## 当前余额\n\n"
                "| 资源 ID | 显示名 | 单位 | 当前量 | 最近一次变动（章+原因） | 备注 |\n"
                "|---|---|---|---|---|---|\n"
                "| | | | | | |\n"
            )
            prior_note = "（本章是首章或首次生成，下方是空骨架，请按 schema 初始化每一项。）"

        inputs_read = [f"state/{schema_path}", f"state/{chapter_path}"]
        if bb.exists("resource_ledger.md"):
            inputs_read.append("state/resource_ledger.md")

        system = (
            "你是一个客观的资源账本员。任务：根据 `resource_schema.yaml` 所定义的资源，\n"
            "从章节正文中抽取本章的资源变动，覆盖式更新 `resource_ledger.md`。\n"
            "\n"
            "# 硬规则\n"
            "1. 只读 schema、正文、上一版账本。**不读** plan / verdict / issues。\n"
            "2. 账本只跟踪 schema 中声明的资源。**不得**自己发明新资源类型。\n"
            "3. 每一项变动必须有正文依据——不得凭空填数值。如果正文用模糊词（schema 的\n"
            "   `forbidden_fuzzy_terms`）代替数字，**不要猜**，在备注栏标注『正文模糊：<原文片段>』。\n"
            "4. 输出结构（Markdown）：\n"
            "   - 『当前余额』总表：所有资源的当前值\n"
            "   - 『本章变动』详情表：本章发生了哪些变动（资源 / 方向 / 数量 / 原因 / 正文引文）\n"
            "5. 变动量必须符合 schema 的 `baseline_scale`。如果单次变动超过既有样本 3 倍，\n"
            "   必须在备注中解释稀有性或复合来源；超过 10 倍则直接在备注标注『⚠ 异常：\n"
            "   建议 Evaluator 审 landmine_power_scaling』。\n"
            "6. 境界/地位类资源（非数字型），用枚举值记录（如『炼气五层』、『坐上台面』），\n"
            "   不强行数字化。\n"
            "7. 使用简体中文。直接用资源 ID 作为第一列，第二列显示名。\n"
            "\n"
            "# 不允许的输出\n"
            "- 整段散文（必须用表格）\n"
            "- 根据 plan『打算』变动的资源（只记录正文实际发生的）\n"
            "- 超出 schema 的资源类型\n"
            "- 用模糊词代替数值（『大量增加』『显著提升』）\n"
            "\n"
            f"# 当前 resource_schema.yaml\n\n```yaml\n{schema_text}\n```\n"
        )

        user = (
            f"# 上一版资源账本 {prior_note}\n\n"
            f"```markdown\n{prior_ledger}\n```\n\n"
            f"# 第 {chapter} 章正文（抽取事实的唯一来源）\n\n"
            f"{chapter_text}\n\n"
            f"# 任务\n\n"
            f"输出更新后的完整 `resource_ledger.md`。第一行是 `# 资源账本 (resource_ledger.md)`。\n"
            f"严格遵守骨架（当前余额 + 本章变动 两张表）。"
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        bb.write_text("resource_ledger.md", text + "\n")


def read_resource_ledger(bb: Blackboard) -> tuple[str, list[str]]:
    """Helper for Evaluator/Planner to cross-reference numerical claims."""
    if bb.exists("resource_ledger.md"):
        return bb.read_text("resource_ledger.md"), ["state/resource_ledger.md"]
    return "（本 setting 未启用资源账本，或账本尚未产出）", []
