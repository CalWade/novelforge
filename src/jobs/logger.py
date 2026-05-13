"""JobLogger：每个 job 一个 rotating file handler.

- 单文件 10MB，保留 3 份（总 40MB 上限）
- `get_job_logger(job_id)` 幂等：同一 job 只创建一次 handler
- `read_log_tail(job_id, offset)` 给前端轮询用
"""
from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src import config

LOGS_DIR = config.PROJECT_ROOT / ".jobs" / "logs"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 3

_LOGGERS: dict[str, logging.Logger] = {}
_LOCK = threading.Lock()


def get_job_logger(job_id: str) -> logging.Logger:
    with _LOCK:
        if job_id in _LOGGERS:
            return _LOGGERS[job_id]
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        lg = logging.getLogger(f"novelforge.job.{job_id}")
        lg.setLevel(logging.INFO)
        lg.propagate = False
        # 清理旧 handler（防止测试中 module reload 出现的累加）
        lg.handlers.clear()
        handler = RotatingFileHandler(
            LOGS_DIR / f"{job_id}.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        lg.addHandler(handler)
        _LOGGERS[job_id] = lg
        return lg


def read_log_tail(job_id: str, offset: int = 0) -> tuple[str, int]:
    """从 offset 字节开始读取日志。返回 (内容, 下一个 offset)."""
    p = LOGS_DIR / f"{job_id}.log"
    if not p.exists():
        return "", 0
    size = p.stat().st_size
    if offset >= size:
        return "", offset
    with p.open("rb") as f:
        f.seek(offset)
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return text, offset + len(raw)
