"""Env management routes: /api/env (GET/POST).

Reads and writes the project root .env file with a whitelist of allowed
keys. Sensitive keys (API tokens) are masked on GET.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from src import config

from web._shared import READONLY_MODE

bp = Blueprint("env", __name__)

_ENV_WRITABLE = {
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "PERPLEXITY_API_KEY",
    "PERPLEXITY_BASE_URL",
    "PERPLEXITY_MODEL",
}
_ENV_SENSITIVE = {"DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY"}


def _env_path() -> Path:
    return config._PROJECT_ROOT / ".env"


def _parse_env(text: str) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, ignore blanks and #comments.

    We avoid python-dotenv's parse here to keep write-back deterministic.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def _serialize_env(existing: dict[str, str], updates: dict[str, str]) -> str:
    """Merge updates into existing, write back in deterministic order.

    Whitelist keys come first (alphabetical), then any other keys the user
    might have added manually. Empty-string values mean "remove this key".
    """
    merged = dict(existing)
    for k, v in updates.items():
        if v == "":
            merged.pop(k, None)
        else:
            merged[k] = v
    lines: list[str] = []
    for k in sorted(_ENV_WRITABLE):
        if k in merged:
            lines.append(f"{k}={merged[k]}")
    for k, v in sorted(merged.items()):
        if k not in _ENV_WRITABLE:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def _mask(value: str) -> str:
    if not value:
        return ""
    tail = value[-4:] if len(value) >= 4 else value
    return f"****{tail}"


def _is_placeholder_key(value: str) -> bool:
    """Empty or the .env.example placeholder string both count as 'not set'."""
    return not value or value.startswith("dc-sk-put-yours")


@bp.get("/api/env")
def api_env_get():
    env_file = _env_path()
    current = _parse_env(env_file.read_text(encoding="utf-8")) if env_file.exists() else {}
    out: dict[str, dict] = {}
    for k in sorted(_ENV_WRITABLE):
        v = current.get(k, "")
        if k in _ENV_SENSITIVE:
            out[k] = {
                "set": not _is_placeholder_key(v),
                "preview": _mask(v),
                "length": len(v),
            }
        else:
            out[k] = {"set": bool(v), "value": v}
    return jsonify(out)


@bp.post("/api/env")
def api_env_post():
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or not data:
        return jsonify({"ok": False, "reason": "json object with at least one key required"}), 400
    updates: dict[str, str] = {}
    for k, v in data.items():
        if k not in _ENV_WRITABLE:
            return jsonify({"ok": False, "reason": f"key not allowed: {k}"}), 400
        if not isinstance(v, str):
            return jsonify({"ok": False, "reason": f"value for {k} must be string"}), 400
        # Reject newline/null injection — otherwise a malicious value like
        # "legit\nINJECTED_KEY=pwned" would smuggle extra lines into .env.
        if any(c in v for c in ("\n", "\r", "\0")):
            return jsonify({"ok": False, "reason": f"value for {k} contains illegal control chars"}), 400
        updates[k] = v

    env_file = _env_path()
    existing = _parse_env(env_file.read_text(encoding="utf-8")) if env_file.exists() else {}
    new_text = _serialize_env(existing, updates)

    # Atomic write
    tmp = env_file.with_suffix(".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, env_file)

    # Live reload so later LLM calls in the same process see new values
    config.reload_env()
    return jsonify({"ok": True, "updated": sorted(updates.keys())})
