"""Lock in temperature clamping for models with server-side fixed-value constraints.

Why: some providers (e.g. kimi-k2.6 on EasyClaw) return HTTP 400
"invalid temperature: only 0.6 is allowed for this model" when any other
temperature is passed. Agent-level temperature (Planner 0.4, Generator 0.85,
Evaluator 0.0) would otherwise crash the entire pipeline on such models.

These tests verify _clamp_temperature clamps for registered model prefixes
and passes through for unregistered ones, without needing a live API.
"""
from __future__ import annotations

import pytest

from src.llm import _FIXED_TEMPERATURE_MODELS, _clamp_temperature, _warned_models


@pytest.fixture(autouse=True)
def reset_warnings():
    """Reset the warning-deduplication set so each test gets a fresh print."""
    _warned_models.clear()
    yield
    _warned_models.clear()


def test_kimi_k2_variants_are_clamped_to_fixed_value():
    # kimi-k2 家族任意 temperature 进来都出 0.6
    assert _clamp_temperature("kimi-k2.6", 0.85) == 0.6
    assert _clamp_temperature("kimi-k2.6", 0.4) == 0.6
    assert _clamp_temperature("kimi-k2.6", 0.0) == 0.6
    assert _clamp_temperature("kimi-k2", 0.85) == 0.6


def test_kimi_k2_with_correct_value_is_noop():
    # 请求值已经等于允许值时，不 clamp 不 warn
    assert _clamp_temperature("kimi-k2.6", 0.6) == 0.6
    # 没有加入 warned set（因为不 warn）
    assert "kimi-k2.6" not in _warned_models


def test_unregistered_models_pass_through():
    # 不在注册表的模型透明传递
    assert _clamp_temperature("deepseek-v4-pro", 0.85) == 0.85
    assert _clamp_temperature("deepseek-v4-pro", 0.0) == 0.0
    assert _clamp_temperature("gpt-4", 1.0) == 1.0
    assert _clamp_temperature("claude-opus-4", 0.3) == 0.3


def test_warning_emitted_only_once_per_model(capsys):
    # 同一 model 多次被 clamp 只打一次 warning
    _clamp_temperature("kimi-k2.6", 0.85)
    _clamp_temperature("kimi-k2.6", 0.4)
    _clamp_temperature("kimi-k2.6", 0.0)
    captured = capsys.readouterr()
    # 只出现一次 "Model 'kimi-k2.6' requires"
    assert captured.err.count("kimi-k2.6") == 1
    assert "will be clamped" in captured.err


def test_registry_has_kimi_k2_entry():
    # 防回归：注册表里必须有 kimi-k2 钳制规则
    assert any("kimi-k2" in key for key in _FIXED_TEMPERATURE_MODELS)
    # 其值确实是服务端要求的 0.6
    for key, val in _FIXED_TEMPERATURE_MODELS.items():
        if "kimi-k2" in key:
            assert val == 0.6
