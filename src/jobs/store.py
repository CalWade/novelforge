"""JobStore：每个 job 一个 JSON 文件，atomic write，内存缓存 active 的。

目录结构：
    .jobs/
      active/<job_id>.json
      archive/<job_id>.json
      logs/<job_id>.log    (由 JobLogger 管理)

线程安全：所有 pub 方法拿 `_lock`（RLock）。
进程隔离：不做（单 worker 约束，见 README）。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from src import config
from src.jobs.schema import TERMINAL_STATES

JOBS_DIR = config.PROJECT_ROOT / ".jobs"

_STORE_SINGLETON: "JobStore | None" = None
_SINGLETON_LOCK = threading.Lock()


def get_store() -> "JobStore":
    global _STORE_SINGLETON
    with _SINGLETON_LOCK:
        if _STORE_SINGLETON is None:
            _STORE_SINGLETON = JobStore(JOBS_DIR)
        return _STORE_SINGLETON


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._active = root / "active"
        self._archive = root / "archive"
        self._logs = root / "logs"
        for d in (self._active, self._archive, self._logs):
            d.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}
        self._runtime: dict[str, dict] = {}  # 非序列化字段：cancel token / target lock
        self._lock = threading.RLock()
        # 启动时懒加载 active
        for p in self._active.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                self._cache[rec["job_id"]] = rec
            except (json.JSONDecodeError, KeyError, OSError):
                continue

    # ---------- CRUD ----------

    def create(self, rec: dict) -> None:
        with self._lock:
            jid = rec["job_id"]
            self._cache[jid] = rec
            self._write_active(rec)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            if job_id in self._cache:
                return dict(self._cache[job_id])
            # 尝试 archive 懒加载
            p = self._archive / f"{job_id}.json"
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    return None
            return None

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id not in self._cache:
                return
            rec = self._cache[job_id]
            if rec["state"] in TERMINAL_STATES:
                return  # 不覆盖终态
            # sub_steps 做 merge 而不是替换
            if "sub_steps" in fields:
                merged = {**rec.get("sub_steps", {}), **fields.pop("sub_steps")}
                rec["sub_steps"] = merged
            rec.update(fields)
            rec["updated_at"] = time.time()
            self._write_active(rec)

    def finish(self, job_id: str, state: str, *, error: str | None = None) -> None:
        with self._lock:
            if job_id not in self._cache:
                return
            rec = self._cache[job_id]
            if rec["state"] in TERMINAL_STATES:
                return  # idempotent
            rec["state"] = state
            rec["error"] = error
            rec["finished_at"] = time.time()
            rec["updated_at"] = rec["finished_at"]
            # archive
            self._write_archive(rec)
            self._remove_active(job_id)
            # 保留内存缓存（方便详情页 fallback）
            # 但移除 runtime
            self._runtime.pop(job_id, None)

    def delete(self, job_id: str) -> None:
        with self._lock:
            rec = self.get(job_id)
            if rec is None:
                return
            if rec["state"] not in TERMINAL_STATES:
                raise ValueError(f"cannot delete job in state: {rec['state']} (still running)")
            self._cache.pop(job_id, None)
            ap = self._archive / f"{job_id}.json"
            if ap.exists():
                ap.unlink()
            lp = self._logs / f"{job_id}.log"
            if lp.exists():
                lp.unlink()
            # 顺手清 rotate 过的
            for p in self._logs.glob(f"{job_id}.log.*"):
                p.unlink(missing_ok=True)

    def list(self, *, state: str | None = None, kind: str | None = None) -> list[dict]:
        with self._lock:
            out: list[dict] = list(self._cache.values())
            # 懒加载 archive
            for p in self._archive.glob("*.json"):
                jid = p.stem
                if jid in self._cache:
                    continue
                try:
                    out.append(json.loads(p.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    continue
            if state:
                out = [r for r in out if r.get("state") == state]
            if kind:
                out = [r for r in out if r.get("kind") == kind]
            out.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
            return out

    # ---------- 运行时（不序列化） ----------

    def set_runtime(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            self._runtime.setdefault(job_id, {}).update(fields)

    def get_runtime(self, job_id: str, key: str) -> Any:
        with self._lock:
            return self._runtime.get(job_id, {}).get(key)

    # ---------- 启动恢复 ----------

    def recover(self) -> list[str]:
        """启动时把 active 里 state ∈ {running,aborting} 的 job 全部标为 interrupted."""
        recovered: list[str] = []
        with self._lock:
            for jid, rec in list(self._cache.items()):
                if rec["state"] in ("running", "aborting"):
                    rec["state"] = "interrupted"
                    rec["error"] = "进程重启导致任务中断"
                    rec["finished_at"] = time.time()
                    rec["updated_at"] = rec["finished_at"]
                    self._write_archive(rec)
                    self._remove_active(jid)
                    recovered.append(jid)
        return recovered

    # ---------- 内部 ----------

    def _write_active(self, rec: dict) -> None:
        self._atomic_write(self._active / f"{rec['job_id']}.json", rec)

    def _write_archive(self, rec: dict) -> None:
        self._atomic_write(self._archive / f"{rec['job_id']}.json", rec)

    def _remove_active(self, job_id: str) -> None:
        p = self._active / f"{job_id}.json"
        if p.exists():
            p.unlink()

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
