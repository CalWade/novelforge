"""Migration script: genres/ + projects/(with genre ref) → presets/ + projects/(self-contained)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


def _load_migrate_module():
    root = Path(__file__).resolve().parent.parent
    spec_path = root / "scripts" / "migrate_to_book_centric.py"
    spec = importlib.util.spec_from_file_location("migrate_to_book_centric", spec_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migrate_to_book_centric"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    # genres/alpha (has resource_schema) + genres/beta (no schema)
    for gid in ("alpha", "beta"):
        g = tmp_path / "genres" / gid
        g.mkdir(parents=True)
        (g / "genre.yaml").write_text(f"id: {gid}\ndisplay_name: {gid}\n", encoding="utf-8")
        (g / "era.md").write_text(f"# era {gid}\n", encoding="utf-8")
        (g / "writing-style-extra.md").write_text(f"# style {gid}\n", encoding="utf-8")
        (g / "iron-laws-extra.md").write_text(f"# laws {gid}\n", encoding="utf-8")
    (tmp_path / "genres" / "alpha" / "resource_schema.yaml").write_text(
        "resources:\n  - name: gold\n", encoding="utf-8"
    )

    # 2 real projects + 1 smoke test residue
    for pid, gid in (("alpha-bookone", "alpha"), ("beta-booktwo", "beta")):
        p = tmp_path / "projects" / pid
        p.mkdir(parents=True)
        (p / "project.yaml").write_text(
            f"id: {pid}\ngenre: {gid}\nprotagonist_name: hero\n", encoding="utf-8"
        )
        (p / "outline.json").write_text("{}", encoding="utf-8")
        (p / "characters.yaml").write_text("main: {}\n", encoding="utf-8")
        (p / "timeline.yaml").write_text("events: []\n", encoding="utf-8")

    smoke = tmp_path / "projects" / "test-ui-smoke"
    smoke.mkdir(parents=True)
    (smoke / "project.yaml").write_text("id: test-ui-smoke\n", encoding="utf-8")

    # root novels pool (must remain untouched)
    novels = tmp_path / "novels"
    novels.mkdir()
    (novels / "README.md").write_text("pool\n", encoding="utf-8")
    (novels / "sample.txt").write_text("chapter one\n", encoding="utf-8")

    return tmp_path


def test_migration_produces_presets_dir(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    presets = fake_repo / "presets"
    assert (presets / "alpha" / "genre.yaml").read_text(encoding="utf-8").startswith("id: alpha")
    assert (presets / "alpha" / "resource_schema.yaml").exists()
    assert (presets / "beta" / "iron-laws-extra.md").exists()
    assert not (presets / "beta" / "resource_schema.yaml").exists()


def test_migration_creates_empty_novels_per_preset(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    for gid in ("alpha", "beta"):
        novels_dir = fake_repo / "presets" / gid / "novels"
        assert (novels_dir / ".gitkeep").exists()
        assert list(novels_dir.glob("*.txt")) == []


def test_migration_copies_genre_files_into_project_dirs(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    alpha = fake_repo / "projects" / "alpha-bookone"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md", "resource_schema.yaml"):
        assert (alpha / fname).exists(), f"{fname} missing in alpha-bookone"
    beta = fake_repo / "projects" / "beta-booktwo"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        assert (beta / fname).exists()
    assert not (beta / "resource_schema.yaml").exists()


def test_migration_rewrites_project_yaml(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    for pid, expected in (("alpha-bookone", "alpha"), ("beta-booktwo", "beta")):
        data = yaml.safe_load((fake_repo / "projects" / pid / "project.yaml").read_text(encoding="utf-8"))
        assert data["source_preset"] == expected
        assert "genre" not in data


def test_migration_deletes_genres_dir(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    assert not (fake_repo / "genres").exists()


def test_migration_deletes_test_ui_smoke(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    assert not (fake_repo / "projects" / "test-ui-smoke").exists()


def test_migration_leaves_novels_pool_untouched(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    assert (fake_repo / "novels" / "sample.txt").read_text(encoding="utf-8") == "chapter one\n"
    assert (fake_repo / "novels" / "README.md").exists()


def test_migration_is_idempotent(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    result = mod.migrate(repo_root=fake_repo)
    assert result["skipped"] is True
    assert "already" in result["reason"].lower()
