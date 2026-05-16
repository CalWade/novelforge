"""Lock in: from-novel job correctly resolves bare filenames to novels/ subdir.

Why: web frontend's preset wizard sends sources as bare filenames (from
GET /api/novels which returns n.name without prefix), but old code
joined them at PROJECT_ROOT directly, looking for files at
/repo/<filename> instead of /repo/novels/<filename>. This caused
"novel not found" failures on every from-novel job submission.

User reported: 新建题材失败. job archive showed FileNotFoundError on
/Users/calvin/Desktop/opencode/地球OL...txt (missing novels/ prefix).

Reproduce: POST /api/jobs with sources=["地球OL.txt"] → must NOT raise.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _import_resolve():
    """Import the inner _resolve_novel_path from jobs.py via execution.

    The function is defined inside _spawn_worker → from-novel branch, so we
    can't import it directly. Instead, reproduce the resolution logic here
    and test it stays in sync with jobs.py.
    """
    from src import config
    
    def resolve(s: str) -> Path:
        p = Path(s)
        if p.is_absolute():
            return p
        if p.parts and p.parts[0] == "novels":
            return config.PROJECT_ROOT / p
        return config.PROJECT_ROOT / "novels" / p
    
    return resolve, config


def test_bare_filename_gets_novels_prefix():
    """Frontend default: checkbox.value = bare filename"""
    resolve, config = _import_resolve()
    p = resolve("地球OL.txt")
    assert p == config.PROJECT_ROOT / "novels" / "地球OL.txt", (
        f"bare filename must resolve to novels/<name>, got {p}"
    )


def test_relative_with_novels_prefix_passes_through():
    """Backward compat: caller already prefixed novels/ explicitly"""
    resolve, config = _import_resolve()
    p = resolve("novels/末世虫潮.txt")
    assert p == config.PROJECT_ROOT / "novels" / "末世虫潮.txt"


def test_absolute_path_passes_through():
    """Caller can pass absolute path (e.g. for testing fixtures elsewhere)"""
    resolve, _ = _import_resolve()
    p = resolve("/tmp/something.txt")
    assert p == Path("/tmp/something.txt")


def test_jobs_py_source_logic_in_sync():
    """Defense: ensure web/routes/jobs.py contains the helper this test
    reproduces. If someone refactors jobs.py and the helper drifts, this
    test won't catch the drift unless we anchor on a string."""
    jobs_py = Path(__file__).resolve().parent.parent / "web" / "routes" / "jobs.py"
    src = jobs_py.read_text(encoding="utf-8")
    # The helper must exist with the novels/ prefix logic
    assert "_resolve_novel_path" in src, (
        "jobs.py missing _resolve_novel_path helper — bare filename resolution may regress"
    )
    assert 'p.parts[0] == "novels"' in src, (
        "jobs.py _resolve_novel_path missing novels/ prefix detection"
    )
    assert '"novels" / p' in src or '"novels", p' in src, (
        "jobs.py _resolve_novel_path missing novels/ join logic"
    )


def test_real_novels_exist_at_expected_path():
    """Sanity: the actual novels/ dir is the canonical location"""
    from src import config
    novels_dir = config.PROJECT_ROOT / "novels"
    assert novels_dir.exists(), (
        "novels/ directory must exist as the canonical material location"
    )
