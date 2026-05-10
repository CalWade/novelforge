"""HookKeeper — maintain state/pending_hooks.md (the unresolved-hook ledger).

Motivation (skill #7):
  Long-chain novels drop hooks if no ledger tracks them. `closing_hook` in
  each plan.json is local to that chapter. After 10+ chapters, hooks blur.
  HookKeeper keeps ONE authoritative table of all unresolved hooks:
    - hook_id / 起始章节 / 类型 / 当前状态 / 最近推进 / 预期回收窗口 / 备注
    - Three priority types: 逃敌 / 未拿到的宝物 / 未解释的耳语
    - Other tracked: 血仇 / 誓约 / 暗线身份 / 未公开交易

Runs AFTER StatusCardUpdater (so the status card already has current-turn info).

Reads:
  - state/chapters/ch{N:03d}.md       — the fresh chapter prose
  - state/pending_hooks.md             — previous ledger (or empty for ch1)
  - state/current_status_card.md       — cross-reference for current state

Writes:
  - state/pending_hooks.md             — Markdown table, overwritten each time

Lesson 3 boundary:
  HookKeeper reads CHAPTER PROSE and the two ledgers. It does NOT read
  plan.json, verdict.json, issues.jsonl. Hooks are extracted from the PROSE,
  not from what Planner *intended* to plant — if Generator forgot to plant
  a planned hook, it simply is not in the ledger (which is correct — it
  doesn't exist in the finished work).
"""
from __future__ import annotations

from ._base import BaseAgent
from ..blackboard import Blackboard


PENDING_HOOKS_SKELETON = """\
# 待回收伏笔池 (pending_hooks.md)

> 唯一的待回收伏笔登记表。正文中埋下但尚未回收的线索都在这里。
> 由 HookKeeper 在每章末尾（StatusCardUpdater 之后）覆盖式更新。
> Planner 写每卷首章 plan 前必读本表，优先安排回收旧钩子。

## 当前活跃伏笔

| hook_id | 起始章 | 类型 | 当前状态 | 最近推进 | 预期回收窗口 | 备注 |
|---|---|---|---|---|---|---|

> 字段含义：
> - **hook_id**：短标识符，建议 `type-N` 格式（如 `escapee-1` / `relic-2` / `whisper-3` / `vendetta-1` / `oath-1` / `identity-1` / `deal-1`）
> - **类型**：逃敌 / 宝物 / 耳语 / 血仇 / 誓约 / 暗线身份 / 未公开交易
> - **当前状态**：待推进 / 推进中 / 待回收 / 即将回收
> - **最近推进**：最近出现它的章节 + 一句话进展
> - **预期回收窗口**：大致章节区间（如 `ch20-ch25`），无法估计写 `未定`

## 已回收伏笔（本章刚关闭）

| hook_id | 起始章 | 回收章 | 回收方式 | 备注 |
|---|---|---|---|---|

> 本表**只保留本章关闭的伏笔**，下一轮会被清空（历史回收不滚动累积，避免膨胀）。

"""


class HookKeeper(BaseAgent):
    name = "hook_keeper"
    temperature = 0.2
    response_format = "text"
    max_tokens = 3000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        chapter_text = bb.read_text(chapter_path)

        if bb.exists("pending_hooks.md"):
            prior_hooks = bb.read_text("pending_hooks.md")
            prior_note = "（下方是上一版伏笔池。保留仍活跃的，删除本章回收的，新增本章埋下的。）"
        else:
            prior_hooks = PENDING_HOOKS_SKELETON
            prior_note = "（本章是首章或首次生成，下方是空白骨架——请从本章正文中抽取所有新埋伏笔填入活跃表。）"

        if bb.exists("current_status_card.md"):
            status_card = bb.read_text("current_status_card.md")
            status_inputs = ["state/current_status_card.md"]
            status_note = "用于交叉验证：状态卡中的活跃伏笔应与本文件一致。"
        else:
            status_card = "（尚无状态卡）"
            status_inputs = []
            status_note = "状态卡尚未生成。"

        inputs_read = [f"state/{chapter_path}"] + status_inputs
        if bb.exists("pending_hooks.md"):
            inputs_read.append("state/pending_hooks.md")

        system = (
            "你是一个客观的伏笔登记员。任务：维护 `pending_hooks.md`——\n"
            "**待回收伏笔池**的唯一登记表。\n"
            "\n"
            "# 硬规则\n"
            "1. 只读传入的章节正文、上一版伏笔池、状态卡。**不读** plan / verdict / issues。\n"
            "2. 伏笔来源必须是**正文真实出现**的线索，不是『大纲里想写但没写』的。\n"
            "3. 分三类重点跟踪：\n"
            "   - **逃敌**（escapee）：本章未能击杀/抓获的敌人，他会回来。\n"
            "   - **宝物**（relic）：本章提及但主角未拿到的重要物品/资源。\n"
            "   - **耳语**（whisper）：本章出现的未解释的暗示、谜语、流言、预言。\n"
            "4. 其他也要跟踪：血仇（vendetta）/ 誓约（oath）/ 暗线身份（identity）/ 未公开交易（deal）。\n"
            "5. **本章回收的伏笔**：从『当前活跃伏笔』表中**删除**该行，并在『已回收伏笔』表中**新增**一行（记录回收方式）。\n"
            "6. **老伏笔本章被推进但未回收**：更新该行的『最近推进』字段为『ch{N}: 一句话进展』。\n"
            "7. **本章新埋伏笔**：在『当前活跃伏笔』表中**新增一行**。hook_id 沿用现有命名规则，不重复。\n"
            "8. 输出是**完整的 Markdown 文档**（标题 + 两张表），严格遵守骨架结构。\n"
            "9. 『已回收伏笔』表只保留本章关闭的伏笔，下一轮覆盖时会被清空。\n"
            "10. 使用简体中文。直接用人名与地名，不用代称。\n"
            "\n"
            "# 不允许的输出\n"
            "- 整段散文叙述（必须用表格）\n"
            "- 根据 plan.json『打算』埋的伏笔（只记录正文实际埋下的）\n"
            "- 没有时间窗口/状态/推进痕迹的模糊钩子（至少要有『起始章』和『当前状态』）\n"
            "- 本章首次出现但已在当章完全解决的线索（那不是伏笔，是闭环）\n"
        )

        user = (
            f"# 上一版伏笔池 {prior_note}\n\n"
            f"```markdown\n{prior_hooks}\n```\n\n"
            f"# 第 {chapter} 章正文（基准事实，只从正文抽取伏笔）\n\n"
            f"{chapter_text}\n\n"
            f"# 当前状态卡（交叉参考）\n\n"
            f"{status_note}\n\n"
            f"{status_card}\n\n"
            f"# 任务\n\n"
            f"输出更新后的完整 `pending_hooks.md`。第一行是 `# 待回收伏笔池 (pending_hooks.md)`。\n"
            f"保留骨架的标题层级与表头格式。"
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
        bb.write_text("pending_hooks.md", text + "\n")


def read_pending_hooks(bb: Blackboard) -> tuple[str, list[str]]:
    """Helper for Planner to read the current hook ledger."""
    if bb.exists("pending_hooks.md"):
        return bb.read_text("pending_hooks.md"), ["state/pending_hooks.md"]
    return "（尚无伏笔池——本章是首章或尚未产出）", []
