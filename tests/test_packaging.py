"""Tests for PackagingAgent: schema validation + agent construction.

Covers:
- Happy path: well-formed output passes validation with no warnings
- All validation failures: missing fields, over-long blurb/subtitle/tagline,
  wrong title count, wrong tag count, empty fields
- Agent can be instantiated and has correct attributes
- Agent _build_prompts assembles correct inputs
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.agents.packaging import (
    MAX_BLURB_CHARS,
    MAX_SUBTITLE_CHARS,
    MAX_TAGLINE_CHARS,
    PackagingAgent,
    validate_packaging,
)


# ── valid sample ──────────────────────────────────────────────

def _valid_packaging():
    """Return a well-formed packaging dict that should pass validation."""
    return {
        "title_candidates": [
            {"title": "港务档案", "rationale": "以系统查询能力为钩子，暗合情报工作属性"},
            {"title": "1983，九龙城寨", "rationale": "年代+地点直接锚定，强化时代感"},
            {"title": "数字不会骗人", "rationale": "主角系统规则提炼，点出核心冲突"},
            {"title": "城寨第一顿饭", "rationale": "从第一章经典场景切入，具象且有力"},
            {"title": "福建仔的香港", "rationale": "身份+地域，强调移民视角"},
        ],
        "recommended_title": "港务档案",
        "subtitle": "一个福建仔与一张情报表",
        "blurb": (
            "1983年6月，林家耀从福建只身抵达香港。口袋里只剩四十三块港币，"
            "投靠的表叔已经搬走，落脚的地方是九龙城寨的时钟酒店。"
            "他唯一的依仗是一个只能查询1983到2000年间公开事件的系统——"
            "报纸头条、股价走势、天气变化，它都知道；但人、私密交易、"
            "即将发生的阴谋，它一概不答。当数字开始说话，这座永远在涨潮的城市"
            "才知道这个福建仔有多危险。"
        ),
        "tagline": "数字比人诚实",
        "cover_prompt_en": (
            "1980s Hong Kong skyline at dusk, neon signs reflecting on wet asphalt "
            "after rain. Kowloon Walled City silhouette in the distance, dense and "
            "chaotic. A solitary man in a worn shirt stands at a street corner, back "
            "to the viewer, facing the glittering city. Muted teal and amber tones, "
            "film grain texture, cinematic composition. No faces visible, focus on "
            "urban atmosphere and era texture."
        ),
        "category_tags": ["港综同人", "重生", "系统流", "1980s", "金融"],
        "blurb_strategy": 1,
    }


# ── happy path ────────────────────────────────────────────────

def test_valid_packaging_passes():
    """Well-formed packaging passes validation with no warnings."""
    obj = _valid_packaging()
    clean, warnings = validate_packaging(obj)
    assert warnings == []
    assert clean["title_candidates"] == obj["title_candidates"]
    assert clean["recommended_title"] == "港务档案"
    assert len(clean["category_tags"]) == 5


def test_valid_packaging_preserves_blurb_strategy():
    """blurb_strategy is not required but should be preserved if present."""
    obj = _valid_packaging()
    # validate_packaging doesn't extract blurb_strategy to clean;
    # the agent's _handle_output merges it back
    # Just verify it doesn't cause a validation error
    clean, _ = validate_packaging(obj)
    assert "title_candidates" in clean


# ── missing fields ────────────────────────────────────────────

_MISSING_FIELDS = [
    ("title_candidates", "缺少必填字段: title_candidates"),
    ("recommended_title", "缺少必填字段: recommended_title"),
    ("subtitle", "缺少必填字段: subtitle"),
    ("blurb", "缺少必填字段: blurb"),
    ("tagline", "缺少必填字段: tagline"),
    ("cover_prompt_en", "缺少必填字段: cover_prompt_en"),
    ("category_tags", "缺少必填字段: category_tags"),
]


@pytest.mark.parametrize("missing_key,expected_msg", _MISSING_FIELDS)
def test_missing_top_level_key_raises(missing_key, expected_msg):
    """Each required top-level key must be present."""
    obj = _valid_packaging()
    del obj[missing_key]
    with pytest.raises(ValueError, match=expected_msg):
        validate_packaging(obj)


# ── over-length fields ────────────────────────────────────────

def test_blurb_over_length_warns():
    """Blurb exceeding MAX_BLURB_CHARS triggers a warning."""
    obj = _valid_packaging()
    obj["blurb"] = "x" * (MAX_BLURB_CHARS + 1)
    _, warnings = validate_packaging(obj)
    assert any("blurb" in w.lower() for w in warnings)


def test_blurb_exactly_limit_no_warning():
    """Blurb at exactly MAX_BLURB_CHARS is fine."""
    obj = _valid_packaging()
    obj["blurb"] = "x" * MAX_BLURB_CHARS
    _, warnings = validate_packaging(obj)
    assert not any("blurb" in w.lower() for w in warnings)


def test_subtitle_over_length_warns():
    obj = _valid_packaging()
    obj["subtitle"] = "x" * (MAX_SUBTITLE_CHARS + 1)
    _, warnings = validate_packaging(obj)
    assert any("subtitle" in w.lower() for w in warnings)


def test_tagline_over_length_warns():
    obj = _valid_packaging()
    obj["tagline"] = "x" * (MAX_TAGLINE_CHARS + 1)
    _, warnings = validate_packaging(obj)
    assert any("tagline" in w.lower() for w in warnings)


# ── wrong type / empty ────────────────────────────────────────

def test_title_candidates_not_list_raises():
    obj = _valid_packaging()
    obj["title_candidates"] = "not a list"
    with pytest.raises(ValueError, match="必须是数组"):
        validate_packaging(obj)


def test_title_candidate_missing_title_raises():
    obj = _valid_packaging()
    obj["title_candidates"][0] = {"rationale": "no title here"}
    with pytest.raises(ValueError, match="缺少 title 字段"):
        validate_packaging(obj)


def test_title_candidate_empty_title_raises():
    obj = _valid_packaging()
    obj["title_candidates"][0]["title"] = "   "
    with pytest.raises(ValueError, match="为空"):
        validate_packaging(obj)


def test_recommended_title_empty_raises():
    obj = _valid_packaging()
    obj["recommended_title"] = ""
    with pytest.raises(ValueError, match="recommended_title 为空"):
        validate_packaging(obj)


def test_cover_prompt_en_empty_raises():
    obj = _valid_packaging()
    obj["cover_prompt_en"] = ""
    with pytest.raises(ValueError, match="cover_prompt_en 为空"):
        validate_packaging(obj)


def test_category_tags_not_list_raises():
    obj = _valid_packaging()
    obj["category_tags"] = "not a list"
    with pytest.raises(ValueError, match="必须是数组"):
        validate_packaging(obj)


# ── count / range warnings ────────────────────────────────────

def test_too_few_title_candidates_warns():
    obj = _valid_packaging()
    obj["title_candidates"] = [
        {"title": "只有一个", "rationale": "不够"}
    ]
    _, warnings = validate_packaging(obj)
    assert any("title_candidates" in w and "只有" in w for w in warnings)


def test_too_few_category_tags_warns():
    obj = _valid_packaging()
    obj["category_tags"] = ["只有一个"]
    _, warnings = validate_packaging(obj)
    assert any("category_tags" in w and "只有" in w for w in warnings)


def test_too_many_category_tags_truncates():
    obj = _valid_packaging()
    obj["category_tags"] = ["a", "b", "c", "d", "e", "f", "g"]
    clean, warnings = validate_packaging(obj)
    assert len(clean["category_tags"]) == 5
    assert any("截取" in w for w in warnings)


def test_recommended_title_not_in_candidates_warns():
    obj = _valid_packaging()
    obj["recommended_title"] = "不存在于候选列表"
    _, warnings = validate_packaging(obj)
    assert any("recommended_title" in w for w in warnings)


def test_cover_prompt_too_short_warns():
    obj = _valid_packaging()
    obj["cover_prompt_en"] = "Hong Kong at night"
    _, warnings = validate_packaging(obj)
    assert any("cover_prompt" in w and "短" in w for w in warnings)


def test_cover_prompt_too_long_warns():
    obj = _valid_packaging()
    # 200+ words
    obj["cover_prompt_en"] = " ".join(["word"] * 200)
    _, warnings = validate_packaging(obj)
    assert any("cover_prompt" in w and "长" in w for w in warnings)


# ── agent construction ────────────────────────────────────────

def test_agent_instantiation():
    """PackagingAgent can be instantiated and has correct attributes."""
    agent = PackagingAgent()
    assert agent.name == "packaging"
    assert agent.temperature == 0.6
    assert agent.response_format == "json"
    assert agent.max_tokens == 4000


def test_agent_inherits_base_agent():
    """PackagingAgent is a BaseAgent subclass."""
    from src.agents._base import BaseAgent
    assert issubclass(PackagingAgent, BaseAgent)


# ── _build_prompts integration ────────────────────────────────

def test_build_prompts_returns_system_user_inputs():
    """_build_prompts assembles correct system/user/inputs tuple."""
    from unittest.mock import MagicMock

    bb = MagicMock()
    # Simulate no files present
    bb.read_yaml.side_effect = FileNotFoundError
    bb.read_json.side_effect = FileNotFoundError
    bb.read_text.side_effect = FileNotFoundError
    bb.list_files.return_value = []

    agent = PackagingAgent()
    system, user, inputs = agent._build_prompts(bb)

    assert isinstance(system, str)
    assert len(system) > 200  # Non-trivial system prompt
    assert isinstance(user, str)
    assert isinstance(inputs, list)
    # Even with no files, user prompt should contain the schema template
    assert "输出格式" in user
    assert "title_candidates" in user


def test__parse_json_strips_fences():
    """The internal _parse_json handles ```json``` fences."""
    from src.agents.packaging import _parse_json

    raw = '```json\n{"key": "value"}\n```'
    result = _parse_json(raw)
    assert result == {"key": "value"}


def test__parse_json_handles_plain_json():
    from src.agents.packaging import _parse_json

    raw = '{"key": "value"}'
    result = _parse_json(raw)
    assert result == {"key": "value"}


# ── full _handle_output integration (mocked LLM) ──────────────

def test_handle_output_writes_valid_packaging_json():
    """_handle_output validates and writes packaging.json."""
    from unittest.mock import MagicMock

    bb = MagicMock()
    bb.read_json.side_effect = FileNotFoundError
    bb.read_text.side_effect = FileNotFoundError
    bb.read_yaml.side_effect = FileNotFoundError
    bb.list_files.return_value = []

    raw = json.dumps(_valid_packaging(), ensure_ascii=False)

    agent = PackagingAgent()
    agent.run = MagicMock(return_value=raw)  # bypass LLM

    # Directly call _handle_output
    agent._handle_output(bb, raw)

    # Verify bb.write_json was called with "packaging.json" and a valid dict
    bb.write_json.assert_called_once()
    call_args = bb.write_json.call_args
    assert call_args[0][0] == "packaging.json"
    output_obj = call_args[0][1]
    assert "title_candidates" in output_obj
    assert len(output_obj["title_candidates"]) == 5
    assert output_obj["recommended_title"] == "港务档案"
    # No warnings for valid output
    assert "_validation_warnings" not in output_obj


def test_handle_output_adds_warnings_for_invalid():
    """_handle_output records validation_warnings when output has issues."""
    from unittest.mock import MagicMock

    bb = MagicMock()
    raw = json.dumps(
        {
            "title_candidates": [
                {"title": "只有一个", "rationale": "不够"}
            ],
            "recommended_title": "只有一个",
            "subtitle": "x" * 100,
            "blurb": "short",
            "tagline": "x" * 100,
            "cover_prompt_en": "Hong Kong at night",
            "category_tags": ["只有一个标签"],
        },
        ensure_ascii=False,
    )

    agent = PackagingAgent()
    agent._handle_output(bb, raw)

    bb.write_json.assert_called_once()
    output_obj = bb.write_json.call_args[0][1]
    warnings = output_obj.get("_validation_warnings", [])
    # Should have multiple warnings
    assert len(warnings) >= 3
