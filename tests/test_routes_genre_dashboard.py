"""genre 看板 3 个 API：genre-state / genre-file / genre-prompts."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    from src import config
    from src.jobs import store as store_mod
    from src.jobs import logger as logger_mod
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(store_mod, "JOBS_DIR", tmp_path / ".jobs")
    monkeypatch.setattr(logger_mod, "LOGS_DIR", tmp_path / ".jobs" / "logs")
    (tmp_path / "presets").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "state").mkdir()
    store_mod._STORE_SINGLETON = None
    logger_mod._LOGGERS.clear()
    from web.app import app as flask_app
    flask_app.config["TESTING"] = True
    yield flask_app


def _mk_job(app, preset_id: str = "p1") -> str:
    """手工建一个 done 状态的 job record（跳过 worker）."""
    from src.jobs import get_store, initial_job_record, new_job_id
    jid = new_job_id()
    rec = initial_job_record(
        job_id=jid, kind="from-novel",
        target={"type": "preset", "id": preset_id},
        label=f"test → {preset_id}",
    )
    rec["started_at"] = time.time() - 60  # 1 分钟前开始
    rec["state"] = "running"  # 保持 running 以便 prompts 过滤不被 finished_at 截断
    get_store().create(rec)
    return jid


def test_genre_state_missing_job_400_vs_404(app):
    client = app.test_client()
    assert client.get("/api/genre-state").status_code == 400
    assert client.get("/api/genre-state?job=nonexistent").status_code == 404


def test_genre_state_returns_files_from_workspace(app, tmp_path):
    jid = _mk_job(app, "p-state")
    preset_dir = tmp_path / "presets" / "p-state"
    preset_dir.mkdir()
    (preset_dir / "era.md").write_text("era content", encoding="utf-8")
    (preset_dir / ".build").mkdir()
    (preset_dir / ".build" / "extraction_notes").mkdir()
    (preset_dir / ".build" / "extraction_notes" / "batch-001.yaml").write_text("a: 1")
    (preset_dir / ".build" / "extraction_notes" / "batch-002.yaml").write_text("b: 2")

    client = app.test_client()
    r = client.get(f"/api/genre-state?job={jid}")
    assert r.status_code == 200
    data = r.get_json()
    paths = [f["path"] for f in data["files"]]
    assert "era.md" in paths
    assert ".build/extraction_notes/batch-001.yaml" in paths
    assert ".build/extraction_notes/batch-002.yaml" in paths
    assert data["counters"]["batches_done"] == 2
    assert data["progress"]["has_era"] is True
    assert data["progress"]["has_blueprint"] is False


def test_genre_file_reads_final_artifact(app, tmp_path):
    jid = _mk_job(app, "p-read")
    preset_dir = tmp_path / "presets" / "p-read"
    preset_dir.mkdir()
    (preset_dir / "era.md").write_text("# 时代\nhello", encoding="utf-8")

    client = app.test_client()
    r = client.get(f"/api/genre-file?job={jid}&path=era.md")
    assert r.status_code == 200
    assert "hello" in r.get_json()["content"]


def test_genre_file_reads_build_artifact(app, tmp_path):
    jid = _mk_job(app, "p-build")
    preset_dir = tmp_path / "presets" / "p-build"
    (preset_dir / ".build" / "extraction_notes").mkdir(parents=True)
    (preset_dir / ".build" / "extraction_notes" / "batch-001.yaml").write_text("xyz: ok")

    client = app.test_client()
    r = client.get(f"/api/genre-file?job={jid}&path=.build/extraction_notes/batch-001.yaml")
    assert r.status_code == 200
    assert "xyz" in r.get_json()["content"]


def test_genre_file_path_traversal_blocked(app, tmp_path):
    jid = _mk_job(app, "p-safe")
    (tmp_path / "presets" / "p-safe").mkdir()
    (tmp_path / "secret.txt").write_text("secret!", encoding="utf-8")

    client = app.test_client()
    r = client.get(f"/api/genre-file?job={jid}&path=../../secret.txt")
    assert r.status_code == 404


def test_genre_prompts_filters_by_agent_prefix(app, tmp_path):
    jid = _mk_job(app, "p-prom")
    log = tmp_path / "state" / "prompts_log.jsonl"
    now = time.time()
    entries = [
        {"agent_name": "generator", "ts": now, "output": "chap"},
        {"agent_name": "genre_extractor", "ts": now, "output": "batch note"},
        {"agent_name": "genre_drafter", "ts": now, "output": "draft"},
        {"agent_name": "preset_from_description", "ts": now, "output": "desc"},
        {"agent_name": "evaluator", "ts": now, "output": "verdict"},
    ]
    log.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n", encoding="utf-8")

    client = app.test_client()
    r = client.get(f"/api/genre-prompts?job={jid}")
    assert r.status_code == 200
    rows = r.get_json()
    names = {row["agent_name"] for row in rows}
    assert names == {"genre_extractor", "genre_drafter", "preset_from_description"}


def test_genre_prompts_respects_job_time_window(app, tmp_path):
    """早于 job started_at 的记录不应被返回."""
    jid = _mk_job(app, "p-win")
    log = tmp_path / "state" / "prompts_log.jsonl"
    now = time.time()
    entries = [
        {"agent_name": "genre_extractor", "ts": now - 120, "output": "old"},  # 早于 started_at=now-60
        {"agent_name": "genre_extractor", "ts": now - 30, "output": "new"},    # 晚于 started_at
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    client = app.test_client()
    rows = client.get(f"/api/genre-prompts?job={jid}").get_json()
    outputs = [r["output"] for r in rows]
    assert outputs == ["new"]  # 只有新的


def test_legacy_jobs_detail_redirects_to_new_view(app):
    jid = _mk_job(app, "p-redir")
    client = app.test_client()
    r = client.get(f"/jobs/{jid}")
    assert r.status_code in (301, 302)
    assert r.headers["Location"] == f"/?view=genre&job={jid}"
