"""PackagingAgent — produces book-packaging artifacts for publication.

Design:
  Not in the per-chapter pipeline. Run on-demand when user wants to publish:
    python -m src.pipeline --packaging

Reads:
  - state/setting.yaml (genre, tone, protagonist, era)
  - state/outline.json (title, synopsis for high-level arc)
  - state/characters.yaml (character names for blurb content)
  - state/era.md (first 800 chars for era flavour)
  - state/chapters/ch001.md (first 1500 chars) + last chapter produced
  - state/packaging_prefs.yaml (optional user overrides)

Writes:
  - state/packaging.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ._base import BaseAgent
from ..blackboard import Blackboard

# ── schema constants ──────────────────────────────────────────
MAX_BLURB_CHARS = 300
MAX_SUBTITLE_CHARS = 25
MAX_TAGLINE_CHARS = 15
TITLE_CANDIDATE_COUNT = 5
CATEGORY_TAG_MIN = 3
CATEGORY_TAG_MAX = 5


# ── validation helpers ────────────────────────────────────────

def validate_packaging(obj: dict) -> tuple[dict, list[str]]:
    """Validate and normalise a packaging JSON object.

    Returns (clean_obj, warnings).  Raises ValueError on unrecoverable
    structural issues (missing top-level keys, wrong types, out-of-range
    lengths).
    """
    warnings: list[str] = []
    clean: dict = {}

    # --- required top-level keys ---
    required_keys = (
        "title_candidates",
        "recommended_title",
        "subtitle",
        "blurb",
        "tagline",
        "cover_prompt_en",
        "category_tags",
    )
    for key in required_keys:
        if key not in obj:
            raise ValueError(f"缺少必填字段: {key}")

    # --- title_candidates ---
    candidates = obj["title_candidates"]
    if not isinstance(candidates, list):
        raise ValueError("title_candidates 必须是数组")
    if len(candidates) < TITLE_CANDIDATE_COUNT:
        warnings.append(
            f"title_candidates 只有 {len(candidates)} 条，要求 {TITLE_CANDIDATE_COUNT} 条"
        )
    clean_candidates = []
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            raise ValueError(f"title_candidates[{i}] 不是对象")
        if "title" not in c:
            raise ValueError(f"title_candidates[{i}] 缺少 title 字段")
        if not isinstance(c["title"], str) or not c["title"].strip():
            raise ValueError(f"title_candidates[{i}].title 为空")
        title_text = c["title"].strip()
        rationale = ""
        if "rationale" in c and isinstance(c["rationale"], str):
            rationale = c["rationale"].strip()
        clean_candidates.append({"title": title_text, "rationale": rationale})
    clean["title_candidates"] = clean_candidates

    # --- recommended_title ---
    recommended = obj.get("recommended_title", "")
    if not isinstance(recommended, str) or not recommended.strip():
        raise ValueError("recommended_title 为空")
    clean["recommended_title"] = recommended.strip()

    # Verify recommended_title matches one of the candidates
    candidate_titles = {c["title"] for c in clean_candidates}
    if clean["recommended_title"] not in candidate_titles:
        warnings.append(
            f"recommended_title '{clean['recommended_title']}' 不在 title_candidates 中"
        )

    # --- subtitle ---
    subtitle = obj.get("subtitle", "")
    if not isinstance(subtitle, str):
        raise ValueError("subtitle 必须是字符串")
    subtitle = subtitle.strip()
    if len(subtitle) > MAX_SUBTITLE_CHARS:
        warnings.append(
            f"subtitle 长度 {len(subtitle)}，超过上限 {MAX_SUBTITLE_CHARS} 字"
        )
    clean["subtitle"] = subtitle

    # --- blurb ---
    blurb = obj.get("blurb", "")
    if not isinstance(blurb, str):
        raise ValueError("blurb 必须是字符串")
    blurb = blurb.strip()
    if len(blurb) > MAX_BLURB_CHARS:
        warnings.append(
            f"blurb 长度 {len(blurb)}，超过上限 {MAX_BLURB_CHARS} 字"
        )
    clean["blurb"] = blurb

    # --- tagline ---
    tagline = obj.get("tagline", "")
    if not isinstance(tagline, str):
        raise ValueError("tagline 必须是字符串")
    tagline = tagline.strip()
    if len(tagline) > MAX_TAGLINE_CHARS:
        warnings.append(
            f"tagline 长度 {len(tagline)}，超过上限 {MAX_TAGLINE_CHARS} 字"
        )
    clean["tagline"] = tagline

    # --- cover_prompt_en ---
    cover = obj.get("cover_prompt_en", "")
    if not isinstance(cover, str):
        raise ValueError("cover_prompt_en 必须是字符串")
    cover = cover.strip()
    if not cover:
        raise ValueError("cover_prompt_en 为空")
    # Rough word count check (50-100 words ideal, warn if way off)
    word_count = len(cover.split())
    if word_count < 30:
        warnings.append(f"cover_prompt_en 仅 {word_count} 词，偏短（建议 50-100）")
    if word_count > 150:
        warnings.append(f"cover_prompt_en 有 {word_count} 词，偏长（建议 50-100）")
    clean["cover_prompt_en"] = cover

    # --- category_tags ---
    tags = obj.get("category_tags", [])
    if not isinstance(tags, list):
        raise ValueError("category_tags 必须是数组")
    clean_tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
    if len(clean_tags) < CATEGORY_TAG_MIN:
        warnings.append(
            f"category_tags 只有 {len(clean_tags)} 个，要求 {CATEGORY_TAG_MIN}-{CATEGORY_TAG_MAX}"
        )
    if len(clean_tags) > CATEGORY_TAG_MAX:
        warnings.append(
            f"category_tags 有 {len(clean_tags)} 个，截取前 {CATEGORY_TAG_MAX} 个"
        )
        clean_tags = clean_tags[:CATEGORY_TAG_MAX]
    clean["category_tags"] = clean_tags

    return clean, warnings


# ── Agent class ───────────────────────────────────────────────

class PackagingAgent(BaseAgent):
    name = "packaging"
    temperature = 0.6
    response_format = "json"
    max_tokens = 4000

    SYSTEM_PROMPT = (
        "你是资深网文出版编辑，专职为完成或正在连载的小说做发布包装。"
        "你的工作不是改稿，是把稿件变成读者愿意点开的商品。\n"
        "\n"
        "工作输入：\n"
        "- 本作的 setting（题材、基调、主角、时代）\n"
        "- 已有章节（提取真实细节，不能凭空造）\n"
        "- 大纲（了解主线走向）\n"
        "\n"
        "工作输出（严格 JSON）：\n"
        "- 5 个书名候选 + 每个的选名理由\n"
        "- 1 个副标题（≤25 字）\n"
        "- 1 段简介（≤300 字）\n"
        "- 1 个 tagline（≤15 字，社媒式）\n"
        "- 1 个英文封面 prompt（Midjourney/SD 风格，50-100 词）\n"
        "- 3-5 个类别标签\n"
        "\n"
        "硬规则：\n"
        "- 书名不能包含『战神/至尊/神帝』等万年网文套话\n"
        "- 书名要具体：动词、名词、数字优先；避免抽象的『传奇』『风云』\n"
        "- 简介只从已有章节里提炼，不编造没写过的情节\n"
        "- 简介三选一写法：①主线概括+留悬念 ②冲突开场抓眼球 ③经典桥段小剧场\n"
        "  在 blurb_strategy 字段里说明选哪种（填 1/2/3）\n"
        "- 封面 prompt 全英文，给 AI 画图用；必须体现题材与时代，"
        "不要人物面部细节（避免 uncanny valley）\n"
        "- category_tags 按读者检索习惯写（不是作者的艺术分类）\n"
        "- 严格输出 JSON，不写任何散文或解释\n"
        "\n"
        "参考示例（港综·1983）：\n"
        '  recommended_title: "港务档案" 不是 "无敌枭雄"\n'
        "  blurb 侧重: 1983 + 福建新移民 + 系统 + 数字不会骗人（设定钩子）\n"
        "  cover_prompt_en 示例: 1980s Hong Kong skyline at dusk, neon + rain on "
        "asphalt, no characters faces visible, muted teal and amber, film grain\n"
    )

    OUTPUT_SCHEMA = """{
  "title_candidates": [
    {"title": "港务档案", "rationale": "理由一句话"},
    ...5 条
  ],
  "recommended_title": "港务档案",
  "subtitle": "≤25字",
  "blurb": "≤300字",
  "blurb_strategy": 1,
  "tagline": "≤15字",
  "cover_prompt_en": "50-100 word English visual description",
  "category_tags": ["标签1", "标签2", "标签3"]
}"""

    def _build_prompts(self, bb: Blackboard, **_):
        inputs_read: list[str] = []

        # 1. Setting metadata
        try:
            setting = bb.read_yaml("setting.yaml")
            inputs_read.append("state/setting.yaml")
        except (OSError, Exception):
            setting = {}
        display_name = setting.get("display_name", "")
        genre = setting.get("genre", "")
        era_label = setting.get("era", "")
        tone = setting.get("tone", "")
        protagonist = setting.get("protagonist_name", "")
        protagonist_hook = setting.get("protagonist_hook", "")
        author_hints = setting.get("author_persona_hints", [])
        genre_avoid = setting.get("genre_avoid", [])

        # 2. Outline summary
        try:
            outline = bb.read_json("outline.json")
            inputs_read.append("state/outline.json")
        except (OSError, Exception):
            outline = {}
        outline_title = outline.get("title", "")
        outline_synopsis = outline.get("synopsis", "")
        chapters_outline = outline.get("chapters", [])
        # Extract chapter titles for arc awareness
        chapter_arc = [
            f"第{c.get('ch','?')}章 {c.get('title','')}"
            for c in chapters_outline[: min(len(chapters_outline), 10)]
        ]

        # 3. Characters excerpt (names only, for blurb authenticity)
        character_names: list[str] = []
        try:
            chars = bb.read_yaml("characters.yaml")
            inputs_read.append("state/characters.yaml")
            if isinstance(chars, dict):
                for group in chars.values():
                    if isinstance(group, list):
                        for ch in group:
                            if isinstance(ch, dict) and ch.get("name"):
                                character_names.append(ch["name"])
        except (OSError, Exception):
            pass

        # 4. Era flavour (first N chars)
        era_snippet = ""
        try:
            era_full = bb.read_text("era.md")
            inputs_read.append("state/era.md")
            era_snippet = era_full[:800]
        except (OSError, Exception):
            pass

        # 5. Chapters: read first chapter (first ~1500 chars) + find last chapter
        chapter_snippets: list[str] = []
        chapter_files = sorted(
            p for p in bb.list_files("chapters", "ch*.md")
            if p.name.startswith("ch") and p.suffix == ".md"
        )
        if chapter_files:
            # First chapter
            try:
                first_text = bb.read_text(f"chapters/{chapter_files[0].name}")
                chapter_snippets.append(
                    f"## 第1章节选\n\n{first_text[:1500]}"
                )
                inputs_read.append(f"state/chapters/{chapter_files[0].name}")
            except (OSError, Exception):
                pass
            # Last chapter (if different from first)
            if len(chapter_files) > 1:
                last_file = chapter_files[-1]
                try:
                    last_text = bb.read_text(f"chapters/{last_file.name}")
                    # Take first 800 chars of last chapter for arc awareness
                    chapter_snippets.append(
                        f"## 最新章节节选 ({last_file.stem})\n\n{last_text[:800]}"
                    )
                    inputs_read.append(f"state/chapters/{last_file.name}")
                except (OSError, Exception):
                    pass

        # 6. Optional user preferences
        user_prefs_block = ""
        try:
            prefs = bb.read_yaml("packaging_prefs.yaml")
            inputs_read.append("state/packaging_prefs.yaml")
            user_prefs_block = "\n# 作者偏好\n\n" + json.dumps(
                prefs, ensure_ascii=False, indent=2
            )
        except (OSError, Exception):
            pass

        # ── Build user prompt ──
        chapter_prose_block = (
            "\n\n".join(chapter_snippets)
            if chapter_snippets
            else "（暂无章节产出）"
        )

        user = (
            f"# 作品设定\n\n"
            f"- 书名（大纲用）: {outline_title or display_name}\n"
            f"- 题材: {genre}\n"
            f"- 时代/世界观: {era_label}\n"
            f"- 基调: {tone}\n"
            f"- 主角: {protagonist}\n"
            f"- 主角设定钩子: {protagonist_hook}\n"
            f"- 作者提示: {json.dumps(author_hints, ensure_ascii=False)}\n"
            f"- 避雷: {json.dumps(genre_avoid, ensure_ascii=False)}\n"
            f"\n# 大纲概要\n\n"
            f"大纲简介: {outline_synopsis or '(未提供)'}\n"
            f"章节目录: {json.dumps(chapter_arc, ensure_ascii=False)}\n"
            f"\n# 主要人物\n\n"
            f"{', '.join(character_names) if character_names else '(未读取到)'}\n"
            f"\n# 时代背景（节选）\n\n{era_snippet or '(无)'}\n"
            f"\n# 章节正文（节选）\n\n{chapter_prose_block}\n"
            f"{user_prefs_block}\n"
            f"# 输出格式（严格 JSON）\n\n"
            f"```json\n{self.OUTPUT_SCHEMA}\n```\n"
        )

        return self.SYSTEM_PROMPT, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, **_):
        obj = _parse_json(raw)
        clean, warnings = validate_packaging(obj)

        # Merge blurb_strategy back in if present (not required in schema but nice to keep)
        if "blurb_strategy" in obj:
            clean["blurb_strategy"] = obj["blurb_strategy"]

        if warnings:
            clean["_validation_warnings"] = warnings

        bb.write_json("packaging.json", clean)


def _parse_json(raw: str):
    """Strip ```json fences if present, then json.loads."""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    return json.loads(s)
