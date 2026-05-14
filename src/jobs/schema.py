"""Job record schema 与常量."""
from __future__ import annotations

import time
import uuid
from typing import Literal, TypedDict

SCHEMA_VERSION = 1

JobState = Literal["running", "aborting", "done", "failed", "aborted", "interrupted"]
JobKind = Literal["from-novel", "from-description", "blank"]
TargetType = Literal["preset", "project"]

TERMINAL_STATES = frozenset({"done", "failed", "aborted", "interrupted"})
PHASE_ORDER = ("extract", "merge", "draft", "validate")
PHASE_TOTAL = 4


class Target(TypedDict):
    type: TargetType
    id: str


class SubSteps(TypedDict, total=False):
    batch_cur: int | None
    batch_total: int | None
    arc_cur: int | None
    arc_total: int | None
    draft_pass: int | None
    validate_round: int | None


def new_job_id() -> str:
    return uuid.uuid4().hex


def empty_sub_steps() -> SubSteps:
    return {
        "batch_cur": None, "batch_total": None,
        "arc_cur": None, "arc_total": None,
        "draft_pass": None, "validate_round": None,
    }


def initial_job_record(
    *,
    job_id: str,
    kind: JobKind,
    target: Target,
    label: str,
    sources: list[str] | None = None,
    params: dict | None = None,
) -> dict:
    now = time.time()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "label": label,
        "kind": kind,
        "target": target,
        "state": "running",
        "phase": None,
        "phase_index": 0,
        "phase_total": PHASE_TOTAL,
        "sub_steps": empty_sub_steps(),
        "progress_text": "",
        "error": None,
        "log_path": f".jobs/logs/{job_id}.log",
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "sources": sources or [],
        "params": params or {},
    }
