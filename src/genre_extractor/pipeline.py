"""Genre pipeline orchestrator (preset-centric).

Three entry points:
- fill_preset(preset_id): detect missing files, fill with stubs
- audit_preset(preset_id): Validator stages 1 + 2
- run_phase(preset_id, phase=...): intent-router rerun of a single phase

Book-centric `extract_to_preset` lives in :mod:`src.genre_extractor.to_preset`.

The build workspace lives at ``presets/<id>/.build/`` and is git-ignored.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from src import config
from src.core.blackboard import Blackboard
from src.genre_extractor import core, schemas
from src.genre_extractor.chapter_stream import ChapterStream


# ---------------------------------------------------------------
# Cooperative cancellation (used by web abort button + intent router)
# Mirrors src/pipeline.py::CANCEL_EVENT.
# ---------------------------------------------------------------
CANCEL_EVENT = threading.Event()


class GenrePipelineAborted(RuntimeError):
    """Raised when CANCEL_EVENT is set between stages."""


def _check_cancel() -> None:
    if CANCEL_EVENT.is_set():
        raise GenrePipelineAborted("genre pipeline aborted by cancel signal")


STUB_GENRE_YAML = """# Preset: {preset_id}
id: {preset_id}
display_name: "{display_name}"
locale: zh-Hans
genre: "{genre}"
era: "{era}"
tone: "{tone}"

author_persona_hints: []
genre_avoid: []
prohibited_styles: []
"""

STUB_ERA = """# Era · {preset_id}

（占位：此文件描述 {era} 的时代事实。由后续题材流水线的 Drafter 填充，
或作者手工编写。至少 500 字才能通过 setting_lint。）
"""

STUB_WRITING_STYLE = """# Writing Style Extra · {preset_id}

（占位：此文件描述 {preset_id} 题材特有的风格规范。至少 300 字才能通过 setting_lint。）
"""

STUB_IRON_LAWS = """# Iron Laws Extra · {preset_id}

## iron_law_extra_1: （占位规则一）

（至少 3 条 iron_law_extra_N 才能通过 setting_lint。）

## iron_law_extra_2: （占位规则二）

