"""P0-5: /extract-genre/progress exposes phase / phase_index / phase_total.

The 4-bar timeline the UI paints needs a stable server-side contract. This
test asserts the dict returned by the progress endpoint includes the phase
fields and that the callback pipeline plumbing correctly advances them.
"""
from __future__ import annotations

from pathlib import Path
import time

import pytest


@pytest.fixture
def app_with_book(tmp_path: Path, monkeypatch):
    """Same skeleton as test_web_project_extract_genre.py — gives us a book
    the progress endpoint can actually answer for."""
    from src import config, bootstrap
    preset = tmp_path / "presets" / "alpha"
    preset.mkdir(parents=True)
    for f in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        (preset / f).write_text("x\n", encoding="utf-8")
    (preset / "genre.yaml").write_text("id: alpha\n", encoding="utf-8")
    (preset / "novels").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "novels" / "seed.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")

    bootstrap.create_project(
        "mybook", display_name="B", protagonist_name="H", chapter_count_target=3,
        from_preset="alpha", blank_outline=True, blank_characters=True,
    )
    from web import app as web_app
    # Isolate each test: the in-memory job dicts persist across tests in
    # the same process, which would otherwise cause "job already running"
    # false conflicts when a prior test's worker hasn't finished.
    with web_app._PROJECT_JOB_LOCK:
        web_app._PROJECT_JOBS.clear()
    with web_app._PRESET_JOB_LOCK:
        web_app._PRESET_JOBS.clear()
    return web_app.app.test_client()


def test_progress_unknown_pid_has_no_phase(app_with_book):
    """Unknown job returns state=unknown; phase fields are absent (or None)
    because there's no job to attribute them to."""
    r = app_with_book.get("/api/projects/never-started/extract-genre/progress")
    assert r.status_code == 200
    data = r.get_json()
    assert data["state"] == "unknown"
    # Contract: phase fields not required for unknown, but if present must be None.
    for k in ("phase", "phase_index", "phase_total"):
        if k in data:
            assert data[k] is None


def test_progress_exposes_phase_fields_after_start(app_with_book, monkeypatch):
    """When a job is running, progress returns phase + phase_index + phase_total."""
    from web import app as web_app

    # Seed a running job using the same helper the real code uses, so any
    # future schema tweak stays covered by this test automatically.
    with web_app._PROJECT_JOB_LOCK:
        web_app._PROJECT_JOBS["mybook"] = web_app._initial_job_state()

    r = app_with_book.get("/api/projects/mybook/extract-genre/progress")
    assert r.status_code == 200
    data = r.get_json()
    assert data["state"] == "running"
    assert data["phase"] == "extract"
    assert data["phase_index"] == 1
    assert data["phase_total"] == 4
    assert "started_at" in data
    assert "updated_at" in data


def test_phase_callback_advances_job(app_with_book):
    """_make_phase_cb mutates the job dict so the progress endpoint shows
    the new phase without waiting for the whole extraction to finish."""
    from web import app as web_app

    with web_app._PROJECT_JOB_LOCK:
        web_app._PROJECT_JOBS["mybook"] = web_app._initial_job_state()

    cb = web_app._make_phase_cb(web_app._PROJECT_JOBS, web_app._PROJECT_JOB_LOCK, "mybook")
    cb("merge", "batch 2/5")

    r = app_with_book.get("/api/projects/mybook/extract-genre/progress")
    data = r.get_json()
    assert data["phase"] == "merge"
    assert data["phase_index"] == 2
    assert data["progress"] == "batch 2/5"

    cb("draft", None)
    data = app_with_book.get("/api/projects/mybook/extract-genre/progress").get_json()
    assert data["phase"] == "draft"
    assert data["phase_index"] == 3

    cb("validate", None)
    data = app_with_book.get("/api/projects/mybook/extract-genre/progress").get_json()
    assert data["phase_index"] == 4


def test_phase_callback_swallows_unknown_phase(app_with_book):
    """A typo in the extractor should not corrupt phase_index into -1+1=0."""
    from web import app as web_app
    with web_app._PROJECT_JOB_LOCK:
        web_app._PROJECT_JOBS["mybook"] = web_app._initial_job_state()
    cb = web_app._make_phase_cb(web_app._PROJECT_JOBS, web_app._PROJECT_JOB_LOCK, "mybook")
    cb("extract", None)
    cb("bogus-phase", None)  # should not clobber phase/phase_index
    data = app_with_book.get("/api/projects/mybook/extract-genre/progress").get_json()
    assert data["phase"] == "extract"
    assert data["phase_index"] == 1


def test_preset_status_also_has_phase_fields(tmp_path, monkeypatch):
    """Same contract on the preset side so the /presets progress page can
    reuse the same phase-timeline component."""
    from src import config
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    (tmp_path / "presets").mkdir(parents=True)

    from web import app as web_app
    client = web_app.app.test_client()
    with web_app._PRESET_JOB_LOCK:
        web_app._PRESET_JOBS["alpha"] = web_app._initial_job_state()

    r = client.get("/api/presets/alpha/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["state"] == "running"
    assert data["phase"] == "extract"
    assert data["phase_index"] == 1
    assert data["phase_total"] == 4


def test_extract_wires_phase_callback(app_with_book, monkeypatch):
    """End-to-end: the real project-extract worker invokes extract_to_project
    with an ``on_phase`` kwarg, which the UI depends on."""
    from web import app as web_app
    # Clear any leftover job state from prior tests in the same module.
    with web_app._PROJECT_JOB_LOCK:
        web_app._PROJECT_JOBS.clear()

    captured = {}

    def fake_extract(book_id, *, sources, with_trial, on_phase=None):
        captured["on_phase"] = on_phase
        # Fire all four phase events to simulate a real extraction.
        if on_phase:
            on_phase("extract", None)
            on_phase("merge", None)
            on_phase("draft", None)
            on_phase("validate", None)

    monkeypatch.setattr(
        "src.genre_extractor.to_project.extract_to_project",
        fake_extract,
    )

    r = app_with_book.post("/api/projects/mybook/extract-genre", json={
        "sources": ["seed.txt"],
    })
    assert r.status_code == 202

    # Let the worker run.
    for _ in range(40):
        s = app_with_book.get("/api/projects/mybook/extract-genre/progress").get_json()
        if s.get("state") == "done":
            break
        time.sleep(0.05)

    assert captured["on_phase"] is not None, "on_phase callback was not wired through"
