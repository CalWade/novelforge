"""Tests for single-layer book-centric bootstrap (Phase 2 refactor).

Replaces the earlier two-layer genre+project tests. The current schema is:
  - presets/<id>/           — seed templates (consumed only by create_project)
  - projects/<id>/          — one novel, self-contained (includes genre files)
  - projects/<id>/state/    — runtime artifacts

See also tests/test_bootstrap_book_centric.py for the create_project wizard.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from src import bootstrap, config


# ---------------- test helpers ----------------


def _seed_project_with_genre_files(
    project_dir: Path, project_id: str, *, with_schema: bool = False
) -> None:
    """Seed a self-contained project directory including genre files."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "id": project_id,
                "display_name": f"test project {project_id}",
                "protagonist_name": "A",
                "protagonist_hook": "hook",
                "opening_year_month": "2024-01",
                "chapter_count_target": 10,
                "chapters_in_outline": 1,
                "source_preset": "test-preset",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (project_dir / "outline.json").write_text(
        json.dumps({"chapters": [{"ch": 1, "title": "t"}]}),
        encoding="utf-8",
    )
    (project_dir / "characters.yaml").write_text(
        "protagonist:\n  name: A\n", encoding="utf-8"
    )
    (project_dir / "timeline.yaml").write_text("2024: []\n", encoding="utf-8")
    # Genre files co-located under the project
    (project_dir / "era.md").write_text("era text", encoding="utf-8")
    (project_dir / "writing-style-extra.md").write_text("style text", encoding="utf-8")
    (project_dir / "iron-laws-extra.md").write_text(
        "## iron_law_extra_1\nfoo\n", encoding="utf-8"
    )
    if with_schema:
        (project_dir / "resource_schema.yaml").write_text(
            "resources: []\nvalidation:\n  increment_rules: []\n  forbidden_fuzzy_terms: []\n",
            encoding="utf-8",
        )


@pytest.fixture
def isolated_repo(tmp_path, monkeypatch):
    """Redirect config paths at a tmp tree so tests don't touch the real repo."""
    presets = tmp_path / "presets"
    projects = tmp_path / "projects"
    presets.mkdir()
    projects.mkdir()
    active = projects / ".active"
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", presets)
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    monkeypatch.setattr(config, "ACTIVE_POINTER", active)
    return tmp_path


# ---------------- list + validate ----------------


def test_list_presets_empty(isolated_repo):
    assert bootstrap.list_presets() == []


def test_list_projects_empty(isolated_repo):
    assert bootstrap.list_projects() == []


def test_validate_project_reports_missing_files(isolated_repo):
    pd = isolated_repo / "projects" / "incomplete"
    pd.mkdir()
    missing = bootstrap.validate_project(pd)
    assert set(missing) == set(bootstrap.REQUIRED_PROJECT_FILES)


def test_validate_project_passes_on_complete(isolated_repo):
    _seed_project_with_genre_files(isolated_repo / "projects" / "p1", "p1")
    assert bootstrap.validate_project(isolated_repo / "projects" / "p1") == []


# ---------------- bootstrap_project ----------------


def test_bootstrap_project_copies_genre_and_project_files(isolated_repo):
    _seed_project_with_genre_files(
        isolated_repo / "projects" / "p1", "p1", with_schema=True
    )
    result = bootstrap.bootstrap_project("p1")
    assert result.project_id == "p1"
    assert result.source_preset == "test-preset"
    state = result.state_dir
    # Genre-layer files present
    assert (state / "era.md").exists()
    assert (state / "writing-style-extra.md").exists()
    assert (state / "iron-laws-extra.md").exists()
    assert (state / "resource_schema.yaml").exists()
    # Project-layer files present
    assert (state / "outline.json").exists()
    assert (state / "characters.yaml").exists()
    assert (state / "timeline.yaml").exists()
    # Synthesized setting.yaml from project.yaml
    merged = yaml.safe_load((state / "setting.yaml").read_text(encoding="utf-8"))
    assert merged["id"] == "p1"
    assert merged["protagonist_name"] == "A"
    assert merged["active_project"] == "p1"
    assert "active_genre" not in merged  # no genre layer anymore
    # progress + accumulators
    assert (state / "progress.json").exists()
    assert (state / "issues.jsonl").exists()
    assert (state / "debt.jsonl").exists()


