"""PlotArcDrafter — turn a one-line ultimate goal into a 4-act plot_arc.yaml skeleton.

Used by the new-project wizard (Step 2) when the user supplies an
``ultimate_goal``. Produces a structured plot_arc.yaml dict matching
src.tools.plot_arc.PlotArc schema (schema_version=1) with 4 acts whose
chapter ranges contiguously cover 1..total_chapters.

Single LLM call. ``milestones`` and ``anchor_quota`` are intentionally
left empty — the author is expected to refine them with the in-place
template editor after creation. Failure modes (bad YAML / model misbehavior)
fall back to a pure-equipartition shell so bootstrap can still continue
(warnings_collector picks up the failure reason).
"""
from __future__ import annotations

import logging
from typing import Optional

import yaml

from src import llm

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是网文卷次架构师。读用户的一句话主角终极目标 + 总章数 + 题材世界观，
输出 4 卷骨架（卷一:setup / 卷二:complications / 卷三:climax_setup / 终卷:resolution）。

每卷必须包含：
- name: 用一个 4-6 字凝练的名字（如"暗格觉醒/锅炉房真相/灰塔/解契约"）
- range: [start_ch, end_ch]
- goal: 1-2 句话主线目标
- must_close_by_end: 2-3 条必须收束的伏笔/线索

milestones 不要填（留作者后续打磨）。
anchor_quota 也不要填。

输出严格 YAML（不写散文不写 markdown 代码块），顶层 schema：

schema_version: 1
total_chapters: <int>
ultimate_goal: "<一句话>"
acts:
  - name: "<卷名>"
    range: [<start>, <end>]
    goal: "<本卷主线目标>"
    must_close_by_end:
      - "<必须收束 1>"
      - "<必须收束 2>"
  - ...

约束：
1. acts 必须刚好 4 卷。
2. range 必须连续覆盖 1..total_chapters，无空隙、无重叠。
3. 章数等分（多余余数从前往后多分 1）。
"""


def _equipartition(total: int, n_acts: int = 4) -> list[tuple[int, int]]:
    """Split 1..total into n_acts contiguous ranges (extra remainders go first)."""
    n_acts = max(1, n_acts) if total < n_acts else n_acts
    base = total // n_acts
    extra = total % n_acts
    out: list[tuple[int, int]] = []
    cursor = 1
    for i in range(n_acts):
        size = base + (1 if i < extra else 0)
        out.append((cursor, cursor + size - 1))
        cursor += size
    return out


def _shell(total: int, ultimate_goal: str) -> dict:
    """Fallback skeleton when LLM misbehaves — pure equipartition with empty fields."""
    splits = _equipartition(total, 4 if total >= 4 else max(1, total))
    default_names = ["卷一", "卷二", "卷三", "终卷"]
    acts = []
    for i, (s, e) in enumerate(splits):
        acts.append({
            "name": default_names[i] if i < len(default_names) else f"卷{i+1}",
            "range": [s, e],
            "goal": "",
            "must_close_by_end": [],
        })
    return {
        "schema_version": 1,
        "total_chapters": total,
        "ultimate_goal": ultimate_goal.strip(),
        "acts": acts,
    }


def _normalize(data: dict, total: int, ultimate_goal: str) -> dict:
    """Coerce LLM output to a valid plot_arc dict.

    - Force schema_version=1 / total_chapters=total / ultimate_goal=user input.
    - Keep at most 4 acts; pad with shell acts if fewer than 4.
    - Re-stitch ranges so they contiguously cover 1..total (acts may have come
      back with off-by-one boundaries; we trust the LLM's relative sizing but
      enforce a contiguous tiling).
    """
    raw_acts = data.get("acts") or []
    if not isinstance(raw_acts, list):
        raw_acts = []
    raw_acts = raw_acts[:4]

    # Determine relative sizes from LLM ranges (fall back to equipartition)
    sizes: list[int] = []
    for a in raw_acts:
        if not isinstance(a, dict):
            sizes.append(0)
            continue
        rng = a.get("range")
        if (
            isinstance(rng, list)
            and len(rng) == 2
            and all(isinstance(x, int) for x in rng)
            and rng[1] >= rng[0]
        ):
            sizes.append(rng[1] - rng[0] + 1)
        else:
            sizes.append(0)

    n_acts = 4 if total >= 4 else max(1, total)
    if len(sizes) < n_acts or sum(sizes) <= 0:
        # not enough info — equipartition
        new_ranges = _equipartition(total, n_acts)
    else:
        # rescale sizes to total, preserve relative weights
        s_sum = sum(sizes)
        scaled = [max(1, round(s * total / s_sum)) for s in sizes[:n_acts]]
        # fix rounding drift
        diff = total - sum(scaled)
        i = 0
        while diff != 0 and scaled:
            idx = i % len(scaled)
            if diff > 0:
                scaled[idx] += 1
                diff -= 1
            elif scaled[idx] > 1:
                scaled[idx] -= 1
                diff += 1
            i += 1
        new_ranges = []
        cursor = 1
        for sz in scaled:
            new_ranges.append((cursor, cursor + sz - 1))
            cursor += sz

    default_names = ["卷一", "卷二", "卷三", "终卷"]
    out_acts: list[dict] = []
    for i, (s, e) in enumerate(new_ranges):
        src = raw_acts[i] if i < len(raw_acts) and isinstance(raw_acts[i], dict) else {}
        raw_name = src.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip()
        else:
            name = default_names[i] if i < len(default_names) else f"卷{i+1}"
        goal = src.get("goal") if isinstance(src.get("goal"), str) else ""
        must_close = src.get("must_close_by_end") or []
        if not isinstance(must_close, list):
            must_close = []
        must_close = [str(x) for x in must_close if str(x).strip()]
        out_acts.append({
            "name": name,
            "range": [s, e],
            "goal": goal,
            "must_close_by_end": must_close,
        })

    return {
        "schema_version": 1,
        "total_chapters": total,
        "ultimate_goal": ultimate_goal.strip(),
        "acts": out_acts,
    }


def run(
    *,
    ultimate_goal: str,
    chapter_count_target: int,
    era_md_excerpt: str = "",
) -> dict:
    """Draft a 4-act plot_arc.yaml dict from a one-line ultimate goal.

    Args:
        ultimate_goal: A one-sentence statement of the protagonist's endgame.
        chapter_count_target: Total chapter count (must be >= 1).
        era_md_excerpt: Optional first ~500 chars of era.md to ground the
            LLM in genre-specific naming.

    Returns:
        dict matching src.tools.plot_arc PlotArc schema.
    """
    total = max(1, int(chapter_count_target))
    goal = (ultimate_goal or "").strip()
    if not goal:
        return _shell(total, "")

    user_parts = [
        f"主角终极目标：{goal}",
        f"总章数：{total}",
    ]
    if era_md_excerpt and era_md_excerpt.strip():
        user_parts.append("题材世界观（era.md 摘录）：\n" + era_md_excerpt.strip())
    user_parts.append("请输出严格 YAML 4 卷骨架（schema_version=1）。")
    user = "\n\n".join(user_parts)

    try:
        raw = llm.chat(
            system=SYSTEM_PROMPT,
            user=user,
            agent_name="plot_arc_drafter",
            temperature=0.3,
            response_format="text",
        ) or ""
        if raw.startswith("```"):
            raw = raw.strip("`").partition("\n")[2].rpartition("```")[0]
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, KeyError) as exc:
        log.warning("PlotArcDrafter bad YAML, returning shell: %s", exc)
        return _shell(total, goal)

    if not isinstance(data, dict):
        return _shell(total, goal)

    return _normalize(data, total, goal)
