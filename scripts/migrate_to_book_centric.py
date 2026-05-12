#!/usr/bin/env python3
"""One-shot migration: genres/ + projects/(with genre ref) → presets/ + projects/(self-contained).

Idempotent: if presets/ already exists OR genres/ is absent, skips.
Safe: does not touch projects/<id>/state/ (bootstrap will regenerate at runtime).
Run once after this change is merged, then delete this file.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional

import yaml

GENRE_FILES = ("era.md", "writing-style-extra.md", "iron-laws-extra.md")
OPTIONAL_GENRE_FILES = ("resource_schema.yaml",)


def migrate(repo_root: Optional[Path] = None) -> dict:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    presets = root / "presets"
    genres = root / "genres"
    projects = root / "projects"

    if presets.exists():
        return {"skipped": True, "reason": "already migrated (presets/ exists)"}
    if not genres.exists():
        return {"skipped": True, "reason": "already migrated (no genres/ found)"}

    # 1. presets/ ← genres/
    presets.mkdir(parents=True)
    for genre_dir in sorted(genres.iterdir()):
        if genre_dir.is_dir():
            shutil.copytree(genre_dir, presets / genre_dir.name)

    # 2. empty novels/ per preset
    for preset_dir in sorted(presets.iterdir()):
        if preset_dir.is_dir():
            (preset_dir / "novels").mkdir(exist_ok=True)
            (preset_dir / "novels" / ".gitkeep").write_text("", encoding="utf-8")

    # 3 + 4. inject genre files + rewrite project.yaml
    if projects.exists():
        for proj_dir in sorted(projects.iterdir()):
            if not proj_dir.is_dir() or proj_dir.name == "test-ui-smoke":
                continue
            proj_yaml = proj_dir / "project.yaml"
            if not proj_yaml.exists():
                continue
            pdata = yaml.safe_load(proj_yaml.read_text(encoding="utf-8")) or {}
            src_id = pdata.get("genre")
            if not src_id:
                continue
            src_dir = presets / src_id
            if not src_dir.exists():
                continue
            for fname in GENRE_FILES + OPTIONAL_GENRE_FILES:
                src = src_dir / fname
                if src.exists():
                    shutil.copy2(src, proj_dir / fname)
            pdata["source_preset"] = src_id
            pdata.pop("genre", None)
            proj_yaml.write_text(
                yaml.safe_dump(pdata, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

    # 5. cleanup
    shutil.rmtree(genres)
    smoke = projects / "test-ui-smoke" if projects.exists() else None
    if smoke and smoke.exists():
        shutil.rmtree(smoke)

    return {"skipped": False, "reason": "migration complete"}


if __name__ == "__main__":
    result = migrate()
    if result["skipped"]:
        print(f"skipped: {result['reason']}", file=sys.stderr)
        sys.exit(0)
    print(f"ok: {result['reason']}")
