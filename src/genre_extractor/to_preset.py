"""Extract a genre pack into presets/<preset-id>/.

Sources come from the global novels/ pool (or absolute paths). Selected
sources are copied into presets/<preset-id>/novels/ so the preset is
self-describing.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

import yaml

from src import config
from src.blackboard import Blackboard
from src.genre_extractor import core, schemas
from src.genre_extractor.chapter_stream import ChapterStream

# See to_project.PhaseCallback for contract.
PhaseCallback = Callable[[str, Optional[str]], None]


def _safe_phase(on_phase: Optional[PhaseCallback], phase: str, progress: Optional[str] = None) -> None:
    """Fire a phase event if wired; never raise — UI glue must not fail extraction."""
    if on_phase is None:
        return
    try:
        on_phase(phase, progress)
    except Exception:
        pass


def _resolve_source(path_str: str) -> Path:
    """Resolve source path: absolute → as-is; relative → tried under novels/ first,
    then under project root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] == "novels":
        return config.PROJECT_ROOT / p
    cand = config.PROJECT_ROOT / "novels" / p
    if cand.exists():
        return cand
    return config.PROJECT_ROOT / p


def _run_full_extraction_to_blueprint(
    bb: Blackboard,
    sources: list,
    *,
    on_phase: Optional[PhaseCallback] = None,
) -> dict:
    """Drive the core pipeline end-to-end; return the final blueprint dict.

    Extracted into its own function so tests can monkeypatch to avoid LLMs.

    ``sources`` is a list of :class:`ChapterStream` instances. They must
    remain alive for the whole call (they own a tempfile via ``__del__``
    for non-UTF-8 source novels); the caller (``extract_to_preset``) holds
    them in its own local, so they won't be GC'd mid-run.

    Fires ``on_phase("extract" | "merge" | "draft")`` at each stage boundary.
    """
    _safe_phase(on_phase, "extract")
    # core.run_extract expects an iterable of (ChapterStream, batch_size) tuples.
    # No open()/close() dance: ChapterStream manages its own tempfile in __del__.
    core.run_extract(
        bb,
        [(s, core.DEFAULT_EXTRACTION_BATCH_SIZE) for s in sources],
    )
    _safe_phase(on_phase, "merge")
    core.run_merge(bb)
    _safe_phase(on_phase, "draft")
    core.run_draft(bb, build_key=str(bb.root))
    # Blueprint was written by run_draft into bb's genre_blueprint.yaml
    return bb.read_yaml("genre_blueprint.yaml") or {}


def extract_to_preset(
    preset_id: str,
    *,
    sources: list[str],
    with_trial: bool = False,
    on_phase: Optional[PhaseCallback] = None,
) -> dict:
    """Run the extraction pipeline; write preset artifacts.

    Refuses to overwrite an existing preset — presets are append-only.
    """
    preset_dir = config.PRESETS_DIR / preset_id
    if preset_dir.exists():
        raise FileExistsError(f"Preset already exists: {preset_id}")

    resolved_sources = [_resolve_source(s) for s in sources]
    for p in resolved_sources:
        if not p.exists():
            raise FileNotFoundError(f"Source not found: {p}")

    preset_dir.mkdir(parents=True)
    (preset_dir / "novels").mkdir()
    build_dir = preset_dir / ".build"
    build_dir.mkdir()

    bb = Blackboard(root=build_dir)

    # Build ChapterStream instances up front (one pass). This:
    #   1. Surfaces encoding / chapter-marker errors early.
    #   2. Gives us the per-source total_chapters count needed to seed
    #      build_status.yaml with a correct ``batches_total``.
    #   3. Avoids re-parsing: the same instances are handed to
    #      _run_full_extraction_to_blueprint → core.run_extract.
    # Held in this function's local so their tempfile-cleaning __del__
    # doesn't fire until the whole pipeline (including run_merge/run_draft)
    # is done.
    streams = [ChapterStream(p) for p in resolved_sources]
    novel_sources = [
        {
            "path": str(p),
            "total_chapters": s.total_chapters,
            "batch_size": core.DEFAULT_EXTRACTION_BATCH_SIZE,
        }
        for p, s in zip(resolved_sources, streams)
    ]

    # Seed build_status.yaml BEFORE run_extract runs. core.run_extract's
    # first action is schemas.update_phase_status(...), which *reads*
    # build_status.yaml — so if we don't seed it here we crash with
    # FileNotFoundError before the first batch.
    bb.write_yaml(
        "build_status.yaml",
        schemas.make_initial_build_status(
            genre_id=preset_id,
            entry="extract-to-preset",
            novel_sources=novel_sources,
        ),
    )

    blueprint = _run_full_extraction_to_blueprint(bb, streams, on_phase=on_phase)
    core.render_files_from_blueprint(blueprint, out_dir=preset_dir)

    # seed genre.yaml
    (preset_dir / "genre.yaml").write_text(
        yaml.safe_dump(
            {
                "id": preset_id,
                "display_name": preset_id,
                "extracted_from": [p.name for p in resolved_sources],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    # copy sources into preset's novels/
    for p in resolved_sources:
        shutil.copy2(p, preset_dir / "novels" / p.name)

    # P0-2: run Validator + Fixer retry loop against the newly-written preset
    # dir. ``files_dir == PRESETS_DIR / preset_id`` here matches the legacy
    # default; passing it explicitly keeps intent obvious and symmetrical
    # with extract_to_project.
    from src.genre_extractor import pipeline
    _safe_phase(on_phase, "validate")
    try:
        pipeline._run_validate(
            bb,
            preset_id,
            with_trial=False,
            files_dir=preset_dir,
        )
    except Exception as e:
        bb.append_jsonl("genre_issues.jsonl", {
            "severity": "warning",
            "file": "(validator)",
            "message": f"validate phase failed: {type(e).__name__}: {e}",
            "genre_id": preset_id,
        })

    result = {"preset_id": preset_id, "sources": [str(p) for p in resolved_sources]}
    if with_trial:
        from src.genre_extractor import trial
        result["trial"] = trial.run_trial_against_preset(preset_id)
    _safe_phase(on_phase, "done")
    return result