def test_bootstrap_activates_project(isolated_repo):
    _seed_project_with_genre_files(isolated_repo / "projects" / "p1", "p1")
    bootstrap.bootstrap_project("p1")
    assert config.get_active_project_id() == "p1"
    assert config.active_project_dir() == isolated_repo / "projects" / "p1"
    assert config.active_state_dir() == isolated_repo / "projects" / "p1" / "state"


def test_bootstrap_unknown_project_raises(isolated_repo):
    with pytest.raises(FileNotFoundError, match="Project not found"):
        bootstrap.bootstrap_project("does-not-exist")


def test_bootstrap_incomplete_project_raises(isolated_repo):
    """Project missing era.md (now a required project-layer file) must fail."""
    pd = isolated_repo / "projects" / "p1"
    _seed_project_with_genre_files(pd, "p1")
    (pd / "era.md").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        bootstrap.bootstrap_project("p1")


def test_bootstrap_purges_stale_resource_schema(isolated_repo):
    """Removing a project's resource_schema.yaml should purge it from state/."""
    pd = isolated_repo / "projects" / "p1"
    _seed_project_with_genre_files(pd, "p1", with_schema=True)

    result = bootstrap.bootstrap_project("p1")
    assert (result.state_dir / "resource_schema.yaml").exists()

    # Remove schema from project source + re-bootstrap
    (pd / "resource_schema.yaml").unlink()
    result2 = bootstrap.bootstrap_project("p1")
    assert not (result2.state_dir / "resource_schema.yaml").exists()


# ---------------- real repo integration ----------------


@pytest.mark.parametrize(
    "project_id",
    [
        "gangster-hk-1983-linjiayao",
        "xianxia-ascension-peichangning",
        "urban-romance-shenruowei",
    ],
)
def test_real_projects_are_complete(project_id):
    """Integration: each shipped project must have all required files."""
    pd = config.PROJECTS_DIR / project_id
    missing = bootstrap.validate_project(pd)
    assert missing == [], f"{project_id} missing required files: {missing}"


# ---------------- preserve_progress ----------------


def test_bootstrap_project_preserves_progress_when_asked(isolated_repo):
    """preserve_progress=True keeps completed_chapters / current_chapter intact."""
    pd = isolated_repo / "projects" / "p1"
    _seed_project_with_genre_files(pd, "p1")
    # first bootstrap creates the state/
    bootstrap.bootstrap_project("p1")
    progress_path = pd / "state" / "progress.json"

    fake = {
        "current_chapter": 99,
        "completed_chapters": [1, 2, 99],
        "in_flight": None,
        "last_update": None,
        "total_llm_calls": 12345,
    }
    progress_path.write_text(json.dumps(fake), encoding="utf-8")

    bootstrap.bootstrap_project("p1", preserve_progress=True)
    new = json.loads(progress_path.read_text(encoding="utf-8"))
    assert new["current_chapter"] == 99
    assert new["completed_chapters"] == [1, 2, 99]
    assert new["total_llm_calls"] == 12345
    assert new["active_project"] == "p1"


def test_bootstrap_project_resets_progress_by_default(isolated_repo):
    """Without preserve_progress, progress is RESET (CLI behavior)."""
    pd = isolated_repo / "projects" / "p1"
    _seed_project_with_genre_files(pd, "p1")
    bootstrap.bootstrap_project("p1")
    progress_path = pd / "state" / "progress.json"

    fake = {"current_chapter": 99, "completed_chapters": [99], "total_llm_calls": 100}
    progress_path.write_text(json.dumps(fake), encoding="utf-8")

    bootstrap.bootstrap_project("p1")  # default preserve_progress=False
    new = json.loads(progress_path.read_text(encoding="utf-8"))
    assert new["current_chapter"] == 0, "progress should have been reset"
    assert new["completed_chapters"] == []
