"""Flask web demo for the Novelforge — application factory.

Exists purely to make the architecture visible to humans in real time:
  - Left: the state/ filesystem as the single source of truth
  - Center: the artifact under inspection (chapter, debt, rules, agents.md)
  - Right: the Prompt Inspector — every LLM call, fresh-context, agent-colored

Every API handler is intentionally small; all heavy lifting lives in src/.

This module is the thin factory: it instantiates Flask, registers the
per-concern blueprints from ``web/routes/*``, and wires global error
handlers so every 4xx returns the same ``{ok:false, reason:...}`` envelope.

Shared mutable state (run-lock, job dicts, sandbox constants) lives in
``web/_shared.py`` — blueprint modules import from there to avoid a
circular import back to this factory. The names are RE-EXPORTED on this
module so existing tests that reach into ``web_app._PROJECT_JOB_LOCK`` or
monkeypatch ``web_app.NOVELS_DIR`` keep working unchanged.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify

from web._shared import (
    NOVEL_MAX_BYTES,
    NOVELS_DIR,
    READONLY_MODE,
    _ALLOWED_FILES,
    _PRESET_JOB_LOCK,
    _PRESET_JOBS,
    _PROJECT_EDITABLE,
    _PROJECT_JOB_LOCK,
    _PROJECT_JOBS,
    PHASE_TOTAL,
    _initial_job_state,
    _make_phase_cb,
    _run_lock,
)
from web.routes import env as env_routes
from web.routes import novels as novels_routes
from web.routes import presets as presets_routes
from web.routes import projects as projects_routes
from web.routes import runner as runner_routes

# Re-exports kept for test access (tests reach web_app._PROJECT_JOB_LOCK etc.)
# and for legacy callers that imported these off web.app directly.
__all__ = [
    "app",
    "NOVELS_DIR", "NOVEL_MAX_BYTES", "READONLY_MODE",
    "_ALLOWED_FILES", "_PROJECT_EDITABLE",
    "_PRESET_JOB_LOCK", "_PRESET_JOBS",
    "_PROJECT_JOB_LOCK", "_PROJECT_JOBS",
    "PHASE_TOTAL", "_initial_job_state", "_make_phase_cb",
    "_run_lock",
]

app = Flask(__name__, static_folder="static", template_folder="templates")

# Accept one Flask request up to 200MB — roughly 4 × 50MB novels at once.
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

# Register per-concern blueprints. Order doesn't matter: no blueprint
# imports another, and route names are globally unique (Flask will shout
# if we ever create a collision).
app.register_blueprint(presets_routes.bp)
app.register_blueprint(projects_routes.bp)
app.register_blueprint(env_routes.bp)
app.register_blueprint(runner_routes.bp)
app.register_blueprint(novels_routes.bp)


# ---------- errors ----------
# All error responses share the same envelope: {"ok": false, "reason": "..."}.
# This keeps the frontend parser simple and matches the shape that mutating
# routes (POST /api/projects/*, /api/env, PUT /api/project-files) return
# inline. Flask's default HTML error pages would break response.json() in JS.
@app.errorhandler(400)
def _h400(e):
    return jsonify({"ok": False, "reason": str(e)}), 400


@app.errorhandler(403)
def _h403(e):
    return jsonify({"ok": False, "reason": str(e)}), 403


@app.errorhandler(404)
def _h404(e):
    return jsonify({"ok": False, "reason": str(e)}), 404


@app.errorhandler(409)
def _h409(e):
    return jsonify({"ok": False, "reason": str(e)}), 409


if __name__ == "__main__":
    # `flask --app web.app run` is the documented launcher; this is a fallback.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
