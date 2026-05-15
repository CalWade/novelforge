"""Evaluator — default-reject critic with adversarial persona + JSON rubric.

This is the most important agent in the pipeline. It is what converts
"5 prompts in a for loop" into a real Planner/Generator/Evaluator triangle.

Key design (per Oracle review):
- Adversarial persona ("默认拒稿, 找不出 3 个硬伤就是失职") — inverts model bias.
- Structured JSON rubric with per-landmine hit/evidence/severity — removes
  room for hollow sycophancy.
- NEVER sees Generator's reasoning or plan — only the final chapter text.
- Cross-checks against characters.yaml + timeline.yaml.
- Loads setting-specific iron-laws-extra.md as additional criteria.

Reads (everything under state/ is setting-injected via bootstrap):
  - state/chapters/ch{N:03d}.md
  - state/characters.yaml
  - state/timeline.yaml
  - state/iron-laws-extra.md  — setting-specific iron laws
  - state/current_status_card.md  — Lesson-3 authoritative "who knows what" snapshot (optional)
  - state/pending_hooks.md        — Lesson-3 active-hooks pool (optional)
  - rules/landmines.md        — universal landmines
  - rules/iron-laws.md        — universal iron laws

Writes:
  - state/chapters/ch{N:03d}.verdict.json
  - appends issues to state/issues.jsonl
"""
from __future__ import annotations

import json
import re
import time

from ._base import BaseAgent
from ._verdict_schema import LANDMINE_IDS, validate_verdict
from ..auditors.ai_slop_guard import static_scan_ai_rhythm
from ..blackboard import Blackboard


