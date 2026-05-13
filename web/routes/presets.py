"""Preset management routes: /api/presets* (list/detail/delete) + /presets* views.

Creation of presets has moved to the unified /api/jobs blueprint
(see :mod:`web.routes.jobs`). This module now only handles read-only
listing, detail, deletion, and template rendering — the three "new preset"
flows (from-novel / from-description / blank) all submit to /api/jobs.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template

from src import config

from web._shared import (
    BUILTIN_PRESETS,
    READONLY_MODE,
)

bp = Blueprint("presets", __name__)


def _preset_dir(preset_id: str):
    return config.PRESETS_DIR / preset_id


@bp.get("/api/presets")
def api_presets_list():
    """List all presets (built-in + user-created). Read-only summary."""
    import yaml
    items: list[dict] = []
    if config.PRESETS_DIR.exists():
        for p in sorted(config.PRESETS_DIR.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            meta: dict = {}
            gy = p / "genre.yaml"
            if gy.exists():
                try:
                    meta = yaml.safe_load(gy.read_text(encoding="utf-8")) or {}
                except (OSError, yaml.YAMLError):
                    meta = {}
            items.append({
                "id": p.name,
                "display_name": meta.get("display_name", p.name),
                "tone": meta.get("tone", ""),
                "builtin": p.name in BUILTIN_PRESETS,
            })
    return jsonify({"presets": items})


@bp.get("/api/presets/<pid>")
def api_preset_detail(pid: str):
    pd = _preset_dir(pid)
    if not pd.exists():
        return jsonify({"ok": False, "reason": "preset not found"}), 404
    files = sorted(f.name for f in pd.iterdir() if f.is_file())
    novels: list[str] = []
    novels_dir = pd / "novels"
    if novels_dir.exists():
        novels = sorted(
            n.name for n in novels_dir.iterdir()
            if n.is_file() and n.suffix.lower() == ".txt"
        )
    return jsonify({
        "id": pid,
        "files": files,
        "novels": novels,
        "builtin": pid in BUILTIN_PRESETS,
    })


@bp.delete("/api/presets/<pid>")
def api_preset_delete(pid: str):
    """Delete a user-created preset. Built-ins are hard-refused."""
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    if pid in BUILTIN_PRESETS:
        return jsonify({
            "ok": False,
            "reason": "built-in preset cannot be deleted",
        }), 403
    pd = _preset_dir(pid)
    if not pd.exists():
        return jsonify({"ok": False, "reason": "preset not found"}), 404
    import shutil
    shutil.rmtree(pd)
    return jsonify({"ok": True, "id": pid})


@bp.get("/presets")
def view_presets_index():
    return render_template("presets/index.html")


@bp.get("/presets/new")
def view_preset_new():
    return render_template("presets/new.html")


@bp.get("/presets/<pid>")
def view_preset_detail(pid: str):
    pd = _preset_dir(pid)
    if not pd.exists():
        abort(404)
    return render_template("presets/detail.html", preset_id=pid)
