"""GenreValidator - three-stage adversarial review.

Stage 1 (structure, no LLM):  delegated to src/tools/setting_lint.py
Stage 2 (semantic, this class):
   Part A - Tier-1 deny-phrase regex scan (no LLM, deterministic)
   Part B - adversarial LLM review, reject-by-default
Stage 3 (trial, optional):    delegated to src/genre_pipeline/trial.py

Design notes (from librarian ★★★ #2 + structured-output techniques):
- Reject-by-default: default verdict is REJECT; only ALL checks pass → accept
- Quote-then-claim: Validator must cite file + line substring before asserting
- Tier-1 as a free, zero-false-positive first pass
- XML-tagged inputs + explicit schema + anti-schema for reliable JSON output
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.blackboard import Blackboard


# -----------------------------------------------------------------------------
# Deny phrase loader — cached at module level
# -----------------------------------------------------------------------------
@lru_cache(maxsize=2)
def _load_deny_phrases(path_str: str) -> tuple[str, ...]:
    p = Path(path_str)
    if not p.exists():
        return ()
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return tuple(out)


def _all_deny_phrases() -> list[tuple[str, str]]:
    """Return list of (phrase, lang) tuples for scanning."""
    from src import config

    rules_dir = config.RULES_DIR
    zh = _load_deny_phrases(str(rules_dir / "deny-phrases-zh.txt"))
    en = _load_deny_phrases(str(rules_dir / "deny-phrases-en.txt"))
    return [(p, "zh") for p in zh] + [(p, "en") for p in en]


# -----------------------------------------------------------------------------
# System prompt — adversarial reviewer
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """输出语言：简体中文（JSON 键英文，值中文）。

你是一位题材包对抗性审稿员（adversarial reviewer）。你的职业信条：
  **默认拒稿（Reject by default）**。只有当所有关卡都明确通过，才放行。
  发现问题不要手软；找不到问题时，也要老实交代。

审稿流程（按顺序执行，必须都做）：

1. **Quote-then-claim**：每条 issue 必须先引用触发它的原文（quote），
   再给出判断（claim）+ 修复建议（suggestion）。无原文引用的 issue 无效。

2. **内部一致性**：iron-laws-extra.md 内部条目之间有矛盾吗？
3. **跨文件一致性**：
   - iron-laws 和 era.md 事实冲突？
   - iron-laws 和 writing-style-extra.md 语气冲突？
   - resource_schema.yaml（若存在）的 baseline_scale 能从 era.md 推得吗？
4. **AI 味 / 模糊词 / 废话**：era.md / writing-style-extra.md 里有套话、
   weasel verbs、dying metaphors、AI 式过渡。
5. **占位内容未填充**：是否还有 "（占位" / "TODO" / "TBD" 之类残留？

严格输出 JSON（只输出 JSON 本体，不要围栏，不要解释）：
{
  "verdict": "accept" | "reject",
  "issues": [
    {
      "severity": "error" | "warning" | "info",
      "file": "era.md | writing-style-extra.md | iron-laws-extra.md | genre.yaml | resource_schema.yaml",
      "quote": "<触发这条 issue 的原文片段，原样>",
      "message": "<问题描述，一句话>",
      "suggestion": "<具体可执行的修复建议，不超过两句>"
    }
  ]
}

VALID 示例（逐字学习这个格式）：
{"verdict":"reject","issues":[{"severity":"error","file":"iron-laws-extra.md","quote":"主角绝不主动杀人","message":"与 era.md 第 3 段「一九八三年油麻地帮派每月械斗 3 次」形成逻辑冲突","suggestion":"改写为「主角避免以个人名义主动杀人，但帮派任务中可参与」"}]}

INVALID 示例（不要这样写）：
{"issues":[{"severity":"error","message":"不够好"}]}     ← 无 quote，无 file，无 suggestion，verdict 缺失。

