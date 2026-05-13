"""Cross-blueprint shared state and helpers for the web demo.

Lives here (not in web/app.py) so blueprint modules can import from a
neutral place without creating a circular import back to the app factory.

Contents — all mutable state used by more than one blueprint:

  * ``_run_lock`` — single-slot lock guarding /api/run, /api/audit and any
    route that must refuse concurrent pipeline runs (e.g. project activate).
  * ``_PRESET_JOBS`` / ``_PRESET_JOB_LOCK`` — in-memory status map for
    /api/presets/new-from-novel + /api/presets/new-from-description workers.
  * ``_PROJECT_JOBS`` / ``_PROJECT_JOB_LOCK`` — same shape, but keyed by
    project id for the /api/projects/new (async path) and
    /api/projects/<pid>/extract-genre workers.
  * ``_PHASES`` / ``PHASE_TOTAL`` — the 4-bar timeline the UI paints.
  * ``_initial_job_state`` / ``_make_phase_cb`` — helpers that manipulate
    those dicts; shared so preset and project workers use identical
    polling contracts.
  * ``READONLY_MODE`` — env-driven kill switch for mutating routes.
  * ``NOVELS_DIR`` — module attribute (not function) so tests can
    monkeypatch it to tmp_path; matches the PRESETS_DIR pattern.
  * ``_ALLOWED_FILES`` / ``_PROJECT_EDITABLE`` — sandbox whitelists.

None of these are ever imported back by web/app.py's factory code so the
direction of dependency is always leaf → shared (no cycles).
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from src import config

# ---------- readonly kill switch ----------
# READONLY_MODE=1 disables /api/run and /api/audit. For hosted demos where
# we don't want evaluators to burn LLM budget or trigger concurrent runs.
READONLY_MODE: bool = os.environ.get("READONLY_MODE", "0") == "1"

# ---------- shared run-lock ----------
_run_lock = threading.Lock()

# ---------- novels / material library config ----------
# novels/ holds user-uploaded source material for genre extraction. The
# directory is in .gitignore (only the README is whitelisted) and we keep a
# single flat layout — no subdirs, no symlinks, no hidden files.
#
# NOVELS_DIR is a module attribute (not a function) so tests can monkeypatch
# it to tmp_path, matching the pattern we use for PRESETS_DIR.
NOVELS_DIR: Path = config.PROJECT_ROOT / "novels"
# Max bytes per uploaded file. The overall Flask MAX_CONTENT_LENGTH is set
# higher (so multi-file uploads work) and per-file enforcement happens in
# the route handler.
NOVEL_MAX_BYTES: int = 50 * 1024 * 1024  # 50MB

# ---------- path sandbox ----------
# Only these locations are legible to the browser.
#
# STATE_DIR is dynamic: after bootstrap it points to projects/<id>/state/.
# We also allow requests of the form "state/..." to map to that directory
# (so Web UI code and existing docs can keep talking about state/ paths
# regardless of which project is active).
# Allowed roots are resolved at call time via _allowed_roots() so they
# track the current STATE_DIR (including after project switches).
_ALLOWED_FILES = (config.PROJECT_ROOT.resolve() / "AGENTS.md",)  # still static

# ---------- preset / project management ----------
BUILTIN_PRESETS = frozenset({
    "gangster-hk-1983",
    "xianxia-ascension",
    "urban-romance-contemporary",
})

# Whitelist of per-project files users may edit via /api/project-files.
_PROJECT_EDITABLE = {"project.yaml", "outline.json", "characters.yaml", "timeline.yaml"}

# ---- preset extraction jobs ----
# Maps preset_id → full job dict:
#   {"state": "running|done|failed|aborted|unknown",
#    "error": str|None,
#    "phase": "extract"|"merge"|"draft"|"validate"|"done"|None,
#    "phase_index": int|None,   # 1..PHASE_TOTAL (or None before first phase)
#    "phase_total": int|None,   # always PHASE_TOTAL (4) once the job starts
#    "progress": str|None,      # optional fine-grained detail, e.g. "batch 3/12"
#    "started_at": float|None,
#    "updated_at": float|None}
# In-memory is fine: a crash mid-extraction should re-run fresh anyway,
# and the preset filesystem is the real source of truth for "was it built".
_PRESET_JOBS: dict[str, dict] = {}
_PRESET_JOB_LOCK = threading.Lock()

# Track per-book extract-genre jobs (4-step wizard async path + Task 4.4).
# Same in-memory pattern as _PRESET_JOBS: filesystem is the real source of
# truth for "did it finish", this dict is just for live UI polling.
_PROJECT_JOBS: dict[str, dict] = {}
_PROJECT_JOB_LOCK = threading.Lock()

# The 4-bar timeline the UI paints. Order matters — index lookups power
# phase_index. "done" is a terminal marker (never returned to the UI as a
# stage to highlight; we use state='done' for that).
_PHASES: tuple[str, ...] = ("extract", "merge", "draft", "validate")
PHASE_TOTAL: int = len(_PHASES)


def _initial_job_state() -> dict:
    """Fresh running-job record with phase fields primed to phase 1.

    Used by both preset and project extraction jobs so the polling contract
    is identical on both sides.
    """
    now = time.time()
    return {
        "state": "running",
        "error": None,
        "phase": _PHASES[0],
        "phase_index": 1,
        "phase_total": PHASE_TOTAL,
        "progress": None,
        "started_at": now,
        "updated_at": now,
    }


def _make_phase_cb(jobs: dict[str, dict], lock: threading.Lock, key: str):
    """Return a callback the extractor can invoke as ``cb(phase, progress)``.

    The returned closure mutates ``jobs[key]`` under ``lock`` to bump the
    phase / phase_index / progress / updated_at fields. Unknown phase names
    (shouldn't happen, but cheap defense) get ignored — we don't want a
    typo in core.py to flip phase_index to -1.

    Rationale for callback-over-globals: each job key (preset_id or
    project_id) has its OWN bucket in its OWN dict, so a naive
    "update the current job" global would race with concurrent extractions.
    The callback carries its identity by closure, which is the minimum
    state needed and therefore the easiest to reason about.
    """
    def _cb(phase: str, progress: str | None = None) -> None:
        with lock:
            job = jobs.get(key)
            if job is None:
                return
            if phase == "done":
                # Terminal marker — leave state alone (the worker writes
                # "done"/"failed" on its own), just bump updated_at so the
                # UI sees activity.
                job["updated_at"] = time.time()
                return
            if phase in _PHASES:
                job["phase"] = phase
                job["phase_index"] = _PHASES.index(phase) + 1
                job["phase_total"] = PHASE_TOTAL
            job["progress"] = progress
            job["updated_at"] = time.time()
    return _cb
