"""Extract a genre pack into projects/<book-id>/.

Sources resolve via the same rules as to_preset (pool-first, absolute ok).
Prior era.md/writing-style-extra.md/iron-laws-extra.md/resource_schema.yaml
contents are backed up into projects/<book-id>/state/.backup/ with a timestamp.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from src import config
from src.blackboard import Blackboard
from src.genre_extractor import core
from src.genre_extractor.to_preset import _resolve_source

GENRE_FILES = (
    "era.md",
    "writing-style-extra.md",
    "iron-laws-extra.md",
    "resource_schema.yaml",
)


def _run_full_extraction_to_blueprint(bb: Blackboard, sources: list[Path]) -> dict:
    """Drive the core pipeline end-to-end; return the final blueprint dict.

    Own function so tests can monkeypatch to avoid LLMs.
    """
    streams = [open(p, "r", encoding="utf-8") for p in sources]
    try:
        core.run_extract(bb, streams)
    finally:
        for s in streams:
            s.close()
    core.run_merge(bb)
    core.run_draft(bb, build_key=str(bb.root))
    return bb.read_yaml("genre_blueprint.yaml") or {}


def extract_to_project(
    book_id: str,
    *,
    sources: list[str],
    with_trial: bool = False,
) -> dict:
    """Extract a genre pack into this book's own directory (overwriting in place,
    prior versions backed up)."""
    book_dir = config.PROJECTS_DIR / book_id
    if not book_dir.exists():
        raise FileNotFoundError(f"Project not found: {book_id}")

    resolved = [_resolve_source(s) for s in sources]
    for p in resolved:
        if not p.exists():
            raise FileNotFoundError(f"Source not found: {p}")

    state_dir = book_dir / "state"
    state_dir.mkdir(exist_ok=True)
    backup_dir = state_dir / ".backup"
    backup_dir.mkdir(exist_ok=True)
    build_dir = state_dir / ".extract_build"
    build_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    for fname in GENRE_FILES:
        src = book_dir / fname
        if src.exists():
            stem, dot, ext = fname.rpartition(".")
            # produce "era.<ts>.md" style names
            backup_name = f"{stem}.{ts}.{ext}" if dot else f"{fname}.{ts}"
            shutil.copy2(src, backup_dir / backup_name)

    bb = Blackboard(root=build_dir)
    blueprint = _run_full_extraction_to_blueprint(bb, resolved)
    core.render_files_from_blueprint(blueprint, out_dir=book_dir)

    result = {"book_id": book_id, "sources": [str(p) for p in resolved]}
    if with_trial:
        from src.genre_extractor import trial
        result["trial"] = trial.run_trial_against_project(book_id)
    return result
