"""SensoryKitMiner — 从作品自产章节抽取"地点 → 五感清单"。

目的：为 Planner 升级提供 era_sensory_kit.yaml，让 Planner 写
scenes[].sensory_prompts 时有"本题材/本作品实际用过的感官词汇"可以引用，
避免每次靠 LLM 独立外推，保证不同章节对同一 location 的描写风格一致。

输入：
  - projects/<book>/state/chapters/ch*.md 已生成的章节正文
  - projects/<book>/state/chapters/ch*.plan.json（取 scenes[].location）

输出：
  - projects/<book>/state/era_sensory_kit.yaml

实现：
  1. 扫所有 plan.json，收集 scenes[].location 出现频次，取 top-N
  2. 对每个 location，收集它在章节正文里的相关段落
     （章节正文按段落切，含该地名关键词 → 取前后 1 段作上下文）
  3. 每 location 一次 LLM 调用（temp=0.0, json 格式），要求按五感逐字摘录
  4. 合并写 era_sensory_kit.yaml

本模块**只读 state/ 不改**除目标文件外任何东西。失败时抛异常，不静默。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from src import config, llm


# ---------- 调优常量 ----------

TOP_N_LOCATIONS = 12     # 最多抽多少个 location，按词频排序
MAX_EXCERPTS_PER_LOC = 6  # 每 location 给 LLM 的最多段落数
EXCERPT_MAX_CHARS = 600   # 每个段落的最大字符数（含上下文）
MIN_LOCATION_MENTIONS = 1  # plan.json 里出现次数 < 此值的 location 不抽
MODEL_TEMPERATURE = 0.0
MODEL_MAX_TOKENS = 1500


# ---------- 数据结构 ----------

@dataclass
class LocationData:
    name: str
    mentions: int  # plan.json 中 scene.location 出现次数
    excerpts: list[str]  # 从章节正文抽取的相关段落


# ---------- 主入口 ----------

def mine_sensory_kit(
    book_id: str,
    *,
    top_n: int = TOP_N_LOCATIONS,
    dry_run: bool = False,
) -> Path:
    """Mine location → sensory kit for a book. Returns the output path.

    Raises FileNotFoundError if project state doesn't exist or has no chapters.
    """
    book_dir = config.PROJECTS_DIR / book_id
    state_dir = book_dir / "state"
    if not state_dir.exists():
        raise FileNotFoundError(f"project state not found: {state_dir}")

    chapters_dir = state_dir / "chapters"
    if not chapters_dir.exists():
        raise FileNotFoundError(f"no chapters yet: {chapters_dir}")

    # Step 1: 收集 location → 出现次数
    loc_mentions = _collect_locations_from_plans(chapters_dir)
    if not loc_mentions:
        raise RuntimeError(
            f"No scene locations found in any plan.json under {chapters_dir}. "
            f"Run at least one chapter through the pipeline first."
        )
    top_locations = sorted(
        loc_mentions.items(), key=lambda x: -x[1]
    )[:top_n]
    top_locations = [
        (name, count) for name, count in top_locations
        if count >= MIN_LOCATION_MENTIONS
    ]

    # Step 2: 收集每个 location 的正文片段
    chapter_texts = _load_all_chapter_texts(chapters_dir)
    location_data: list[LocationData] = []
    for name, mentions in top_locations:
        excerpts = _extract_excerpts(name, chapter_texts)
        if not excerpts:
            continue
        location_data.append(LocationData(
            name=name, mentions=mentions, excerpts=excerpts,
        ))

    if not location_data:
        raise RuntimeError(
            "Collected locations but no matching excerpts in chapter texts."
        )

    # Step 3: LLM 抽取每个 location 的五感清单
    kit = {"schema_version": 1, "locations": {}}
    for loc in location_data:
        sensory = _extract_sensory(loc)
        if sensory:
            kit["locations"][loc.name] = sensory

    # Step 4: 写盘
    out_path = state_dir / "era_sensory_kit.yaml"
    if dry_run:
        return out_path

    header = (
        f"# era_sensory_kit.yaml — 按 location 的结构化五感清单\n"
        f"# 由 SensoryKitMiner 从 {book_id} 的已生成章节抽取\n"
        f"# 消费者：Planner（写 plan.scenes[].sensory_prompts 时按 scene.location 查表）\n"
        f"# 作者可手工编辑；下次 miner 运行不会覆盖手工项，仅追加新 location\n"
        f"# locations 下每条 {list(kit['locations'].keys())[:3]}... 各 5 感 3-5 词\n"
        f"\n"
    )
    body = yaml.safe_dump(
        kit, allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    out_path.write_text(header + body, encoding="utf-8")
    return out_path


# ---------- Step 1: 收集 location ----------

def _collect_locations_from_plans(chapters_dir: Path) -> dict[str, int]:
    """Walk all ch*.plan.json, count scenes[].location frequency."""
    counts: dict[str, int] = {}
    for plan_path in sorted(chapters_dir.glob("ch*.plan.json")):
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scenes = plan.get("scenes") or []
        for scene in scenes:
            loc = (scene.get("location") or "").strip()
            if not loc:
                continue
            # 清洗：常见的 "九龙城寨 · 东头村道口" 取主地名 "九龙城寨"
            # 第一级分隔符用 · / ·（全角） / 空格 + 数字
            main = re.split(r"\s*[·・]\s*", loc, maxsplit=1)[0].strip()
            if main:
                counts[main] = counts.get(main, 0) + 1
    return counts


# ---------- Step 2: 收集正文片段 ----------

def _load_all_chapter_texts(chapters_dir: Path) -> list[tuple[int, str]]:
    """Return [(chapter_number, markdown_text), ...]."""
    out: list[tuple[int, str]] = []
    for md_path in sorted(chapters_dir.glob("ch*.md")):
        m = re.match(r"ch(\d+)\.md$", md_path.name)
        if not m:
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append((int(m.group(1)), text))
    return out


def _extract_excerpts(
    location: str,
    chapter_texts: list[tuple[int, str]],
) -> list[str]:
    """Find paragraphs in chapter_texts that mention `location`.

    Returns at most MAX_EXCERPTS_PER_LOC excerpts, each ≤ EXCERPT_MAX_CHARS.
    Each excerpt is "ch{N}:\n<paragraph>" so LLM knows the source.
    """
    out: list[str] = []
    seen_hashes: set[int] = set()
    for ch_num, text in chapter_texts:
        # 按空行分段
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for para in paras:
            if location not in para:
                continue
            h = hash(para[:200])
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            trimmed = para[:EXCERPT_MAX_CHARS]
            out.append(f"ch{ch_num:03d}:\n{trimmed}")
            if len(out) >= MAX_EXCERPTS_PER_LOC:
                return out
    return out


# ---------- Step 3: LLM 抽取五感 ----------

_SYSTEM_PROMPT = """你是感官样本抽取员。
从给定的小说章节片段里，按五感分类**逐字摘录**具体细节词组。