## iron_law_extra_3: （占位规则三）
"""


def _build_dir(preset_id: str) -> Path:
    return config.PRESETS_DIR / preset_id / ".build"


def _build_bb(preset_id: str) -> Blackboard:
    bd = _build_dir(preset_id)
    bd.mkdir(parents=True, exist_ok=True)
    return Blackboard(root=bd)


def _count_chapters_in_text(text: str) -> int:
    """Delegate to :mod:`genre_extractor.core`."""
    return core.count_chapters_in_text(text)


def _split_text_into_batches(
    text: str, total_chapters: int, batch_size: int
) -> list[str]:
    """Delegate to :mod:`genre_extractor.core`. ``total_chapters`` is kept in
    the signature for backwards compatibility but ignored by core."""
    return core.split_text_into_batches(
        text, batch_size=batch_size, total_chapters=total_chapters,
    )


def _run_extract(bb: Blackboard, source_streams):
    """Delegate to :mod:`genre_extractor.core`."""
    core.run_extract(bb, source_streams)


def _run_merge(bb: Blackboard):
    """Delegate to :mod:`genre_extractor.core`."""
    core.run_merge(bb)


def _parse_batch_id(fname: str) -> int | None:
    """Delegate to :mod:`genre_extractor.core`."""
    return core._parse_batch_id(fname)


def _run_merge_concat(bb: Blackboard, notes):
    """Delegate to :mod:`genre_extractor.core`."""
    core._run_merge_concat(bb, notes)


def _run_merge_multitier(bb: Blackboard, batch_ids: list[int]):
    """Delegate to :mod:`genre_extractor.core`."""
    core._run_merge_multitier(bb, batch_ids)


# Threshold for book-level distill: ≥ 4 arcs → distill. Below that, the
# last arc is promoted to latest_merged directly. Kept here for backwards
# compatibility — the authoritative constant lives in ``core``.
BOOK_ARC_THRESHOLD = core.BOOK_ARC_THRESHOLD


def _run_draft(bb: Blackboard, preset_id: str):
    """Populate the blueprint via ``core.run_draft`` then render real files
    (era.md / writing-style-extra.md / iron-laws-extra.md and optionally
    resource_schema.yaml) into ``presets/<id>/`` from that blueprint.

    Previously this delegated to ``_render_files_from_blueprint`` below,
    which only writes *stubs* and intentionally never overwrites existing
    files. The result: ``run_phase(preset_id, phase="draft")`` silently
    succeeded without updating era.md / writing-style-extra.md / etc.
    from the freshly-produced blueprint. We now call the real renderer
    in :mod:`genre_extractor.core` so drafting actually drafts.
    """
    core.run_draft(bb, preset_id)
    blueprint = bb.read_yaml("genre_blueprint.yaml") or {}
    preset_dir = config.PRESETS_DIR / preset_id
    core.render_files_from_blueprint(blueprint, out_dir=preset_dir)


def _render_files_from_blueprint(bb: Blackboard, preset_id: str):
    """Deterministic stub filler — ensures the 4 preset files *exist*.

    .. warning:: This is NOT the function you want if you mean "take
       the fresh blueprint and materialise it to disk". For that, use
       ``src.genre_extractor.core.render_files_from_blueprint(blueprint,
       out_dir=...)``, which actually reads ``blueprint['era']['content']``
       etc. and writes them.

    This legacy helper only fills missing placeholders and never
    overwrites real content — it's used by :func:`fill_preset` to seed
    an empty preset directory with writable stubs so authors / the
    Validator have something to work with. ``_run_draft`` no longer
    calls it.
    """
    preset_dir = config.PRESETS_DIR / preset_id
    preset_dir.mkdir(parents=True, exist_ok=True)
    # Only fill stubs that don't exist; never overwrite real content.
    ctx = dict(
        preset_id=preset_id,
        display_name=preset_id,
        genre="TBD", era="TBD", tone="TBD",
    )
    for fname, tmpl in (
        ("genre.yaml", STUB_GENRE_YAML),
        ("era.md", STUB_ERA),
        ("writing-style-extra.md", STUB_WRITING_STYLE),
        ("iron-laws-extra.md", STUB_IRON_LAWS),
    ):
        if not (preset_dir / fname).exists():
            (preset_dir / fname).write_text(tmpl.format(**ctx), encoding="utf-8")


def _run_validate(
    bb: Blackboard,
    preset_id: str,
    *,
    with_trial: bool,
    max_fix_retries: int = 2,
    files_dir: Path | None = None,
):
    """Run Validator Stages 1+2, then Fixer retry loop up to `max_fix_retries` times.

    Mirrors the novel pipeline's Evaluator→Fixer ≤2 retry pattern (Lesson 4):
      attempt 0: validate → if only info/warning: done
                           if any error: Fixer
      attempt 1: validate → same check → Fixer
      attempt 2: validate → if still error: ship_with_debt to genre_debt.jsonl

    Stage 3 (trial) runs only at the end if with_trial=True.

    When ``files_dir`` is supplied, Validator / Fixer / setting_lint all read
    and write against that directory; otherwise the legacy behaviour applies
    (``PRESETS_DIR / preset_id``). This keeps ``audit_preset`` / ``run_phase``
    callers unchanged while letting ``extract_to_project`` / ``extract_to_preset``
    point at arbitrary scope directories.
    """
    from src.genre_extractor.agents.validator import GenreValidator

    # Defensive: extract_to_project / extract_to_preset may call us right
    # after run_draft without a build_status.yaml (the run_draft path
    # doesn't always seed one when called via the book-centric entry points).
    # Without this, update_phase_status would KeyError / FileNotFoundError
    # and the whole validate phase would be reported as failed.
    if not bb.exists("build_status.yaml"):
        bb.write_yaml(
            "build_status.yaml",
            schemas.make_initial_build_status(
                genre_id=preset_id,
                entry="validate",
                novel_sources=[],
            ),
        )

    schemas.update_phase_status(bb, phase="validate", status="in_progress")

    final_errors: list = []
    for attempt in range(max_fix_retries + 1):
        # Clear prior issues for a fresh pass (keep the log on disk as history
        # via audit-trail elsewhere; here we care about the *latest* verdict).
        bb.write_text("genre_issues.jsonl", "")

        # Stage 1: structural (setting_lint)
        _run_setting_lint(bb, preset_id, files_dir=files_dir)

        # Stage 2: semantic
        try:
            GenreValidator().run(bb, genre_id=preset_id, files_dir=files_dir)
        except Exception as e:
            bb.append_jsonl("genre_issues.jsonl", {
                "severity": "warning",
                "file": "(validator)",
                "message": f"Stage 2 failed: {type(e).__name__}: {e}",
                "genre_id": preset_id,
            })

        issues = bb.read_jsonl("genre_issues.jsonl")
        final_errors = [i for i in issues if i.get("severity") == "error"]

        if not final_errors:
            break  # clean — no need to fix

        if attempt < max_fix_retries:
            # Ask Fixer to patch the offending files, one file at a time.
            _apply_fixer_round(bb, preset_id, final_errors, files_dir=files_dir)
        # else: will fall through to ship_with_debt below

    if final_errors:
        # Lesson 4: ship with debt rather than loop forever.
        bb.append_jsonl("genre_debt.jsonl", {
            "ts": time.time(),
            "genre_id": preset_id,
            "retries_used": max_fix_retries,
            "unresolved_errors": final_errors,
        })

    # Stage 3: trial (optional), runs after the fix loop stabilized (or gave up)
    if with_trial:
        from src.genre_extractor import trial
        trial.run_trial(preset_id, bb)

    schemas.update_phase_status(bb, phase="validate", status="done")


def _apply_fixer_round(
    bb: Blackboard,
    preset_id: str,
    errors: list,
    *,
    files_dir: Path | None = None,
) -> None:
    """Group errors by file, invoke GenreFixer once per file.

    Fixer silently skips files that can't be resolved from `file` metadata
    (e.g. "(validator)", "(structure)") — those are not individual files.
    """
    from src.genre_extractor.agents.fixer import GenreFixer

    by_file: dict[str, list] = {}
    for issue in errors:
        fname = issue.get("file", "")
        if not fname or fname.startswith("("):
            continue  # meta-issue, no file to patch
        by_file.setdefault(fname, []).append(issue)

    if not by_file:
        return

    fixer = GenreFixer()
    for fname, file_issues in by_file.items():
        try:
            fixer.run(
                bb,
                genre_id=preset_id,
                file_name=fname,
                issues=file_issues,
                files_dir=files_dir,
            )
        except Exception as e:
            bb.append_jsonl("genre_issues.jsonl", {
                "severity": "warning",
                "file": fname,
                "message": f"Fixer failed on {fname}: {type(e).__name__}: {e}",
                "genre_id": preset_id,
            })


def _run_setting_lint(
    bb: Blackboard,
    preset_id: str,
    *,
    files_dir: Path | None = None,
):
    """Call setting_lint and translate its LintReport to genre_issues.

    If ``files_dir`` points at ``projects/<book_id>/``, we route to
    ``lint_project(book_id)`` instead of ``lint_preset(preset_id)``. Otherwise
    the legacy preset-centric path applies.
    """
    from src.tools import setting_lint

    try:
        if files_dir is not None:
            # Detect whether the directory lives under PROJECTS_DIR — if so,
            # lint as a project; otherwise treat it as a preset-shaped directory.
            report = _lint_scope(files_dir, preset_id)
        else:
            report = setting_lint.lint_genre(preset_id)
    except Exception as e:
        bb.append_jsonl("genre_issues.jsonl", {
            "severity": "warning",
            "file": "(setting_lint)",
            "message": f"setting_lint failed: {type(e).__name__}: {e}",
            "genre_id": preset_id,
        })
        return

    # LintReport.issues is a list of LintIssue(level, file, message)
    for issue in report.issues:
        level_map = {"ERROR": "error", "WARNING": "warning", "INFO": "info"}
        bb.append_jsonl("genre_issues.jsonl", {
            "severity": level_map.get(issue.level, "info"),
            "file": issue.file,
            "message": issue.message,
            "genre_id": preset_id,
            "source": "setting_lint",
        })


def _lint_scope(files_dir: Path, scope_id: str):
    """Dispatch lint_project / lint_preset based on where ``files_dir`` lives.

    Falls back to ``lint_preset(scope_id)`` if the directory can't be mapped
    to a known PROJECTS_DIR entry.
    """
    from src.tools import setting_lint

    try:
        rel = files_dir.resolve().relative_to(config.PROJECTS_DIR.resolve())
        # rel.parts[0] is the book_id
        book_id = rel.parts[0] if rel.parts else scope_id
        return setting_lint.lint_project(book_id)
    except (ValueError, IndexError):
        return setting_lint.lint_preset(scope_id)


def fill_preset(preset_id: str) -> dict:
    """Detect missing files and fill with stubs. v1: no LLM."""
    preset_dir = config.PRESETS_DIR / preset_id
    if not preset_dir.exists():
        raise FileNotFoundError(f"preset not found: {preset_id}")
    missing = []
    ctx = dict(preset_id=preset_id, display_name=preset_id, genre="TBD", era="TBD", tone="TBD")
    for fname, stub_template in (
        ("genre.yaml", STUB_GENRE_YAML),
        ("era.md", STUB_ERA),
        ("writing-style-extra.md", STUB_WRITING_STYLE),
        ("iron-laws-extra.md", STUB_IRON_LAWS),
    ):
        if not (preset_dir / fname).exists():
            missing.append(fname)
            (preset_dir / fname).write_text(
                stub_template.format(**ctx), encoding="utf-8",
            )
    return {"ok": True, "preset_id": preset_id, "filled": missing}


def audit_preset(preset_id: str) -> dict:
    """Run Validator stages 1 + 2. Returns summary."""
    # Fail fast on unknown presets — `_build_bb` below would otherwise
    # silently `mkdir` a brand-new `.build/` under a non-existent preset
    # and report a clean "ok" verdict on an empty directory.
    preset_dir = config.PRESETS_DIR / preset_id
    if not preset_dir.exists():
        raise FileNotFoundError(f"preset not found: {preset_id}")
    bb = _build_bb(preset_id)
    # Ensure a build_status exists so helpers work; if not, create a minimal one.
    if not bb.exists("build_status.yaml"):
        bb.write_yaml(
            "build_status.yaml",
            schemas.make_initial_build_status(
                genre_id=preset_id, entry="audit-preset", novel_sources=[],
            ),
        )
    _run_validate(bb, preset_id, with_trial=False)
    issues = bb.read_jsonl("genre_issues.jsonl")
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    return {
        "ok": len(errors) == 0,
        "preset_id": preset_id,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def run_phase(preset_id: str, *, phase: str, with_trial: bool = False) -> dict:
    """Intent-router entry: rerun a single phase. Build status must already exist."""
    # Fail fast on unknown presets — same reasoning as audit_preset:
    # _build_bb would silently mkdir under a non-existent preset.
    preset_dir = config.PRESETS_DIR / preset_id
    if not preset_dir.exists():
        raise FileNotFoundError(f"preset not found: {preset_id}")
    bb = _build_bb(preset_id)
    if not bb.exists("build_status.yaml"):
        raise FileNotFoundError(
            f"no build_status.yaml for {preset_id}; run --to-preset first"
        )
    if phase == "extract":
        # Requires re-reading the source novels — look them up in build_status
        status = bb.read_yaml("build_status.yaml")
        source_streams: list[tuple[ChapterStream, int]] = []
        for src in status.get("novel_sources", []):
            p = Path(src["path"])
            if p.exists():
                stream = ChapterStream(p)
                source_streams.append((stream, src["batch_size"]))
        # Guard: silently succeeding on zero streams gives users a false
        # "ok" and stalls the funnel. If build_status has no resolvable
        # sources, tell the caller clearly rather than write zero batches
        # and mark the phase done.
        if not source_streams:
            raise ValueError(
                f"preset {preset_id} has no resolvable novel_sources in "
                f"build_status.yaml; run --to-preset first to seed it"
            )
        _run_extract(bb, source_streams)
    elif phase == "merge":
        _run_merge(bb)
    elif phase == "draft":
        _run_draft(bb, preset_id)
    elif phase == "validate":
        _run_validate(bb, preset_id, with_trial=with_trial)
    else:
        raise ValueError(f"unknown phase: {phase}")
    return {"ok": True, "preset_id": preset_id, "phase": phase}
