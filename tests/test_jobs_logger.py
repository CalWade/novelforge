"""JobLogger：rotating file handler，文本日志 append."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def log_env(tmp_path: Path, monkeypatch):
    from src.jobs import logger as mod
    monkeypatch.setattr(mod, "LOGS_DIR", tmp_path / "logs")
    return tmp_path


def test_get_logger_writes_to_file(log_env):
    from src.jobs.logger import get_job_logger
    lg = get_job_logger("job1")
    lg.info("hello")
    lg.info("world")
    content = (log_env / "logs" / "job1.log").read_text(encoding="utf-8")
    assert "hello" in content
    assert "world" in content


def test_two_loggers_same_job_share_handler(log_env):
    """重复调用 get_job_logger 不应加多个 handler（防止重复写）."""
    from src.jobs.logger import get_job_logger
    lg1 = get_job_logger("j2")
    lg2 = get_job_logger("j2")
    assert lg1 is lg2
    lg1.info("once")
    content = (log_env / "logs" / "j2.log").read_text(encoding="utf-8")
    assert content.count("once") == 1


def test_read_tail_returns_content_from_offset(log_env):
    from src.jobs.logger import get_job_logger, read_log_tail
    lg = get_job_logger("j3")
    lg.info("line A")
    lg.info("line B")
    (content1, next_off1) = read_log_tail("j3", offset=0)
    assert "line A" in content1
    assert next_off1 > 0
    # 不再写入
    (content2, next_off2) = read_log_tail("j3", offset=next_off1)
    assert content2 == ""
    assert next_off2 == next_off1


def test_read_tail_missing_log_returns_empty(log_env):
    from src.jobs.logger import read_log_tail
    c, o = read_log_tail("unknown-job", offset=0)
    assert c == ""
    assert o == 0
