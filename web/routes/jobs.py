"""Jobs blueprint: /api/jobs CRUD + abort + log tailing + /jobs /jobs/<id> 页面."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, render_template, request

from src.jobs import (
    GenrePipelineAborted,
    NullCancelToken,
    ThreadEventToken,
    get_job_logger,
    get_store,
    initial_job_record,
    new_job_id,
    read_log_tail,
)
from web._shared import acquire_target_lock


bp = Blueprint("jobs", __name__)

# ---------- API ----------


@bp.get("/api/jobs")
def list_jobs():
    store = get_store()
    state = request.args.get("state")
    kind = request.args.get("kind")
    return jsonify({"jobs": store.list(state=state, kind=kind)})


@bp.post("/api/jobs")
def create_job():
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get("kind")
    target = body.get("target")
    sources = body.get("sources") or []
    params = body.get("params") or {}

    if kind not in ("from-novel", "from-description", "blank", "extract-to-project"):
        return jsonify({"error": "unknown kind"}), 400
    if not isinstance(target, dict) or target.get("type") not in ("preset", "project"):
        return jsonify({"error": "bad target"}), 400

    # Pre-flight: 对于新建 preset 的 kind，如果 target 目录已经存在，
    # 直接 409 拒绝，避免用户提交后才在详情页看到 "Preset already exists"。
    # （extract-to-project 是覆盖语义，允许目录已存在。）
    from src import config
    if kind in ("from-novel", "from-description", "blank"):
        preset_dir = config.PRESETS_DIR / target["id"]
        if preset_dir.exists():
            return jsonify({
                "error": (
                    f"preset '{target['id']}' already exists. "
                    f"先在题材库删除它，或换一个新 id。"
                ),
            }), 409

    # Per-target lock
    lock = acquire_target_lock(target["type"], target["id"])
    if lock is None:
        return jsonify({"error": "another job is already running for this target"}), 409

    store = get_store()
    job_id = new_job_id()
    label = _build_label(kind, target)
    rec = initial_job_record(
        job_id=job_id, kind=kind, target=target,
        label=label, sources=sources, params=params,
    )
    store.create(rec)

    cancel = ThreadEventToken()
    store.set_runtime(job_id, cancel=cancel, target_lock=lock)

    t = threading.Thread(target=_run_worker, args=(job_id,), daemon=True)
    t.start()

    return jsonify({"job_id": job_id}), 201


@bp.get("/api/jobs/<job_id>")
def get_job(job_id):
    rec = get_store().get(job_id)
    if rec is None:
        abort(404)
    return jsonify(rec)


@bp.post("/api/jobs/<job_id>/abort")
def abort_job(job_id):
    store = get_store()
    rec = store.get(job_id)
    if rec is None:
        abort(404)
    if rec["state"] != "running":
        return jsonify({"error": f"cannot abort job in state: {rec['state']}"}), 409
    token: ThreadEventToken | None = store.get_runtime(job_id, "cancel")
    if token is not None:
        token.cancel()
    store.update(job_id, state="aborting")
    return jsonify({"ok": True})


@bp.delete("/api/jobs/<job_id>")
def delete_job(job_id):
    store = get_store()
    try:
        store.delete(job_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"ok": True})


@bp.get("/api/jobs/<job_id>/log")
def job_log(job_id):
    offset = int(request.args.get("offset", 0))
    content, next_off = read_log_tail(job_id, offset)
    return jsonify({"content": content, "next_offset": next_off})


# ---------- 看板 API（复用首页三栏布局的数据源） ----------
# 这三条 API 是为了让首页的 state-tree / viewer / prompt-inspector
# 三栏复用到题材任务。形状与 /api/state + /api/file + /api/prompts
# 对齐，前端只需在 view=genre 时切换 URL 即可，不必维护两套渲染。


def _genre_job_workspace(job_id: str) -> tuple[dict, Path]:
    """Resolve a job's on-disk workspace (preset dir + .build/).

    Returns (job_record, workspace_path). For `from-novel`/`blank`/
    `from-description`, workspace = presets/<id>/; for
    `extract-to-project`, workspace = projects/<id>/state/.extract_build/.
    Raises 404 if job not found.
    """
    from src import config

    rec = get_store().get(job_id)
    if rec is None:
        abort(404, "job not found")
    target = rec["target"]
    if target["type"] == "preset":
        return rec, Path(config.PRESETS_DIR) / target["id"]
    # project: 题材产物落在 state/.extract_build/，但最终 4 份文件回落
    # projects/<id>/（不是 state/，因 to_project 输出到 book_dir）
    return rec, Path(config.PROJECTS_DIR) / target["id"]


@bp.get("/api/genre-state")
def api_genre_state():
    """Snapshot for the genre-view dashboard (mirrors /api/state shape).

    Query: ?job=<job_id>
    Returns: {job, files, counters, progress}
      - job: full JobStore record
      - files: 扁平清单，每项 {path, kind, exists}
      - counters: {issues, debt, prompts_total, genre_prompts}
      - progress: 最终产物 4 份文件是否存在 + .build 里各 phase 产物数量
    """

    job_id = request.args.get("job", "").strip()
    if not job_id:
        return jsonify({"error": "job query param required"}), 400

    rec, workspace = _genre_job_workspace(job_id)
    build_dir = workspace / ".build"
    if rec["target"]["type"] == "project":
        # 作品侧 build 目录路径不同
        build_dir = workspace / "state" / ".extract_build"

    # 最终产物（preset 侧在 workspace；project 侧在 workspace 根）
    final_files = ("era.md", "writing-style-extra.md", "iron-laws-extra.md",
                   "resource_schema.yaml", "genre.yaml")
    files: list[dict] = []
    for fname in final_files:
        p = workspace / fname
        if p.exists():
            files.append({
                "path": f"{fname}",
                "kind": "final",
                "size": p.stat().st_size,
            })

    # .build 里所有文件
    if build_dir.exists():
        for root, _dirs, fnames in sorted(__import__("os").walk(build_dir)):
            root_path = Path(root)
            rel_root = root_path.relative_to(build_dir)
            for fname in sorted(fnames):
                if fname.startswith("."):
                    continue
                rel = (rel_root / fname).as_posix()
                full = root_path / fname
                files.append({
                    "path": f".build/{rel}",
                    "kind": "build",
                    "size": full.stat().st_size,
                })

    # 计数 —— 从 .build 里的 jsonl 读
    def _count_jsonl(name: str) -> int:
        p = build_dir / name
        if not p.exists():
            return 0
        try:
            with p.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    counters = {
        "issues": _count_jsonl("genre_issues.jsonl"),
        "debt": _count_jsonl("genre_debt.jsonl"),
        "batches_done": len([f for f in files if f["path"].startswith(".build/extraction_notes/batch-")]),
        "arcs_done": len([f for f in files if f["path"].startswith(".build/extraction_notes/arcs/")]),
    }

    # 产物进度（给 pills 用）
    progress = {
        "has_era": (workspace / "era.md").exists(),
        "has_style": (workspace / "writing-style-extra.md").exists(),
        "has_laws": (workspace / "iron-laws-extra.md").exists(),
        "has_blueprint": (build_dir / "genre_blueprint.yaml").exists(),
    }

    return jsonify({
        "job": rec,
        "files": files,
        "counters": counters,
        "progress": progress,
        "build_dir": str(build_dir),
        "workspace": str(workspace),
    })


@bp.get("/api/genre-file")
def api_genre_file():
    """Read a file inside a genre job's workspace.

    Query: ?job=<job_id>&path=<relative_path>
    Safe-resolves path relative to the workspace (no traversal).
    """

    job_id = request.args.get("job", "").strip()
    rel = request.args.get("path", "").strip()
    if not job_id or not rel:
        return jsonify({"error": "job and path required"}), 400

    rec, workspace = _genre_job_workspace(job_id)
    build_dir = workspace / ".build"
    if rec["target"]["type"] == "project":
        build_dir = workspace / "state" / ".extract_build"

    # 两个合法根：workspace（最终产物）、build_dir（过程产物）
    candidates = []
    if rel.startswith(".build/"):
        candidates.append((build_dir / rel[len(".build/"):]).resolve())
    else:
        candidates.append((workspace / rel).resolve())

    for cand in candidates:
        # 路径沙箱：必须落在 workspace 内
        try:
            cand.relative_to(workspace.resolve())
        except ValueError:
            continue
        if cand.exists() and cand.is_file():
            try:
                content = cand.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return jsonify({"error": "binary file"}), 415
            return jsonify({
                "path": rel,
                "content": content,
                "size": cand.stat().st_size,
                "mimetype": _guess_genre_mimetype(cand.suffix),
            })
    return jsonify({"error": "not found"}), 404


def _guess_genre_mimetype(suffix: str) -> str:
    return {
        ".md": "text/markdown",
        ".yaml": "text/yaml", ".yml": "text/yaml",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".txt": "text/plain",
    }.get(suffix.lower(), "text/plain")


@bp.get("/api/genre-prompts")
def api_genre_prompts():
    """Filter prompts_log entries by job_id (or by agent_name prefix 'genre_').

    Query: ?job=<job_id>&limit=<N>
    目前 llm.chat() 没记录 job_id，所以我们按 agent_name 前缀过滤
    （genre_extractor / genre_drafter / genre_validator / genre_fixer /
    genre_arc_merger / genre_book_distiller / genre_style_guard /
    genre_consistency_guard / genre_fact_checker / preset_from_description
    等），并按 job.started_at 之后的时间窗裁剪。
    """
    import json
    from src import config

    job_id = request.args.get("job", "").strip()
    limit = max(1, min(int(request.args.get("limit", 200)), 1000))
    if not job_id:
        return jsonify({"error": "job query param required"}), 400

    rec = get_store().get(job_id)
    if rec is None:
        abort(404, "job not found")
    started_at = rec.get("started_at", 0) or 0
    finished_at = rec.get("finished_at")  # None if still running

    # prompts_log.jsonl 在当前 active project 的 state/ 里。若无 active
    # project（例如用户直接从首页用"题材库"入口跑），回落到题材 build 目录
    # 里可能有的独立 log（未来可扩展）。目前只读 state/prompts_log.jsonl。
    log_path = config.STATE_DIR / "prompts_log.jsonl"
    if not log_path.exists():
        return jsonify([])

    genre_prefixes = ("genre_", "preset_from_description")
    rows: list[dict] = []
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 按 agent_name 前缀 + 时间窗口过滤
                agent = row.get("agent_name", "")
                if not any(agent.startswith(p) for p in genre_prefixes):
                    continue
                ts = row.get("ts", 0) or 0
                if ts < started_at:
                    continue
                if finished_at and ts > finished_at + 5:
                    # 5 秒余量，兼容时钟抖动
                    continue
                rows.append(row)
    except OSError:
        return jsonify([])

    rows.reverse()  # newest first
    return jsonify(rows[:limit])


# ---------- 页面 ----------


@bp.get("/jobs")
def page_jobs_list():
    return render_template("jobs/index.html")


@bp.get("/jobs/<job_id>")
def page_jobs_detail(job_id):
    """旧的 4-节点图详情页已被题材看板替代。

    重定向到首页 ?view=genre&job=<id>，复用首页三栏布局。
    """
    from flask import redirect, url_for
    return redirect(f"/?view=genre&job={job_id}")


# ---------- 内部 ----------


def _build_label(kind: str, target: dict) -> str:
    tid = target["id"]
    mapping = {
        "from-novel": f"素材库拆题材 → {tid}",
        "from-description": f"从描述生成题材 → {tid}",
        "blank": f"空壳题材 → {tid}",
        "extract-to-project": f"覆盖作品题材 → {tid}",
    }
    return mapping.get(kind, kind)


def _run_worker(job_id: str) -> None:
    store = get_store()
    rec = store.get(job_id)
    if rec is None:
        return
    logger = get_job_logger(job_id)
    cancel = store.get_runtime(job_id, "cancel") or NullCancelToken()
    target_lock: threading.Lock | None = store.get_runtime(job_id, "target_lock")

    def on_progress(
        *,
        phase: str | None = None,
        phase_index: int | None = None,
        sub_steps: dict | None = None,
        progress_text: str | None = None,
    ) -> None:
        updates: dict[str, Any] = {}
        if phase is not None:
            updates["phase"] = phase
        if phase_index is not None:
            updates["phase_index"] = phase_index
        if sub_steps is not None:
            updates["sub_steps"] = sub_steps
        if progress_text is not None:
            updates["progress_text"] = progress_text
            logger.info(f"[{phase or '-'}] {progress_text}")
        store.update(job_id, **updates)

    try:
        logger.info(f"job started: kind={rec['kind']} target={rec['target']}")
        _dispatch(rec, cancel=cancel, on_progress=on_progress, logger=logger)
        store.finish(job_id, "done")
        logger.info("job finished: done")
    except GenrePipelineAborted:
        store.finish(job_id, "aborted", error="用户中止")
        logger.info("job aborted by user")
    except Exception as e:  # noqa: BLE001
        store.finish(job_id, "failed", error=str(e))
        logger.exception("job failed")
    finally:
        if target_lock is not None:
            try:
                target_lock.release()
            except RuntimeError:
                pass


def _dispatch(rec: dict, *, cancel, on_progress, logger) -> None:
    kind = rec["kind"]
    target = rec["target"]
    params = rec.get("params", {})
    sources = rec.get("sources", [])

    if kind == "blank":
        from src.genre_extractor.blank_preset import create_blank_preset
        create_blank_preset(
            target["id"],
            display_name=params.get("display_name") or target["id"],
            tone=params.get("tone", ""),
            cancel=cancel,
            on_progress=on_progress,
        )
    elif kind == "from-description":
        from src.genre_extractor.from_description import extract_from_description
        extract_from_description(
            target["id"],
            display_name=params.get("display_name") or target["id"],
            tone=params.get("tone", ""),
            description=params.get("description", ""),
            cancel=cancel,
            on_progress=on_progress,
        )
    elif kind == "from-novel":
        from src.genre_extractor.to_preset import extract_to_preset
        extract_to_preset(
            target["id"],
            sources=sources,
            with_trial=bool(params.get("with_trial", False)),
            cancel=cancel,
            on_progress=on_progress,
        )
    elif kind == "extract-to-project":
        from src.genre_extractor.to_project import extract_to_project
        extract_to_project(
            target["id"],
            sources=sources,
            with_trial=bool(params.get("with_trial", False)),
            cancel=cancel,
            on_progress=on_progress,
        )
    else:
        raise ValueError(f"unknown kind: {kind}")
