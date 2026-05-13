"""Project management routes.

Covers:
  * /api/projects            — list with active flag
  * /api/projects/activate   — switch active book (bootstrap)
  * /api/projects/new        — 4-step wizard (sync or async via extract)
  * /api/projects/<pid>/extract-genre{,/progress,/abort}
  * /api/projects/<pid>/draft-outline, /draft-characters
  * /api/project-files        — edit project.yaml / outline.json / etc.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from src import config

from web._shared import (
    PHASE_TOTAL,
    READONLY_MODE,
    _PROJECT_EDITABLE,
    _PROJECT_JOB_LOCK,
    _PROJECT_JOBS,
    _initial_job_state,
    _make_phase_cb,
    _run_lock,
)

bp = Blueprint("projects", __name__)


@bp.get("/api/projects")
def api_projects():
    from src import bootstrap
    import yaml
    active = config.get_active_project_id()
    out = []
    for pid in bootstrap.list_projects():
        pyaml_path = config.PROJECTS_DIR / pid / "project.yaml"
        try:
            pyaml = yaml.safe_load(pyaml_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            pyaml = {}
        out.append({
            "id": pid,
            "genre": pyaml.get("genre"),
            "display_name": pyaml.get("display_name", pid),
            "has_state": (config.PROJECTS_DIR / pid / "state").exists(),
            "is_active": (pid == active),
        })
    return jsonify({"active": active, "projects": out})


@bp.post("/api/projects/activate")
def api_project_activate():
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    data = request.get_json(silent=True) or {}
    pid = (data.get("id") or "").strip()
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    # Refuse if pipeline is running to avoid state mid-flight swap
    if not _run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "reason": "pipeline running; try abort first"}), 409
    try:
        from src import bootstrap
        try:
            result = bootstrap.bootstrap_project(pid)
        except (FileNotFoundError, ValueError) as e:
            return jsonify({"ok": False, "reason": str(e)}), 400
        return jsonify({
            "ok": True,
            "active": result.project_id,
            "source_preset": result.source_preset,
            "copied_files": result.copied_files,
        })
    finally:
        _run_lock.release()


@bp.post("/api/projects/new")
def api_project_new():
    """4-step wizard: name → genre → outline → characters.

    Required fields:
      id, display_name, protagonist_name, chapter_count_target

    Genre source (exactly one must be indicated):
      from_preset=<id>  |  blank_genre=True  |  from_extract={sources, with_trial}

    Outline source (exactly one):
      outline_synopsis=<str> (LLM drafts)  |  blank_outline=True

    Characters source (exactly one):
      characters_brief=<str> (LLM drafts)  |  blank_characters=True

    When from_extract is provided, skeleton project is created synchronously
    and the genre extraction runs in a background thread (returns 202).
    Otherwise synchronous create_project + bootstrap_project (returns 200).
    """
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    body = request.get_json(silent=True) or {}

    # Validate required scalar fields up-front — create_project's own checks
    # would raise ValueError too, but doing it here gives crisper messages
    # and avoids creating an aborted on-disk skeleton for trivial mistakes.
    required = ("id", "display_name", "protagonist_name", "chapter_count_target")
    for f in required:
        if body.get(f) is None or body.get(f) == "":
            return jsonify({"ok": False, "reason": f"{f} required"}), 400

    pid = body["id"]
    from_extract = body.get("from_extract")

    # Async path: from_extract with non-empty sources.
    # Strategy: create the project skeleton with blank genre stubs right
    # now (so the project appears in /api/projects immediately), then kick
    # off genre extraction in a background thread. The extractor
    # (to_project.extract_to_project) overwrites the blank stubs in place.
    if from_extract and from_extract.get("sources"):
        try:
            from src.bootstrap import create_project
            create_project(
                pid,
                display_name=body["display_name"],
                protagonist_name=body["protagonist_name"],
                chapter_count_target=int(body["chapter_count_target"]),
                blank_genre=True,
                blank_outline=bool(body.get("blank_outline", False)),
                outline_synopsis=body.get("outline_synopsis"),
                blank_characters=bool(body.get("blank_characters", False)),
                characters_brief=body.get("characters_brief"),
            )
        except FileExistsError as e:
            return jsonify({"ok": False, "reason": str(e)}), 409
        except ValueError as e:
            return jsonify({"ok": False, "reason": str(e)}), 400
        except FileNotFoundError as e:
            return jsonify({"ok": False, "reason": str(e)}), 404

        with _PROJECT_JOB_LOCK:
            _PROJECT_JOBS[pid] = _initial_job_state()

        sources = list(from_extract["sources"])
        with_trial = bool(from_extract.get("with_trial", False))

        def _worker():
            try:
                # Import lazily so tests can monkeypatch the module attr.
                from src.genre_extractor import to_project as to_proj
                to_proj.extract_to_project(
                    pid, sources=sources, with_trial=with_trial,
                    on_phase=_make_phase_cb(_PROJECT_JOBS, _PROJECT_JOB_LOCK, pid),
                )
                with _PROJECT_JOB_LOCK:
                    _PROJECT_JOBS[pid].update({
                        "state": "done", "error": None,
                        "phase": "done", "updated_at": time.time(),
                    })
            except Exception as e:
                with _PROJECT_JOB_LOCK:
                    _PROJECT_JOBS[pid].update({
                        "state": "failed", "error": str(e),
                        "updated_at": time.time(),
                    })

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except BaseException:
            with _PROJECT_JOB_LOCK:
                _PROJECT_JOBS[pid] = {
                    "state": "failed", "error": "thread spawn failed",
                    "phase": None, "phase_index": None, "phase_total": PHASE_TOTAL,
                    "progress": None, "started_at": time.time(),
                    "updated_at": time.time(),
                }
            raise
        return jsonify({"ok": True, "project_id": pid, "state": "extracting"}), 202

    # Sync path: create skeleton + bootstrap into state/.
    try:
        from src.bootstrap import bootstrap_project, create_project
        create_project(
            pid,
            display_name=body["display_name"],
            protagonist_name=body["protagonist_name"],
            chapter_count_target=int(body["chapter_count_target"]),
            from_preset=body.get("from_preset"),
            blank_genre=bool(body.get("blank_genre", False)),
            outline_synopsis=body.get("outline_synopsis"),
            blank_outline=bool(body.get("blank_outline", False)),
            characters_brief=body.get("characters_brief"),
            blank_characters=bool(body.get("blank_characters", False)),
            overwrite=bool(body.get("overwrite", False)),
        )
        bootstrap_project(pid)
    except ValueError as e:
        return jsonify({"ok": False, "reason": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"ok": False, "reason": str(e)}), 404
    except FileExistsError as e:
        return jsonify({"ok": False, "reason": str(e)}), 409
    return jsonify({"ok": True, "project_id": pid})


@bp.get("/api/projects/<pid>/extract-genre/progress")
def api_project_extract_progress(pid: str):
    """Poll the per-project extract-genre job. Unknown pid → state='unknown'.

    Stable 200 in all cases so the UI has a consistent polling contract
    (same shape as /api/presets/<pid>/status).
    """
    with _PROJECT_JOB_LOCK:
        job = _PROJECT_JOBS.get(pid)
    if job is None:
        return jsonify({"state": "unknown", "project_id": pid})
    return jsonify({**job, "project_id": pid})


@bp.post("/api/projects/<pid>/extract-genre")
def api_project_extract_genre(pid: str):
    """Post-creation 'overwrite genre config' — re-run extraction into an
    existing book, rewriting its state/era.md + style/laws files in place.

    Async: validates synchronously, then spawns a daemon thread running
    to_project.extract_to_project. If the book is currently the active
    project, the worker also re-bootstraps so state/ picks up the new
    genre files immediately. Caller polls /extract-genre/progress.
    """
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    project_dir = config.PROJECTS_DIR / pid
    if not project_dir.exists():
        return jsonify({"ok": False, "reason": "project not found"}), 404
    body = request.get_json(silent=True) or {}
    sources = body.get("sources") or []
    if not sources:
        return jsonify({"ok": False, "reason": "sources required"}), 400
    with_trial = bool(body.get("with_trial", False))

    with _PROJECT_JOB_LOCK:
        if pid in _PROJECT_JOBS and _PROJECT_JOBS[pid].get("state") == "running":
            return jsonify({"ok": False, "reason": "job already running"}), 409
        _PROJECT_JOBS[pid] = _initial_job_state()

    def _worker():
        try:
            # Import lazily so tests can monkeypatch the module attr.
            from src.genre_extractor import to_project
            to_project.extract_to_project(
                pid, sources=sources, with_trial=with_trial,
                on_phase=_make_phase_cb(_PROJECT_JOBS, _PROJECT_JOB_LOCK, pid),
            )
            if config.get_active_project_id() == pid:
                from src import bootstrap
                bootstrap.bootstrap_project(pid, preserve_progress=True)
            with _PROJECT_JOB_LOCK:
                _PROJECT_JOBS[pid].update({
                    "state": "done", "error": None,
                    "phase": "done", "updated_at": time.time(),
                })
        except Exception as e:
            with _PROJECT_JOB_LOCK:
                _PROJECT_JOBS[pid].update({
                    "state": "failed", "error": str(e),
                    "updated_at": time.time(),
                })

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except BaseException:
        with _PROJECT_JOB_LOCK:
            _PROJECT_JOBS[pid] = {
                "state": "failed", "error": "thread spawn failed",
                "phase": None, "phase_index": None, "phase_total": PHASE_TOTAL,
                "progress": None, "started_at": time.time(),
                "updated_at": time.time(),
            }
        raise
    return jsonify({"ok": True, "state": "running"}), 202


@bp.post("/api/projects/<pid>/extract-genre/abort")
def api_project_extract_abort(pid: str):
    """Soft abort: flip job state so UI stops polling. Extraction may still
    complete in the background thread (cooperative cancellation not plumbed
    through Blackboard yet)."""
    with _PROJECT_JOB_LOCK:
        if pid in _PROJECT_JOBS:
            _PROJECT_JOBS[pid].update({
                "state": "aborted", "error": None,
                "updated_at": time.time(),
            })
    return jsonify({"ok": True})


@bp.post("/api/projects/<pid>/draft-outline")
def api_project_draft_outline(pid: str):
    """Regenerate outline.json from a synopsis via OutlineDrafter LLM call.

    Delegates to pipeline.run_draft_outline, which persists the new
    outline.json under projects/<pid>/ and re-bootstraps state/ if this
    project is currently active.
    """
    if not (config.PROJECTS_DIR / pid).exists():
        return jsonify({"ok": False, "reason": "project not found"}), 404
    body = request.get_json(silent=True) or {}
    synopsis = body.get("synopsis", "")
    from src.pipeline import run_draft_outline
    try:
        out = run_draft_outline(pid, synopsis=synopsis)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "reason": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "reason": str(e)}), 500
    return jsonify(out)


@bp.post("/api/projects/<pid>/draft-characters")
def api_project_draft_characters(pid: str):
    """Regenerate characters.yaml from a brief via CharactersDrafter LLM call.

    Delegates to pipeline.run_draft_characters, which persists the new
    characters.yaml under projects/<pid>/ and re-bootstraps state/ if this
    project is currently active.
    """
    if not (config.PROJECTS_DIR / pid).exists():
        return jsonify({"ok": False, "reason": "project not found"}), 404
    body = request.get_json(silent=True) or {}
    brief = body.get("brief", "")
    from src.pipeline import run_draft_characters
    try:
        out = run_draft_characters(pid, brief=brief)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "reason": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "reason": str(e)}), 500
    return jsonify(out)


# ---------- project file editing ----------

def _active_project_path(name: str) -> Path:
    """Resolve a file in the currently active project's source dir.

    Enforces the whitelist at the single boundary so callers can't smuggle
    arbitrary paths. Raises Flask 400/409 as appropriate.
    """
    if name not in _PROJECT_EDITABLE:
        abort(400, f"name must be one of {sorted(_PROJECT_EDITABLE)}")
    pid = config.get_active_project_id()
    if not pid:
        abort(409, "no active project")
    return config.PROJECTS_DIR / pid / name


@bp.get("/api/project-files")
def api_project_file_get():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "name query parameter required"}), 400
    path = _active_project_path(name)
    if not path.exists():
        return jsonify({"ok": False, "reason": f"{name} not found in active project"}), 404
    return jsonify({
        "name": name,
        "content": path.read_text(encoding="utf-8"),
        "mtime": path.stat().st_mtime,
    })


@bp.put("/api/project-files")
def api_project_file_put():
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if "content" not in data:
        return jsonify({"ok": False, "reason": "content required"}), 400
    content = data["content"]
    if not isinstance(content, str):
        return jsonify({"ok": False, "reason": "content must be string"}), 400
    path = _active_project_path(name)

    # Atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)

    # Re-seed state/ so agents see the new content on next run.
    # preserve_progress=True — the user is editing source, not starting over.
    from src import bootstrap
    pid: str = config.get_active_project_id()  # type: ignore[assignment] — _active_project_path already validated
    try:
        bootstrap.bootstrap_project(pid, preserve_progress=True)
    except (FileNotFoundError, ValueError) as e:
        return jsonify({"ok": False, "reason": f"re-seed failed: {e}"}), 400
    return jsonify({"ok": True, "name": name, "re_seeded": True})