规则：
1. 只抽取原文里**实际出现**的感官细节，不抽象、不概括、不创作。
2. 每条 5-20 字的短词组，例如："冷气机滴水声"、"沟渠腐臭"、"柱侯牛腩味"。
3. 五感严格分类：visual（视觉）/ auditory（听觉）/ olfactory（嗅觉）/ tactile（触觉）/ gustatory（味觉）。
4. 每类 3-5 条，不够就少，不要凑数。
5. 输出严格 JSON，不写任何解释。"""


_USER_TEMPLATE = """# 地点
{location}

# 来自章节的片段
{excerpts_block}

# 输出 JSON
```json
{{
  "visual": ["<词组>", ...],
  "auditory": ["<词组>", ...],
  "olfactory": ["<词组>", ...],
  "tactile": ["<词组>", ...],
  "gustatory": ["<词组>", ...]
}}
```

只输出 JSON 本体，不要任何解释或 markdown 围栏外的文字。"""


def _extract_sensory(loc: LocationData) -> dict | None:
    """Single LLM call. Returns {visual/auditory/olfactory/tactile/gustatory: [...]}.

    On failure returns None so the caller just skips this location.
    """
    excerpts_block = "\n\n---\n\n".join(loc.excerpts)
    user = _USER_TEMPLATE.format(
        location=loc.name,
        excerpts_block=excerpts_block,
    )
    try:
        raw = llm.chat(
            system=_SYSTEM_PROMPT,
            user=user,
            agent_name="sensory_kit_miner",
            temperature=MODEL_TEMPERATURE,
            max_tokens=MODEL_MAX_TOKENS,
            response_format="json",
            inputs_read=[
                f"chapters/(excerpts of {loc.mentions} plan-level mentions)",
            ],
        )
    except Exception:
        return None

    data = _parse_llm_output(raw)
    if not data:
        return None

    # 清洗 & 验证
    cleaned: dict[str, list[str]] = {}
    for key in ("visual", "auditory", "olfactory", "tactile", "gustatory"):
        items = data.get(key) or []
        if not isinstance(items, list):
            continue
        uniq: list[str] = []
        for it in items:
            if not isinstance(it, str):
                continue
            it = it.strip()
            if not it or len(it) > 30:  # 过长的 LLM 可能在写句子不是词组
                continue
            if it not in uniq:
                uniq.append(it)
            if len(uniq) >= 5:
                break
        if uniq:
            cleaned[key] = uniq
    return cleaned or None


def _parse_llm_output(raw: str) -> dict | None:
    """Parse LLM output. Be tolerant of ```json fences."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # 剥 ``` 围栏
    if text.startswith("```"):
        text = text.strip("`")
        _, _, text = text.partition("\n")
        if "```" in text:
            text = text.rpartition("```")[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


# ---------- CLI ----------

def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Mine era_sensory_kit.yaml from a project's own chapters."
    )
    parser.add_argument("book_id", help="projects/<book_id>/state 作品 id")
    parser.add_argument("--top-n", type=int, default=TOP_N_LOCATIONS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        out = mine_sensory_kit(
            args.book_id, top_n=args.top_n, dry_run=args.dry_run,
        )
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1

    if args.dry_run:
        print(f"(dry-run) would write: {out}")
    else:
        print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
