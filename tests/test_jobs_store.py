"""JobStore：文件落盘 + 内存缓存 + 启动恢复."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def store_env(tmp_path: Path, monkeypatch):
    from src.jobs import store as store_mod
    monkeypatch.setattr(store_mod, "JOBS_DIR", tmp_path / ".jobs")
    # 强制新建 store 实例
    store_mod._STORE_SINGLETON = None
    return tmp_path


def test_create_and_get_job(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    rec = initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p1"}, label="L",
    )
    s.create(rec)
    back = s.get(jid)
    assert back["job_id"] == jid
    assert back["state"] == "running"


def test_persist_roundtrip(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    path = store_env / ".jobs" / "active" / f"{jid}.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["job_id"] == jid


def test_update_writes_to_disk(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    s.update(jid, phase="extract", phase_index=1, progress_text="batch 1/5")
    rec = s.get(jid)
    assert rec["phase"] == "extract"
    assert rec["progress_text"] == "batch 1/5"
    disk = json.loads((store_env / ".jobs" / "active" / f"{jid}.json").read_text())
    assert disk["phase"] == "extract"


def test_finish_moves_to_archive(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    s.finish(jid, "done")
    assert not (store_env / ".jobs" / "active" / f"{jid}.json").exists()
    assert (store_env / ".jobs" / "archive" / f"{jid}.json").exists()
    rec = s.get(jid)
    assert rec["state"] == "done"
    assert rec["finished_at"] is not None


def test_finish_idempotent(store_env):
    """已处于终态的 job 不被覆盖（防止 abort 后 worker 仍然 finish(done)）."""
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    s.finish(jid, "aborted", error="user abort")
    s.finish(jid, "done")  # should be no-op
    rec = s.get(jid)
    assert rec["state"] == "aborted"
    assert rec["error"] == "user abort"


def test_list_filters_by_state(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    j1 = new_job_id()
    j2 = new_job_id()
    s.create(initial_job_record(
        job_id=j1, kind="blank", target={"type": "preset", "id": "a"}, label="A",
    ))
    s.create(initial_job_record(
        job_id=j2, kind="blank", target={"type": "preset", "id": "b"}, label="B",
    ))
    s.finish(j2, "done")
    running = s.list(state="running")
    done = s.list(state="done")
    assert [r["job_id"] for r in running] == [j1]
    assert [r["job_id"] for r in done] == [j2]


def test_delete_rejects_running(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    with pytest.raises(ValueError, match="running"):
        s.delete(jid)


def test_delete_archived_ok(store_env):
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    s = get_store()
    jid = new_job_id()
    s.create(initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    ))
    s.finish(jid, "done")
    s.delete(jid)
    assert s.get(jid) is None


def test_recover_marks_orphans_interrupted(store_env):
    """启动时发现 active/ 里 state=running 的 job，标记为 interrupted."""
    from src.jobs.store import get_store
    from src.jobs.schema import initial_job_record, new_job_id
    import src.jobs.store as store_mod
    jid = new_job_id()
    # 手工写 active 文件，模拟进程崩溃
    active = store_env / ".jobs" / "active"
    active.mkdir(parents=True)
    rec = initial_job_record(
        job_id=jid, kind="blank", target={"type": "preset", "id": "p"}, label="L",
    )
    (active / f"{jid}.json").write_text(json.dumps(rec))
    # 重置 singleton，触发 recover
    store_mod._STORE_SINGLETON = None
    s = get_store()
    s.recover()
    rec2 = s.get(jid)
    assert rec2["state"] == "interrupted"
    assert "进程重启" in rec2["error"]
    assert not (active / f"{jid}.json").exists()