硬约束：
- verdict 字段必填，只能是 "accept" / "reject"。
- 每条 issue 的 quote 必须是 4 个输入文件里真实出现过的字符串（不要自造）。
- severity=error 表示必须修才能发布；warning 是强烈建议；info 是提示。
- 若确实找不到任何问题：verdict="accept"，issues=[]（不要凑数）。
- 不使用模糊词：似乎 / 大致 / 某种程度上 / 总而言之。
"""


class GenreValidator(BaseAgent):
    name = "genre_validator"
    temperature = 0.0
    response_format = "json"
    max_tokens = 3000

    SYSTEM_PROMPT = SYSTEM_PROMPT  # kept as class attr for external imports

    # -------------------------------------------------------------------------
    # Tier-1: deterministic deny-phrase regex scan (no LLM)
    # -------------------------------------------------------------------------
    def _tier1_deny_scan(self, genre_id: str) -> list[dict]:
        """Regex-scan the genre pack files for any deny-phrase hit.

        Returns a list of issue dicts (severity='warning' — Tier-1 never
        raises an error, it only flags style risk).
        """
        from src import config

        genre_dir = config.GENRES_DIR / genre_id
        files_to_scan = (
            "era.md",
            "writing-style-extra.md",
            "iron-laws-extra.md",
        )
        phrases = _all_deny_phrases()
        if not phrases:
            return []

        issues: list[dict] = []
        for fname in files_to_scan:
            fp = genre_dir / fname
            if not fp.exists():
                continue
            text = fp.read_text(encoding="utf-8")
            text_lower = text.lower()
            for phrase, lang in phrases:
                needle = phrase if lang == "zh" else phrase.lower()
                haystack = text if lang == "zh" else text_lower
                idx = haystack.find(needle)
                if idx == -1:
                    continue
                # Slice ±20 chars of context for a quote
                start = max(0, idx - 20)
                end = min(len(text), idx + len(phrase) + 20)
                context = text[start:end].replace("\n", " ").strip()
                issues.append(
                    {
                        "severity": "warning",
                        "file": fname,
                        "quote": context,
                        "message": (
                            f"命中 deny-phrase「{phrase}」"
                            f"（{'中文' if lang == 'zh' else 'English'} deny 列表）：" 
                            f"{'AI 味/废话套语' if lang == 'zh' else 'AI-slop phrase'}，建议重写"
                        ),
                        "suggestion": f"删除或替换「{phrase}」，改用具体描写代替套话",
                        "source": "tier1-deny-scan",
                    }
                )
        return issues

    # -------------------------------------------------------------------------
    # Stage 2 Part B: LLM semantic review
    # -------------------------------------------------------------------------
    def _build_prompts(self, bb: Blackboard, *, genre_id: str, **_):
        from src import config

        genre_dir = config.GENRES_DIR / genre_id
        files_to_read = (
            "genre.yaml",
            "era.md",
            "writing-style-extra.md",
            "iron-laws-extra.md",
            "resource_schema.yaml",
        )
        blocks = []
        inputs_read: list[str] = []
        for fname in files_to_read:
            fp = genre_dir / fname
            if fp.exists():
                text = fp.read_text(encoding="utf-8")
                blocks.append(
                    f"<file name=\"{fname}\">\n{text[:4000]}\n</file>"
                )
                inputs_read.append(f"genres/{genre_id}/{fname}")

        user = (
            f"<genre_pack id=\"{genre_id}\">\n"
            + "\n\n".join(blocks)
            + "\n</genre_pack>\n\n"
            + "<your_task>\n"
            + "按系统指令的 5 步流程审查上方 <genre_pack>，默认拒稿。\n"
            + "每条 issue 必须 quote-then-claim。只输出 JSON 本体。\n"
            + "</your_task>"
        )
        return SYSTEM_PROMPT, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, genre_id: str, **_):
        obj = _parse_json(raw)
        for issue in obj.get("issues", []):
            issue["genre_id"] = genre_id
            # Strip verdict-level metadata from per-issue record; keep source tag
            issue.setdefault("source", "stage2-llm")
            bb.append_jsonl("genre_issues.jsonl", issue)

    # -------------------------------------------------------------------------
    # run() override — runs Tier-1 FIRST (fast, free), then Stage 2 LLM
    # -------------------------------------------------------------------------
    def run(self, bb: Blackboard, **kwargs) -> str:
        genre_id: str = kwargs["genre_id"]

        # Tier-1: deterministic deny-phrase scan
        tier1_issues = self._tier1_deny_scan(genre_id)
        for issue in tier1_issues:
            issue["genre_id"] = genre_id
            bb.append_jsonl("genre_issues.jsonl", issue)

        # Stage 2: LLM adversarial review (uses BaseAgent.run plumbing)
        return super().run(bb, **kwargs)


def _parse_json(raw: str):
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, flags=re.S)
    if m:
        s = m.group(1)
    return json.loads(s)
