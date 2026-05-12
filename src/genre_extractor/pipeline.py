"""Genre pipeline orchestrator.

Four entry points:
- new_genre(genre_id, ...): stub scaffold, no LLM
- fill_genre(genre_id): detect missing files, call Drafter to fill
- audit_genre(genre_id): Validator stages 1 + 2 (no LLM for stage 1)
- extract_from_novel(genre_id, sources, with_trial): full pipeline

The build workspace lives at genres/<id>/.build/ and is git-ignored.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from src import config
from src.core.blackboard import Blackboard
from src.genre_extractor import adaptive, chapter_detector, core, schemas
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


STUB_GENRE_YAML = """# Genre: {genre_id}
id: {genre_id}
display_name: "{display_name}"
locale: zh-Hans
genre: "{genre}"
era: "{era}"
tone: "{tone}"

author_persona_hints: []
genre_avoid: []
prohibited_styles: []
"""

STUB_ERA = """# Era · {genre_id}

（占位：此文件描述 {era} 的时代事实。由后续题材流水线的 Drafter 填充，
或作者手工编写。至少 500 字才能通过 setting_lint。）
"""

STUB_WRITING_STYLE = """# Writing Style Extra · {genre_id}

（占位：此文件描述 {genre_id} 题材特有的风格规范。至少 300 字才能通过 setting_lint。）
"""

STUB_IRON_LAWS = """# Iron Laws Extra · {genre_id}

## iron_law_extra_1: （占位规则一）

（至少 3 条 iron_law_extra_N 才能通过 setting_lint。）

## iron_law_extra_2: （占位规则二）

