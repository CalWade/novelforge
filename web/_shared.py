"""Cross-blueprint shared state and helpers for the web demo.

Lives here (not in web/app.py) so blueprint modules can import from a
neutral place without creating a circular import back to the app factory.

Contents — all mutable state used by more than one blueprint:

  * ``_run_lock`` — single-slot lock guarding /api/run, /api/audit and any
    route that must refuse concurrent pipeline runs (e.g. project activate).
  * ``_TARGET_LOCKS`` / ``acquire_target_lock`` — per-target (preset|project
    id) mutex used by the /api/jobs blueprint to refuse concurrent extract
    jobs writing to the same directory.
  * ``READONLY_MODE`` — env-driven kill switch for mutating routes.
  * ``NOVELS_DIR`` — module attribute (not function) so tests can
    monkeypatch it to tmp_path; matches the PRESETS_DIR pattern.
  * ``_ALLOWED_FILES`` / ``_PROJECT_EDITABLE`` — sandbox whitelists.

None of these are ever imported back by web/app.py's factory code so the
direction of dependency is always leaf → shared (no cycles).

Legacy removed (2026-05-13): ``_PRESET_JOBS`` / ``_PROJECT_JOBS`` /
``_make_phase_cb`` / ``_initial_job_state`` / ``_PHASES`` / ``PHASE_TOTAL``.
All superseded by the unified :mod:`src.jobs` system (JobStore + JobLogger +
CancelToken) consumed via the /api/jobs blueprint (``web/routes/jobs.py``).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from src import config

# ---------- readonly kill switch ----------
# READONLY_MODE=1 disables /api/run and /api/audit. For hosted demos where
# we don't want evaluators to burn LLM budget or trigger concurrent runs.
READONLY_MODE: bool = os.environ.get("READONLY_MODE", "0") == "1"

# ---------- shared run-lock ----------
_run_lock = threading.Lock()

# ---------- per-target job mutex ----------
# The /api/jobs blueprint refuses to spawn a second job for the same
# (target_type, target_id). This keeps two concurrent extract jobs from
# both writing into, say, ``projects/xianxia/state/.extract_build/``.
# Different targets are fully parallel — this dict is keyed per-target,
# not global.
_TARGET_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_TARGET_LOCKS_META = threading.Lock()


def acquire_target_lock(target_type: str, target_id: str) -> threading.Lock | None:
    """Try (non-blocking) to claim the per-target lock.

    Returns the Lock on success (caller must release when worker exits),
    None if another worker already holds it.
    """
    key = (target_type, target_id)
    with _TARGET_LOCKS_META:
        lock = _TARGET_LOCKS.setdefault(key, threading.Lock())
    if lock.acquire(blocking=False):
        return lock
    return None


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
