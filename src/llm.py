"""LLM client — OpenAI-compatible Chat Completions against DeepSeek-V4-Pro.

Every successful call appends a structured record to state/prompts_log.jsonl
so the Web UI's Prompt Inspector can show "each agent call is fresh context,
here's exactly what was sent and what came back". This is the UI affordance
that converts our architecture claims into visible evidence.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx

from . import config

# We reuse a single httpx client for connection pooling.
# Read timeout is long because Generator can take 2-4 minutes for 3000-char
# Chinese chapters. We trust the server's own timeout to cut us off if it dies.
_client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0))

def _prompts_log_path():
    """Resolve at call time so it follows project switches."""
    return config.STATE_DIR / "prompts_log.jsonl"


def _log_call(entry: dict) -> None:
    """Append one call record to the prompt log. Atomic-append via open('a')."""
    log_path = _prompts_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# 模型能力注册表：某些模型服务端强制单一 temperature，传任何其他值都返回 400。
# 规则：key 是 model id 的匹配前缀/子串，value 是允许的固定 temperature。
# 匹配时用 substring，不用正则，避免意外误伤。
# 新模型加到这里即可；若模型接受任意值，不用登记。
_FIXED_TEMPERATURE_MODELS: dict[str, float] = {
    "kimi-k2": 0.6,   # 包括 kimi-k2.6 / kimi-k2 等变体
}

# 用于去重 warning（同一 model 在首次调用时打印一次，避免每次 chat 都刷日志）
_warned_models: set[str] = set()


def _clamp_temperature(model: str, requested: float) -> float:
    """Clamp temperature if the model has a server-side fixed-value constraint.

    Returns the temperature to actually send. If the model is in the registry
    and the requested value differs, emit a one-time stderr warning so users
    see why their agent's temperature setting is being ignored.
    """
    for key, fixed in _FIXED_TEMPERATURE_MODELS.items():
        if key in model:
            if abs(requested - fixed) > 1e-6 and model not in _warned_models:
                import sys
                print(
                    f"[llm] Model '{model}' requires temperature={fixed}; "
                    f"requested {requested} will be clamped. "
                    f"Agent temperature settings degrade to soft hints on this model.",
                    file=sys.stderr,
                )
                _warned_models.add(model)
            return fixed
    return requested


def chat(
    system: str,
    user: str,
    *,
    agent_name: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: Literal["text", "json"] = "text",
    inputs_read: list[str] | None = None,
) -> str:
    """Send a chat completion request. Returns the raw assistant text.

    Args:
        system: system prompt
        user: user prompt
        agent_name: for logging (e.g., 'planner', 'generator')
        temperature: sampling
        max_tokens: server-side cap
        response_format: 'json' forces JSON mode when supported
        inputs_read: optional list of state/ file paths this agent read,
                     purely for logging transparency.

    Raises:
        httpx.HTTPError on transport error.
        RuntimeError on non-2xx with provider error body.
    """
    config.assert_llm_configured()

    call_id = str(uuid.uuid4())
    started_at = time.time()

    # 模型能力钳制：部分模型服务端强制单一 temperature（如 kimi-k2.6 只允许 0.6）。
    # 业务层 agent 设置的 temperature（Planner 0.4 / Generator 0.85 等）在此类
    # 模型上会退化为服务端允许值——保证流水线能跑，创造性意图退化为软建议。
    effective_temp = _clamp_temperature(config.LLM_MODEL, temperature)

    payload: dict = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": effective_temp,
        "max_tokens": max_tokens,
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    url = f"{config.LLM_BASE_URL}/chat/completions"
    resp = _client.post(url, headers=headers, json=payload)
    latency_ms = int((time.time() - started_at) * 1000)

    if resp.status_code >= 400:
        err_body = resp.text
        _log_call(
            {
                "id": call_id,
                "ts": started_at,
                "agent_name": agent_name,
                "system": system,
                "user": user,
                "inputs_read": inputs_read or [],
                "model": config.LLM_MODEL,
                "temperature": effective_temp,
                "response_format": response_format,
                "latency_ms": latency_ms,
                "output": None,
                "usage": None,
                "error": f"HTTP {resp.status_code}: {err_body[:500]}",
            }
        )
        raise RuntimeError(f"LLM call failed ({resp.status_code}): {err_body[:500]}")

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    _log_call(
        {
            "id": call_id,
            "ts": started_at,
            "agent_name": agent_name,
            "system": system,
            "user": user,
            "inputs_read": inputs_read or [],
            "model": config.LLM_MODEL,
            "temperature": effective_temp,
            "response_format": response_format,
            "latency_ms": latency_ms,
            "output": text,
            "usage": usage,
            "error": None,
        }
    )
    return text


def smoke_test() -> str:
    """Quick connectivity sanity check."""
    return chat(
        system="You are a terse assistant.",
        user="说一句中文，然后报出你是哪个模型。",
        agent_name="__smoke__",
        temperature=0.0,
        max_tokens=120,
    )


if __name__ == "__main__":
    print(smoke_test())