class Evaluator(BaseAgent):
    name = "evaluator"
    temperature = 0.0
    response_format = "json"
    max_tokens = 4000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        chapter_text = bb.read_text(chapter_path)

        characters = bb.read_text("characters.yaml")
        timeline = bb.read_text("timeline.yaml")
        iron_laws_extra = bb.read_text("iron-laws-extra.md")
        # Read Lesson-3 bookkeeping — these are the authoritative "who knows what"
        # snapshots. Critical for landmine_10 (反派信息越界 / 人设前后矛盾)
        # and landmine_13 (世界观矛盾). Absent/empty files are tolerated (chapter 1).
        status_card = bb.read_text("current_status_card.md") if bb.exists("current_status_card.md") else ""
        pending_hooks = bb.read_text("pending_hooks.md") if bb.exists("pending_hooks.md") else ""
        landmines = self._read_rule("landmines.md")
        iron_laws = self._read_rule("iron-laws.md")
        info_priority = self._read_rule("00-information-priority.md")

        try:
            setting = bb.read_yaml("setting.yaml")
        except Exception:
            setting = {}
        genre = setting.get("genre", "通用小说")
        era_label = setting.get("era", "")

        inputs_read = [
            f"state/{chapter_path}",
            "state/characters.yaml",
            "state/timeline.yaml",
            "state/iron-laws-extra.md",
            "rules/landmines.md",
            "rules/iron-laws.md",
            "rules/00-information-priority.md",
        ]
        # Only log the Lesson-3 bookkeeping files when they actually carry content.
        # Listing empty/absent files in inputs_read would falsely suggest to the
        # Inspector (and to future debuggers) that the Evaluator had a "who knows
        # what" snapshot to cross-check against — they'd then mis-attribute any
        # missed landmine_10 hit to a reading failure rather than to a genuinely
        # absent card (e.g. chapter 1 before StatusCardUpdater has ever run).
        if status_card.strip():
            inputs_read.append("state/current_status_card.md")
        if pending_hooks.strip():
            inputs_read.append("state/pending_hooks.md")

        system = (
            f"你是网文质检员，本题材（{genre} · {era_label}）方向。\n"
            "你的默认立场是**拒稿**。\n"
            "你的任务不是评判文笔好坏，而是**机械核对 19 条雷点 + 静态指标**。\n"
            "找不到 ≥3 个硬伤就是失职。\n"
            "\n"
            "# 工作前提（关键）\n"
            "\n"
            "1. 本章由另一个 LLM 生成。该 LLM 与你共享训练偏好——它喜欢破折号、\n"
            "   否定对比、明喻、短段。这些偏好在网文读者眼里是『AI 味』。\n"
            "   你读起来『流畅有节奏』≈ AI 节奏病。\n"
            "2. 静态扫描已经数过 4 项确定性指标（见 user prompt 末尾的『机械扫描结果』）。\n"
            "   超阈值即必命中 landmine_18，severity 由超标程度决定，没有商量。\n"
            "3. 默认 overall_pass = false。在你逐条核对完 19 条 landmine 全部未命中、\n"
            "   且 4 项静态指标全部低于阈值后，才能反转为 true。\n"
            "\n"
            "你只信稿件本身，不听任何『作者本意』的辩解。\n"
            "你不关心作者花了多少功夫，你只关心读者看到的是什么。\n"
            "\n"
            "# 核对规程（按顺序执行，不能跳）\n"
            "\n"
            "## 步骤 1：读静态扫描结果（user prompt 末尾的机械扫描数字）\n"
            "- neg_contrast >= 5  → landmine_18 命中（severity ≥ medium）\n"
            "- emdash >= 20       → landmine_18 命中（severity ≥ medium）\n"
            "- short_para >= 35%  → landmine_18 命中（severity ≥ medium）\n"
            "- simile >= 25       → landmine_18 命中（severity ≥ medium）\n"
            "任何一项 ≥ severe 阈值（10 / 30 / 50% / 40），severity = high。\n"
            "任意两项及以上同时超过 moderate 阈值，severity ≥ medium。\n"
            "evidence 直接写『指标 X = N，超过健康上限 M』并补充原文最典型片段。\n"
            "\n"
            "## 步骤 2：核对其他 18 条 landmine（独立判断）\n"
            "对每条独立打分：hit / evidence（必须原文引文 ≥10 字）/ severity。\n"
            "- 时间线、人设崩塌、世界观矛盾这类硬伤，见一个抓一个。\n"
            "- 不要因为已经命中了 landmine_18 就把别的也带上。\n"
            "- 也不要因为已经命中多条就反过来怀疑自己是否扩散——扩散的判别由\n"
            "  evidence 是否独立来决定，不由命中数决定。\n"
            "\n"
            "## 步骤 3：决定 overall_pass\n"
            "- 任何 high 命中 → false\n"
            "- 2 个及以上 medium 命中 → false\n"
            "- 其他 → true\n"
            "- 但默认偏向 false：如果你不确定某条算不算 medium，按 medium 算。\n"
            "\n"
            "## 步骤 4：top_3_fixes\n"
            "- where 必须是 ≥6 字的原文引文\n"
            "- what 必须 ≥10 字的具体改写方向\n"
            "- 找不到 3 个就少于 3 个，但不能用 `…` / `...` / 空字符串占位\n"
            "\n"
            "# 反偷懒条款\n"
            "\n"
            "- 『全 false + overall_pass=true』是有效输出，但你必须在内部承担举证责任：\n"
            "  你确认了 4 项静态指标都低于阈值，且 18 条其他 landmine 都没有原文证据。\n"
            "- 如果 4 项静态指标超标但你仍然让 landmine_18 hit=false，这是失职。\n"
            "- 不要害怕命中数量。AI 味灾难章节确实可能 4-6 个 landmine 同时命中。\n"
            "  漏报远比扩散危险。\n"
            "\n"
            "# 对人设和时间线的交叉验证\n"
            "\n"
            "- 如果稿件中主角的行为违背 characters.yaml 中的 redlines / traits，必须在\n"
            "  landmine_10（人设前后矛盾）或 landmine_11（人物形象单薄）命中。\n"
            "- 如果稿件中的年份、事件、物价与 timeline.yaml 不符，必须在\n"
            "  landmine_13（世界观模糊/脱离现实）命中。\n"
            "- 如果稿件违反题材特有铁律（iron-laws-extra.md），必须在\n"
            "  landmine_10 或 landmine_13 命中，evidence 中说明违反了哪条 iron_law_extra_N。\n"
            "- 如果 `current_status_card.md` 的「已知真相」表明某信息**反派不应知道**，\n"
            "  而章节中反派表现出知情（或反向：只有反派知道的信息，主角在无合理推理链下\n"
            "  突然知晓），必须在 landmine_10 命中，evidence 引**章节原文具体句子** +\n"
            "  引**状态卡对应条目**（例如 `状态卡·已知真相·『X 情报』反派知否=否`）。\n"
            "- 如果 `pending_hooks.md` 的「活跃伏笔」与本章情节矛盾——例如本章回收了某\n"
            "  hook_id，但回收方式与该伏笔的类型/当前状态定义不符；或本章推进了某伏笔\n"
            "  的方向与伏笔表中记录的既定走向相反——必须在 landmine_10 或 landmine_13\n"
            "  命中，evidence 需同时引原文和对应 hook_id 行。\n"
            "- 以上两条当状态卡 / 伏笔池**未提供**（首章或尚未产出）时不适用，不要为此扣分。\n"
            "\n"
            "# 叙事技术层专项自查（校准集数据表明 Evaluator 易漏此类）\n"
            "\n"
            "在给出 landmines 结论之前，必须就以下 4 条做一次**专项扫描**，"
            "哪怕其他层没问题，这些也可能独立命中：\n"
            "\n"
            "- **landmine_4 视角杂乱** — 同一场景中叙事视角是否至少跳换过一次？"
            "  典型模式：A 段写 主角 X 的内心活动 → B 段突然切到配角 Y 的心理 → "
            "  C 段又跳回 X。即使是短短一段配角视角插入，只要**中间无明确切换标记**"
            "  （空行、时间/地点提示、或显式的『与此同时，另一边』），就要命中。\n"
            "- **landmine_9 节奏失控与过渡生硬** — 同一章中场景之间是否有过渡？"
            "  典型模式：『林家耀喝完冻鸳鸯走出茶餐厅』下一段直接『当天夜里，大雨』"
            "  中间无一句过渡（如『接下来几个小时他在码头转了转』或『到了晚上』）"
            "  就是硬切，命中。\n"
            "- **landmine_8 冲突乏力** — 主角与对手的对抗是否"
            "  『敌人一出现就退场/认输/消失』？"
            "  对抗建立是否不到 100 字就结束？是否敌人不战而退？是则命中。\n"
            "- **landmine_15 爽点不足** — 高潮是否在 3 行之内解决？"
            "  是否赢得太轻松、敌人莫名其妙服软？胜利是否没有对应的代价或伤害？"
            "  是则命中。\n"
            "\n"
            "以上 4 条，如果文本有对应征兆但你在 landmines 打分时**忘了命中**，"
            "就是失职。确认完再给最终结论。\n"
            "\n"
            "# 绝对格式要求\n"
            "\n"
            "- 严格输出 JSON，不写任何散文、解释或 Markdown。\n"
            "- JSON 必须包含所有 19 个 landmine_N 键，一个都不能少。\n"
            "- evidence 若未命中则为 null。\n"
            "- top_3_fixes 的 where 字段绝不能是 `…` / `...`。\n"
            "\n"
            "# 参考：19 个雷点（完整列表）\n\n"
            + landmines
            + "\n\n# 参考：通用 24 条铁律\n\n"
            + iron_laws
            + "\n\n# 参考：题材特有铁律（由 setting 注入）\n\n"
            + iron_laws_extra
            + "\n\n# 参考：信息源优先级（冲突仲裁协议）\n\n"
            + info_priority
        )

        # NOTE: we intentionally do NOT embed a skeleton with "…" placeholders
        # in the user prompt schema — that was the root cause of the "Evaluator
        # returned skeleton" bug. Instead we describe the required keys.
        # Build an optional "authoritative current-state" block. We only include
        # these sections when the files carry content — an empty block would
        # dilute the prompt and risk the LLM fabricating violations against a
        # non-existent snapshot.
        bookkeeping_block = ""
        if status_card.strip():
            bookkeeping_block += (
                "\n# 当前时间点权威状态卡 (current_status_card.md)\n"
                "> 以下是章节结束时的『谁知道什么 / 当前敌我 / 活跃伏笔』权威快照。\n"
                "> 用于交叉验证『反派信息越界』『伏笔回收不符』等问题。\n\n"
                f"```markdown\n{status_card}\n```\n"
            )
        if pending_hooks.strip():
            bookkeeping_block += (
                "\n# 活跃伏笔池 (pending_hooks.md)\n"
                "> 以下是进入本章前尚未回收的伏笔池。本章对任一 hook_id 的推进/回收\n"
                "> 必须与其既定类型和当前状态自洽。\n\n"
                f"```markdown\n{pending_hooks}\n```\n"
            )

        # Run the static AI-rhythm scanner so the LLM sees the deterministic
        # numbers Python already counted. Reused later in _handle_output for
        # the override post-process; running once here keeps _build_prompts
        # honest about what the LLM was shown.
        scan = static_scan_ai_rhythm(chapter_text)
        m = scan["metrics"]
        scan_block = (
            "\n\n# 机械扫描结果（这是 Python 数出来的真实数字）\n\n"
            f"- 否定对比 '不是X，是Y'：**{m['neg_contrast']}** 次"
            "（健康 ≤2 / moderate ≥5 / severe ≥10）\n"
            f"- 破折号 '——'：**{m['emdash']}** 次"
            "（健康 ≤8 / moderate ≥20 / severe ≥30）\n"
            f"- 短段 <30 字占比：**{m['short_para_ratio']*100:.1f}%**"
            "（健康 ≤20% / moderate ≥35% / severe ≥50%）\n"
            f"- 明喻 '像X'：**{m['simile']}** 次"
            "（健康 ≤15 / moderate ≥25 / severe ≥40）\n"
            "\n（静态扫描的 severe 命中会被流水线后处理强制写入 verdict，"
            "但你的 LLM 判断仍要据此决定 landmine_18 在 evidence 里写什么细节。）\n"
        )

        user = (
            f"# 本章节（第 {chapter} 章）全文\n\n"
            f"{chapter_text}\n\n"
            f"# 人物档案 (characters.yaml)\n\n```yaml\n{characters}\n```\n\n"
            f"# 时间线 (timeline.yaml)\n\n```yaml\n{timeline}\n```\n"
            f"{bookkeeping_block}"
            f"\n# 输出 JSON 结构（严格遵守）\n\n"
            "必须包含以下字段：\n"
            "- `overall_pass` (boolean)\n"
            "- `landmines`：对象，包含 `landmine_1` 到 `landmine_19` 全部 19 键，\n"
            "  每个值是 `{hit: bool, evidence: string|null, severity: 'high'|'medium'|'low'|null}`\n"
            "- `top_3_fixes`：数组，0-3 个元素；每个元素是\n"
            "  `{where: <原文引文，至少 6 个字>, what: <改写方向，至少 10 个字>}`\n"
            "\n"
            "✋ 不要复用示例占位符 — 每一处 evidence / where 都必须是你从上方章节原文中找到的真实引文。\n"
            + scan_block
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        # Parse JSON defensively (strip markdown fences if any)
        try:
            parsed = _parse_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            # Malformed JSON at parse level — synthesize failing verdict
            parsed = {"_parse_error": f"JSON parse failed: {e}"}

        # Validate + normalize + detect skeleton (pure function, unit-tested)
        result = validate_verdict(parsed)
        verdict = result["clean_verdict"]
        warnings = result["validation_warnings"]
        skeleton = result["skeleton_detected"]

        # Surface warnings for observability. Stored in the verdict file so the
        # Inspector can show them alongside the rubric.
        if warnings:
            verdict["_validation_warnings"] = warnings

        # Patch 1：静态扫描命中直接覆盖 LLM 主观判断
        # 原理：LLM 数不清楚 42 个破折号但 Python 能。机械事实归 Python，
        # 价值判断归 LLM。任何静态扫描的 severe 命中都强制 landmine_18=high
        # + overall_pass=false。这是 Oracle 诊断的「静态扫描成果不流通」修复。
        chapter_text = bb.read_text(f"chapters/ch{chapter:03d}.md")
        scan = static_scan_ai_rhythm(chapter_text)
        # Guard against trivially-short fixture chapters (test seeds, sanity stubs).
        # Real chapters are 2000+ chars / dozens of paragraphs. With <5 paragraphs
        # the short_para_ratio metric is meaningless (1 paragraph = 100% short).
        # Skip the override entirely for such inputs so unit-test fixtures
        # ("# t\n\n正文") aren't force-failed.
        meaningful_scan = scan["metrics"]["total_paras"] >= 5
        severe_hits = (
            [h for h in scan["hits"] if h["severity"] == "severe"]
            if meaningful_scan
            else []
        )
        moderate_hits = (
            [h for h in scan["hits"] if h["severity"] == "moderate"]
            if meaningful_scan
            else []
        )

        if severe_hits or len(moderate_hits) >= 2:
            # severe 命中 → high（强制 overall_pass=false）
            # 仅 moderate 累积（≥2）→ medium（不强制翻车，与已有 LLM medium 合并计数）
            severity = "high" if severe_hits else "medium"
            evidence_parts = []
            for h in severe_hits + moderate_hits:
                evidence_parts.append(
                    f"{h['criterion']}={h['count']} (健康上限 {h['threshold']})"
                )
            verdict["landmines"]["landmine_18"] = {
                "hit": True,
                "evidence": "静态扫描机械命中：" + " / ".join(evidence_parts),
                "severity": severity,
                "_source": "static_scan",
            }
            # high 命中按规则就是 fail
            if severity == "high":
                verdict["overall_pass"] = False
            elif severity == "medium":
                # medium：与现有 LLM 命中合并；如果已经有 ≥1 个 medium，达到 2+ 翻 false
                med_count = sum(
                    1
                    for mid, m in verdict["landmines"].items()
                    if m.get("hit") and m.get("severity") == "medium"
                )
                if med_count >= 2:
                    verdict["overall_pass"] = False
            # 把静态命中追加到 top_3_fixes（如果还有空位）
            if "top_3_fixes" not in verdict or verdict["top_3_fixes"] is None:
                verdict["top_3_fixes"] = []
            slots_left = 3 - len(verdict["top_3_fixes"])
            for h in (severe_hits + moderate_hits)[:max(0, slots_left)]:
                where = (h.get("snippet") or h["criterion"])[:60]
                if len(where) < 6:
                    where = f"{h['criterion']} 命中（count={h['count']}）"
                verdict["top_3_fixes"].append(
                    {
                        "where": where,
                        "what": h.get("suggested_direction", "节奏修复（删冗余/合并短段/降密度）"),
                        "_source": "static_scan",
                    }
                )

        bb.write_json(f"chapters/ch{chapter:03d}.verdict.json", verdict)

        # Log individual issues (skip synthetic skeleton hits — those aren't
        # about the chapter, they're about the evaluator output itself)
        if not skeleton:
            ts = time.time()
            for mine_id, entry in verdict["landmines"].items():
                if entry.get("hit"):
                    bb.append_jsonl(
                        "issues.jsonl",
                        {
                            "ts": ts,
                            "chapter": chapter,
                            "landmine_id": mine_id,
                            "severity": entry.get("severity"),
                            "evidence": entry.get("evidence"),
                        },
                    )


def _parse_json(raw: str):
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    return json.loads(s)
