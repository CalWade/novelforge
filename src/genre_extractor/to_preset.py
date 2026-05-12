"""Extract a genre pack into presets/<preset-id>/.

Sources come from the global novels/ pool (or absolute paths). Selected
sources are copied into presets/<preset-id>/novels/ so the preset is
self-describing.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from src import config
from src.blackboard import Blackboard
from src.genre_extractor import core


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


def _run_full_extraction_to_blueprint(bb: Blackboard, sources: list[Path]) -> dict:
    """Drive the core pipeline end-to-end; return the final blueprint dict.

    Extracted into its own function so tests can monkeypatch to avoid LLMs.
    """
    streams = [open(p, "r", encoding="utf-8") for p in sources]
    try:
        core.run_extract(bb, streams)
    finally:
        for s in streams:
            s.close()
    core.run_merge(bb)
    core.run_draft(bb, build_key=str(bb.root))
    # Blueprint was written by run_draft into bb's genre_blueprint.yaml
    return bb.read_yaml("genre_blueprint.yaml") or {}


def extract_to_preset(
    preset_id: str,
    *,
    sources: list[str],
    with_trial: bool = False,
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
    blueprint = _run_full_extraction_to_blueprint(bb, resolved_sources)
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

    result = {"preset_id": preset_id, "sources": [str(p) for p in resolved_sources]}
    if with_trial:
        from src.genre_extractor import trial
        result["trial"] = trial.run_trial_against_preset(preset_id)
    return result
