"""Preset management routes: /api/presets* + /presets* views.

Covers listing, detail, delete, three "new preset" variants
(from-novel async, blank sync, from-description async), and polling.
"""
from __future__ import annotations

import threading
import time

from flask import Blueprint, abort, jsonify, render_template, request

from src import config

from web._shared import (
    BUILTIN_PRESETS,
    READONLY_MODE,
    _PRESET_JOB_LOCK,
    _PRESET_JOBS,
    _initial_job_state,
    _make_phase_cb,
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


@bp.post("/api/presets/new-from-novel")
def api_preset_new_from_novel():
    """Kick off a genre-extraction job in a background thread.

    Validation happens synchronously (id, sources, no existing preset, no
    running job for this id). Once accepted, extract_to_preset runs in a
    daemon thread; the caller polls /api/presets/<pid>/status.
    """
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    body = request.get_json(silent=True) or {}
    pid = (body.get("id") or "").strip()
    sources = body.get("sources") or []
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    if not sources:
        return jsonify({"ok": False, "reason": "sources required"}), 400
    if _preset_dir(pid).exists():
        return jsonify({"ok": False, "reason": "preset already exists"}), 409

    with _PRESET_JOB_LOCK:
        existing = _PRESET_JOBS.get(pid)
        if existing is not None and existing.get("state") == "running":
            return jsonify({"ok": False, "reason": "job already running"}), 409
        _PRESET_JOBS[pid] = _initial_job_state()

    with_trial = bool(body.get("with_trial", False))

    def _worker():
        try:
            # Import lazily so test monkeypatch on the module attribute
            # takes effect — we resolve the function fresh each call.
            from src.genre_extractor import to_preset
            to_preset.extract_to_preset(
                pid,
                sources=sources,
                with_trial=with_trial,
                on_phase=_make_phase_cb(_PRESET_JOBS, _PRESET_JOB_LOCK, pid),
            )
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid].update({
                    "state": "done", "error": None,
                    "phase": "done", "updated_at": time.time(),
                })
        except Exception as e:
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid].update({
                    "state": "failed", "error": str(e),
                    "updated_at": time.time(),
                })

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "preset_id": pid, "state": "running"}), 202


# ---- New blank preset (sync) ----

@bp.post("/api/presets/new-blank")
def api_preset_new_blank():
    body = request.get_json(silent=True) or {}
    pid = (body.get("id") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    tone = body.get("tone") or ""
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    if not display_name:
        return jsonify({"ok": False, "reason": "display_name required"}), 400
    try:
        from src.genre_extractor.blank_preset import create_blank_preset
        create_blank_preset(pid, display_name=display_name, tone=tone)
    except ValueError as e:
        return jsonify({"ok": False, "reason": str(e)}), 400
    except FileExistsError as e:
        return jsonify({"ok": False, "reason": str(e)}), 409
    return jsonify({"ok": True, "preset_id": pid})


# ---- New preset from description (async) ----

@bp.post("/api/presets/new-from-description")
def api_preset_new_from_description():
    body = request.get_json(silent=True) or {}
    pid = (body.get("id") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    tone = body.get("tone") or ""
    description = (body.get("description") or "").strip()
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    if not display_name:
        return jsonify({"ok": False, "reason": "display_name required"}), 400
    if not description:
        return jsonify({"ok": False, "reason": "description required"}), 400
    if _preset_dir(pid).exists():
        return jsonify({"ok": False, "reason": "preset already exists"}), 409

    with _PRESET_JOB_LOCK:
        if pid in _PRESET_JOBS and _PRESET_JOBS[pid].get("state") == "running":
            return jsonify({"ok": False, "reason": "job already running"}), 409
        _PRESET_JOBS[pid] = _initial_job_state()

    def worker():
        try:
            from src.genre_extractor import from_description
            from_description.extract_from_description(
                pid,
                display_name=display_name,
                tone=tone,
                description=description,
            )
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid].update({
                    "state": "done", "error": None,
                    "phase": "done", "updated_at": time.time(),
                })
        except Exception as e:
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid].update({
                    "state": "failed", "error": str(e),
                    "updated_at": time.time(),
                })

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"ok": True, "preset_id": pid, "state": "running"}), 202


@bp.get("/api/presets/<pid>/status")
def api_preset_status(pid: str):
    """Poll the background extraction job. Unknown pid → state='unknown'.

    Returns 200 in all cases so the UI has a stable polling contract.
    """
    with _PRESET_JOB_LOCK:
        job = _PRESET_JOBS.get(pid)
    if job is None:
        return jsonify({"state": "unknown", "preset_id": pid})
    return jsonify({**job, "preset_id": pid})


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
