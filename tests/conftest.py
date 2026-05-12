"""Shared fixtures for the test suite."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import bootstrap, config


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """Create a throwaway bootstrapped project in tmp_path; return its id.

    Used by tests that need to exercise the full bootstrap / project-file /
    preserve_progress machinery WITHOUT touching the real projects/ dir on
    disk. If those tests crashed mid-way with restore-via-try/finally they
    could (and did) leave a real user's project.yaml tainted.

    The fixture:
      1. Redirects config.PROJECTS_DIR to tmp_path.
      2. Copies the real `gangster-hk-1983-linjiayao` project into tmp_path
         under a fixed id (so we inherit a valid outline/characters/timeline
         without maintaining a synthetic fixture project).
      3. Points config.ACTIVE_POINTER at a tmp file.
      4. Bootstraps the project — this seeds tmp_path/<id>/state/ and makes
         it the active project for the test.
      5. At teardown, monkeypatch auto-reverts all config overrides and
         pytest wipes tmp_path.

    Yields the project id as a string.
    """
    import shutil

    src_project = config.PROJECTS_DIR / "gangster-hk-1983-linjiayao"
    if not src_project.exists():
        pytest.skip("real gangster-hk-1983-linjiayao project missing; cannot set up isolated copy")

    pid = "isolated-test-proj"
    dst_project = tmp_path / pid
    # Copy the core project files + co-located genre files (single-layer).
    # state/ will be re-created by bootstrap.
    dst_project.mkdir()
    for fname in (
        "project.yaml", "outline.json", "characters.yaml", "timeline.yaml",
        "era.md", "writing-style-extra.md", "iron-laws-extra.md",
    ):
        shutil.copy2(src_project / fname, dst_project / fname)
    # Optional resource_schema.yaml: copy if present (gangster has one)
    optional = src_project / "resource_schema.yaml"
    if optional.exists():
        shutil.copy2(optional, dst_project / "resource_schema.yaml")

    # Redirect config paths
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / ".active")

    # Bootstrap to create state/ under the isolated project
    bootstrap.bootstrap_project(pid)

    yield pid

    # No explicit cleanup needed: tmp_path is wiped, monkeypatch reverts.
    # But restore STATE_DIR so other tests in the same process don't see
    # a pointer to a vanished tmp_path.
    config.refresh_state_dir()