## iron_law_extra_3: （占位规则三）
"""


def _build_dir(genre_id: str) -> Path:
    return config.GENRES_DIR / genre_id / ".build"


def _build_bb(genre_id: str) -> Blackboard:
    bd = _build_dir(genre_id)
    bd.mkdir(parents=True, exist_ok=True)
    return Blackboard(root=bd)


def new_genre(
    genre_id: str,
    *,
    display_name: str = "",
    genre: str = "",
    era: str = "",
    tone: str = "",
) -> dict:
    """Create a minimal scaffold under genres/<id>/. No LLM call."""
    genre_dir = config.GENRES_DIR / genre_id
    if genre_dir.exists():
        raise FileExistsError(f"Genre already exists: {genre_dir}")
    genre_dir.mkdir(parents=True)

    ctx = dict(
        genre_id=genre_id,
        display_name=display_name or genre_id,
        genre=genre or "TBD",
        era=era or "TBD",
        tone=tone or "TBD",
    )
    (genre_dir / "genre.yaml").write_text(STUB_GENRE_YAML.format(**ctx), encoding="utf-8")
    (genre_dir / "era.md").write_text(STUB_ERA.format(**ctx), encoding="utf-8")
    (genre_dir / "writing-style-extra.md").write_text(
        STUB_WRITING_STYLE.format(**ctx), encoding="utf-8"
    )
    (genre_dir / "iron-laws-extra.md").write_text(
        STUB_IRON_LAWS.format(**ctx), encoding="utf-8"
    )

    bb = _build_bb(genre_id)
    bb.write_yaml(
        "build_status.yaml",
        schemas.make_initial_build_status(genre_id=genre_id, entry="new-genre"),
    )
    return {"ok": True, "genre_id": genre_id, "path": str(genre_dir)}


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


def extract_from_novel(
    genre_id: str,
    *,
    sources: list[str],
    with_trial: bool = False,
    dry_run: bool = False,
) -> dict:
    """End-to-end extract -> merge -> draft -> validate.

    Each phase updates build_status.yaml. Can be resumed mid-phase via
    --extract-only / --merge-only etc.

    dry_run: don't actually call LLM; just set up status and noop stages.
    Used by CLI tests.
    """
    genre_dir = config.GENRES_DIR / genre_id
    genre_dir.mkdir(parents=True, exist_ok=True)

    bb = _build_bb(genre_id)

    # Count chapters per source. ChapterStream uses a streaming index for
    # files >= 5MB so we never load multi-MB novels fully into memory.
    novel_sources = []
    # Each entry: (ChapterStream, batch_size).
    source_streams: list[tuple[ChapterStream, int]] = []
    for src in sources:
        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(f"source novel not found: {src}")
        stream = ChapterStream(p)
        total_ch = stream.total_chapters
        bs = adaptive.adaptive_batch_size(total_ch)
        novel_sources.append(
            {"path": str(p), "total_chapters": total_ch, "batch_size": bs}
        )
        source_streams.append((stream, bs))

    # Fresh build_status
    status = schemas.make_initial_build_status(
        genre_id=genre_id,
        entry="extract-from-novel",
        novel_sources=novel_sources,
    )
    bb.write_yaml("build_status.yaml", status)

    if dry_run:
        # Mark all phases done without LLM
        for phase in ("extract", "merge", "draft", "validate"):
            schemas.update_phase_status(bb, phase=phase, status="done")
        return {
            "ok": True,
            "mode": "dry_run",
            "genre_id": genre_id,
            "sources": novel_sources,
            "with_trial": with_trial,
        }

    # --- Phase 1: Extract ---
    _run_extract(bb, source_streams)

    # --- Phase 2: Merge ---
    _run_merge(bb)

    # --- Phase 3: Draft ---
    _run_draft(bb, genre_id)

    # --- Phase 4: Validate ---
    _run_validate(bb, genre_id, with_trial=with_trial)

    return {
        "ok": True,
        "genre_id": genre_id,
        "phases": bb.read_yaml("build_status.yaml")["phases"],
        "with_trial": with_trial,
    }


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


def _run_draft(bb: Blackboard, genre_id: str):
    """Populate the blueprint via ``core.run_draft`` then render files into
    ``genres/<id>/`` (the legacy preset location). New callers that want
    custom output should use ``core.run_draft`` + ``core.render_files_from_blueprint``
    directly.
    """
    core.run_draft(bb, genre_id)
    _render_files_from_blueprint(bb, genre_id)


def _render_files_from_blueprint(bb: Blackboard, genre_id: str):
    """Deterministic template fill. v1 = only ensure the 4 stubs exist.

    Production rendering (reading blueprint.era_observations -> era.md paragraphs,
    blueprint.iron_law_candidates -> iron_law_extra_N sections) is deferred to
    a follow-up iteration so v1 can focus on schema plumbing.
    """
    genre_dir = config.GENRES_DIR / genre_id
    genre_dir.mkdir(parents=True, exist_ok=True)
    # Only fill stubs that don't exist; never overwrite real content.
    ctx = dict(
        genre_id=genre_id,
        display_name=genre_id,
        genre="TBD", era="TBD", tone="TBD",
    )
    for fname, tmpl in (
        ("genre.yaml", STUB_GENRE_YAML),
        ("era.md", STUB_ERA),
        ("writing-style-extra.md", STUB_WRITING_STYLE),
        ("iron-laws-extra.md", STUB_IRON_LAWS),
    ):
        if not (genre_dir / fname).exists():
            (genre_dir / fname).write_text(tmpl.format(**ctx), encoding="utf-8")


def _run_validate(bb: Blackboard, genre_id: str, *, with_trial: bool,
                  max_fix_retries: int = 2):
    """Run Validator Stages 1+2, then Fixer retry loop up to `max_fix_retries` times.

    Mirrors the novel pipeline's Evaluator→Fixer ≤2 retry pattern (Lesson 4):
      attempt 0: validate → if only info/warning: done
                           if any error: Fixer
      attempt 1: validate → same check → Fixer
      attempt 2: validate → if still error: ship_with_debt to genre_debt.jsonl

    Stage 3 (trial) runs only at the end if with_trial=True.
    """
    from src.genre_extractor.agents.validator import GenreValidator

    schemas.update_phase_status(bb, phase="validate", status="in_progress")

    final_errors: list = []
    for attempt in range(max_fix_retries + 1):
        # Clear prior issues for a fresh pass (keep the log on disk as history
        # via audit-trail elsewhere; here we care about the *latest* verdict).
        bb.write_text("genre_issues.jsonl", "")

        # Stage 1: structural (setting_lint)
        _run_setting_lint(bb, genre_id)

        # Stage 2: semantic
        try:
            GenreValidator().run(bb, genre_id=genre_id)
        except Exception as e:
            bb.append_jsonl("genre_issues.jsonl", {
                "severity": "warning",
                "file": "(validator)",
                "message": f"Stage 2 failed: {type(e).__name__}: {e}",
                "genre_id": genre_id,
            })

        issues = bb.read_jsonl("genre_issues.jsonl")
        final_errors = [i for i in issues if i.get("severity") == "error"]

        if not final_errors:
            break  # clean — no need to fix

        if attempt < max_fix_retries:
            # Ask Fixer to patch the offending files, one file at a time.
            _apply_fixer_round(bb, genre_id, final_errors)
        # else: will fall through to ship_with_debt below

    if final_errors:
        # Lesson 4: ship with debt rather than loop forever.
        bb.append_jsonl("genre_debt.jsonl", {
            "ts": time.time(),
            "genre_id": genre_id,
            "retries_used": max_fix_retries,
            "unresolved_errors": final_errors,
        })

    # Stage 3: trial (optional), runs after the fix loop stabilized (or gave up)
    if with_trial:
        from src.genre_extractor import trial
        trial.run_trial(genre_id, bb)

    schemas.update_phase_status(bb, phase="validate", status="done")


def _apply_fixer_round(bb: Blackboard, genre_id: str, errors: list) -> None:
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
            fixer.run(bb, genre_id=genre_id, file_name=fname, issues=file_issues)
        except Exception as e:
            bb.append_jsonl("genre_issues.jsonl", {
                "severity": "warning",
                "file": fname,
                "message": f"Fixer failed on {fname}: {type(e).__name__}: {e}",
                "genre_id": genre_id,
            })


def _run_setting_lint(bb: Blackboard, genre_id: str):
    """Call setting_lint.lint_genre and translate its LintReport to genre_issues."""
    from src.tools import setting_lint

    try:
        report = setting_lint.lint_genre(genre_id)
    except Exception as e:
        bb.append_jsonl("genre_issues.jsonl", {
            "severity": "warning",
            "file": "(setting_lint)",
            "message": f"setting_lint failed: {type(e).__name__}: {e}",
            "genre_id": genre_id,
        })
        return

    # LintReport.issues is a list of LintIssue(level, file, message)
    for issue in report.issues:
        level_map = {"ERROR": "error", "WARNING": "warning", "INFO": "info"}
        bb.append_jsonl("genre_issues.jsonl", {
            "severity": level_map.get(issue.level, "info"),
            "file": issue.file,
            "message": issue.message,
            "genre_id": genre_id,
            "source": "setting_lint",
        })


def fill_genre(genre_id: str) -> dict:
    """Detect missing files and fill with stubs. v1: no LLM."""
    genre_dir = config.GENRES_DIR / genre_id
    if not genre_dir.exists():
        raise FileNotFoundError(f"genre not found: {genre_id}")
    missing = []
    ctx = dict(genre_id=genre_id, display_name=genre_id, genre="TBD", era="TBD", tone="TBD")
    for fname, stub_template in (
        ("genre.yaml", STUB_GENRE_YAML),
        ("era.md", STUB_ERA),
        ("writing-style-extra.md", STUB_WRITING_STYLE),
        ("iron-laws-extra.md", STUB_IRON_LAWS),
    ):
        if not (genre_dir / fname).exists():
            missing.append(fname)
            (genre_dir / fname).write_text(
                stub_template.format(**ctx), encoding="utf-8",
            )
    return {"ok": True, "genre_id": genre_id, "filled": missing}


def audit_genre(genre_id: str) -> dict:
    """Run Validator stages 1 + 2. Returns summary."""
    bb = _build_bb(genre_id)
    # Ensure a build_status exists so helpers work; if not, create a minimal one.
    if not bb.exists("build_status.yaml"):
        bb.write_yaml(
            "build_status.yaml",
            schemas.make_initial_build_status(
                genre_id=genre_id, entry="audit-genre", novel_sources=[],
            ),
        )
    _run_validate(bb, genre_id, with_trial=False)
    issues = bb.read_jsonl("genre_issues.jsonl")
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    return {
        "ok": len(errors) == 0,
        "genre_id": genre_id,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def run_phase(genre_id: str, *, phase: str, with_trial: bool = False) -> dict:
    """Intent-router entry: rerun a single phase. Build status must already exist."""
    bb = _build_bb(genre_id)
    if not bb.exists("build_status.yaml"):
        raise FileNotFoundError(
            f"no build_status.yaml for {genre_id}; run --extract-from-novel first"
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
        _run_extract(bb, source_streams)
    elif phase == "merge":
        _run_merge(bb)
    elif phase == "draft":
        _run_draft(bb, genre_id)
    elif phase == "validate":
        _run_validate(bb, genre_id, with_trial=with_trial)
    else:
        raise ValueError(f"unknown phase: {phase}")
    return {"ok": True, "genre_id": genre_id, "phase": phase}
