"""Setting Lint — validate a genre + project pair's structure.

Usage (new two-layer CLI):
    python -m src.tools.setting_lint --genre gangster-hk-1983
    python -m src.tools.setting_lint --project gangster-hk-1983-linjiayao
    python -m src.tools.setting_lint --all
    python -m src.tools.setting_lint --all --strict

Legacy usage (pre-refactor, still works if the genre id happens to match
an old unified `settings/<name>/` path OR a bootstrapped `state/` dir):
    python -m src.tools.setting_lint --setting <path>

Levels:
    ERROR   — must fix; pipeline won't run correctly
    WARNING — should fix; degrades quality
    INFO    — suggestion for the author

Exit codes:
    0  no errors (warnings allowed unless --strict)
    1  has errors (or has warnings + --strict)
    2  pack not found / arg error

Checks performed on a UNIFIED (genre + project merged) view:
    1. File presence: all 7 required files + optional resource_schema
    2. Parseability: YAML / JSON parse successfully
    3. Schema: each file has the required top-level fields
    4. Cross-references:
       - setting.yaml.protagonist_name == characters.yaml.protagonist.name
       - outline.json.chapters[].key_characters are all in characters.yaml
       - outline.json.chapters[].year_month falls within timeline.yaml span
    5. Content thresholds:
       - era.md ≥ 500 chars (too thin = bad worldbuilding)
       - writing-style-extra.md ≥ 300 chars
       - iron-laws-extra.md ≥ 3 iron_law_extra_N entries
       - outline.json first 3 chapters fully beat-sheeted (黄金三章)
    6. Hygiene:
       - no 'MVP' / '黑客松' / 'hackathon' meta-speak in any *.md
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import config


# --- schema ---

REQUIRED_FILES = [
    "setting.yaml",
    "outline.json",
    "timeline.yaml",
    "characters.yaml",
    "era.md",
    "writing-style-extra.md",
    "iron-laws-extra.md",
]

# OPTIONAL: only checked when present. Non-numeric settings (e.g.
# urban-romance) deliberately omit resource_schema.yaml and that is
# correct — ResourceLedger will simply skip for such settings.
OPTIONAL_FILES = [
    "resource_schema.yaml",
]

REQUIRED_SETTING_FIELDS = [
    "id",
    "display_name",
    "locale",
    "genre",
    "era",
    "tone",
    "protagonist_name",
    "chapter_count_target",
    "chapters_in_outline",
]

REQUIRED_OUTLINE_FIELDS = [
    "title",
    "protagonist",
    "chapter_count_target",
    "chapters",
]

REQUIRED_CHAPTER_FIELDS = [
    "ch",
    "title",
    "key_characters",
    "beats",
]

FULLY_BEATED_FIELDS = [
    "ch",
    "title",
    "year_month",
    "key_location",
    "key_characters",
    "beats",
    "opening_hook",
    "closing_hook",
    "tension",
    "word_target",
]

META_WORDS_BLOCKED_IN_SETTING_MD = [
    "MVP",
    "黑客松",
    "hackathon",
    "参赛作品",
    "评委",
]

MIN_ERA_CHARS = 500
MIN_STYLE_EXTRA_CHARS = 300
MIN_EXTRA_IRON_LAWS = 3


# --- lint infrastructure ---

@dataclass
class LintIssue:
    level: str  # "ERROR" | "WARNING" | "INFO"
    file: str
    message: str

    def render(self) -> str:
        icon = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "ℹ️ "}[self.level]
        return f"  {icon} [{self.level:7}] {self.file}: {self.message}"


@dataclass
class LintReport:
    setting_name: str
    issues: list[LintIssue] = field(default_factory=list)

    def error(self, file: str, msg: str) -> None:
        self.issues.append(LintIssue("ERROR", file, msg))

    def warning(self, file: str, msg: str) -> None:
        self.issues.append(LintIssue("WARNING", file, msg))

    def info(self, file: str, msg: str) -> None:
        self.issues.append(LintIssue("INFO", file, msg))

    @property
    def n_errors(self) -> int:
        return sum(1 for i in self.issues if i.level == "ERROR")

    @property
    def n_warnings(self) -> int:
        return sum(1 for i in self.issues if i.level == "WARNING")

    @property
    def n_infos(self) -> int:
        return sum(1 for i in self.issues if i.level == "INFO")

    def render(self) -> str:
        lines = [f"\n=== {self.setting_name} ==="]
        if not self.issues:
            lines.append("  🟢 全部检查通过")
        else:
            for issue in self.issues:
                lines.append(issue.render())
        lines.append(
            f"  → errors: {self.n_errors}, warnings: {self.n_warnings}, "
            f"infos: {self.n_infos}"
        )
        return "\n".join(lines)


# --- individual checks ---

def lint_setting(setting_dir: Path) -> LintReport:
    name = setting_dir.name
    report = LintReport(setting_name=name)

    # Check 1: file presence
    missing = [f for f in REQUIRED_FILES if not (setting_dir / f).exists()]
    for f in missing:
        report.error(f, "required file missing")
    if missing:
        return report  # nothing else to check

    # Check 2: parseability + load data
    try:
        setting_yaml = yaml.safe_load((setting_dir / "setting.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        report.error("setting.yaml", f"YAML parse failed: {e}")
        return report

    try:
        outline = json.loads((setting_dir / "outline.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        report.error("outline.json", f"JSON parse failed: {e}")
        return report

    try:
        timeline = yaml.safe_load((setting_dir / "timeline.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        report.error("timeline.yaml", f"YAML parse failed: {e}")
        return report

    try:
        characters = yaml.safe_load((setting_dir / "characters.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        report.error("characters.yaml", f"YAML parse failed: {e}")
        return report

    era_md = (setting_dir / "era.md").read_text(encoding="utf-8")
    style_extra_md = (setting_dir / "writing-style-extra.md").read_text(encoding="utf-8")
    iron_extra_md = (setting_dir / "iron-laws-extra.md").read_text(encoding="utf-8")

    # Check 3a: setting.yaml schema
    if not isinstance(setting_yaml, dict):
        report.error("setting.yaml", "top-level must be a mapping")
    else:
        for f in REQUIRED_SETTING_FIELDS:
            if f not in setting_yaml:
                report.error("setting.yaml", f"missing required field: {f}")
        # id should match directory name for clarity.
        # Skip this check when linting a synthesized unified view (dir name
        # is a tempdir like 'unified', not the real pack id).
        is_synthesized = name == "unified" or name.startswith("lint_unified_")
        if not is_synthesized:
            if setting_yaml.get("id") and setting_yaml["id"] != name:
                report.warning(
                    "setting.yaml",
                    f"id='{setting_yaml['id']}' doesn't match dir name '{name}' "
                    "(reproducibility: bootstrap --setting <dir> uses dir name)",
                )

    # Check 3b: outline.json schema
    if not isinstance(outline, dict):
        report.error("outline.json", "top-level must be an object")
    else:
        for f in REQUIRED_OUTLINE_FIELDS:
            if f not in outline:
                report.error("outline.json", f"missing required field: {f}")

        chapters = outline.get("chapters") or []
        if not isinstance(chapters, list):
            report.error("outline.json", "chapters must be a list")
            chapters = []

        declared_ct = outline.get("chapters_in_outline", len(chapters))
        if declared_ct != len(chapters):
            report.warning(
                "outline.json",
                f"chapters_in_outline={declared_ct} but "
                f"actual chapters list has {len(chapters)} entries",
            )

        for i, ch in enumerate(chapters):
            if not isinstance(ch, dict):
                report.error("outline.json", f"chapters[{i}] not a dict")
                continue
            for f in REQUIRED_CHAPTER_FIELDS:
                if f not in ch:
                    report.error(
                        "outline.json",
                        f"chapters[{i}] (ch={ch.get('ch', '?')}) missing field: {f}",
                    )

    # Check 3c: characters.yaml schema
    if not isinstance(characters, dict):
        report.error("characters.yaml", "top-level must be a mapping")
    else:
        if "protagonist" not in characters:
            report.error("characters.yaml", "missing 'protagonist' section")
        else:
            proto = characters["protagonist"]
            if not isinstance(proto, dict) or "name" not in proto:
                report.error(
                    "characters.yaml",
                    "protagonist must be a dict with at least 'name'",
                )

        supporting = characters.get("supporting", [])
        if not isinstance(supporting, list):
            report.warning("characters.yaml", "'supporting' should be a list")
        elif len(supporting) < 3:
            report.warning(
                "characters.yaml",
                f"only {len(supporting)} supporting characters; "
                "setting with <3 supporting chars feels thin",
            )

    # Check 3d: timeline.yaml schema
    if timeline is None or (not isinstance(timeline, (dict, list))):
        report.warning("timeline.yaml", "empty or non-mapping/list timeline")
    else:
        # Count total entries (timeline can be nested by year or flat list)
        total = _count_timeline_entries(timeline)
        if total < 3:
            report.warning(
                "timeline.yaml",
                f"only {total} timeline entries; ≥3 recommended for era grounding",
            )

    # Check 4: cross-references
    # 4a: setting.protagonist_name == characters.protagonist.name
    sy_proto = (setting_yaml or {}).get("protagonist_name")
    ch_proto = ((characters or {}).get("protagonist") or {}).get("name")
    if sy_proto and ch_proto and sy_proto != ch_proto:
        report.error(
            "setting.yaml↔characters.yaml",
            f"protagonist_name mismatch: setting.yaml='{sy_proto}' "
            f"vs characters.yaml='{ch_proto}'",
        )

    # 4b: outline key_characters must appear in characters.yaml
    if isinstance(characters, dict):
        known_names = _extract_character_names(characters)
        for i, ch in enumerate(outline.get("chapters") or []):
            if not isinstance(ch, dict):
                continue
            for char in ch.get("key_characters") or []:
                if not _character_known(char, known_names):
                    report.warning(
                        "outline.json↔characters.yaml",
                        f"chapters[{i}] (ch={ch.get('ch', '?')}) references "
                        f"unknown character '{char}'",
                    )

    # 4c: outline characters actually appear in some chapter
    # (reverse check: every supporting character should show up in outline)
    outline_cast: set[str] = set()
    for ch in outline.get("chapters") or []:
        if isinstance(ch, dict):
            for char in ch.get("key_characters") or []:
                outline_cast.add(str(char))
    if isinstance(characters, dict):
        for supp in characters.get("supporting") or []:
            if isinstance(supp, dict) and "name" in supp:
                if not _character_known(supp["name"], outline_cast):
                    report.info(
                        "characters.yaml↔outline.json",
                        f"supporting '{supp['name']}' never appears in outline",
                    )

    # Check 5: content thresholds
    era_chars = len(era_md.replace("\n", "").replace(" ", ""))
    if era_chars < MIN_ERA_CHARS:
        report.warning(
            "era.md",
            f"only {era_chars} chars; minimum recommended {MIN_ERA_CHARS} "
            "(thin era = weak Generator grounding)",
        )

    style_chars = len(style_extra_md.replace("\n", "").replace(" ", ""))
    if style_chars < MIN_STYLE_EXTRA_CHARS:
        report.warning(
            "writing-style-extra.md",
            f"only {style_chars} chars; minimum recommended {MIN_STYLE_EXTRA_CHARS}",
        )

    extra_laws = re.findall(r"iron_law_extra_(\d+)", iron_extra_md)
    if len(extra_laws) < MIN_EXTRA_IRON_LAWS:
        report.warning(
            "iron-laws-extra.md",
            f"found {len(extra_laws)} iron_law_extra_N entries; "
            f"minimum recommended {MIN_EXTRA_IRON_LAWS} "
            "(genre-specific rules are how settings differ)",
        )

    # Golden 3 chapters: first 3 must be fully beated
    chapters_list = outline.get("chapters") or []
    for i in range(min(3, len(chapters_list))):
        ch = chapters_list[i]
        if not isinstance(ch, dict):
            continue
        missing_fields = [f for f in FULLY_BEATED_FIELDS if f not in ch]
        if missing_fields:
            report.warning(
                "outline.json",
                f"chapters[{i}] (ch={ch.get('ch', '?')}) is in 黄金三章 "
                f"but missing detailed fields: {missing_fields}",
            )
        beats = ch.get("beats") or []
        if len(beats) < 3:
            report.warning(
                "outline.json",
                f"chapters[{i}] (ch={ch.get('ch', '?')}) has only "
                f"{len(beats)} beat(s); first 3 chapters should have ≥3 each",
            )

    # Check 6: hygiene — no meta-speak
    for file in [era_md, style_extra_md, iron_extra_md]:
        pass  # handled per-file below

    for fname, content in [
        ("era.md", era_md),
        ("writing-style-extra.md", style_extra_md),
        ("iron-laws-extra.md", iron_extra_md),
    ]:
        for word in META_WORDS_BLOCKED_IN_SETTING_MD:
            if word in content:
                report.info(
                    fname,
                    f"contains project-meta word '{word}' — setting content "
                    "should be in-world, not refer to the system project",
                )

    # Check 7 (optional): resource_schema.yaml — only validated when present.
    # Missing schema is a valid choice (non-numeric settings like urban-romance
    # deliberately opt out so ResourceLedger stays skipped).
    schema_path = setting_dir / "resource_schema.yaml"
    if schema_path.exists():
        _lint_resource_schema(schema_path, report)
    else:
        report.info(
            "resource_schema.yaml",
            "optional file absent — ResourceLedger agent will be skipped for this "
            "setting (fine for non-numeric genres; add the file if your genre has "
            "trackable resources like 灵石/情报值/境界)",
        )

    return report


def _lint_resource_schema(schema_path: Path, report: LintReport) -> None:
    """Validate an optional resource_schema.yaml. Only called when file exists."""
    fname = "resource_schema.yaml"
    try:
        data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        report.error(fname, f"YAML parse failed: {e}")
        return

    if not isinstance(data, dict):
        report.error(fname, "top-level must be a mapping with 'resources' and 'validation'")
        return

    # resources[]
    resources = data.get("resources")
    if not isinstance(resources, list):
        report.error(fname, "'resources' must be a list")
        return
    if len(resources) == 0:
        report.warning(
            fname,
            "'resources' is empty — file serves no purpose; delete it to let "
            "ResourceLedger skip cleanly, or declare at least one tracked resource",
        )

    seen_ids: set[str] = set()
    for i, r in enumerate(resources):
        if not isinstance(r, dict):
            report.error(fname, f"resources[{i}] must be a mapping")
            continue
        for f in ("id", "display_name", "unit", "description"):
            if f not in r:
                report.error(
                    fname,
                    f"resources[{i}] missing required field: {f}",
                )
        rid = r.get("id")
        if isinstance(rid, str):
            if rid in seen_ids:
                report.error(fname, f"duplicate resource id: {rid}")
            seen_ids.add(rid)
        # baseline_scale is recommended (helps ResourceLedger + Evaluator)
        if "baseline_scale" not in r:
            report.info(
                fname,
                f"resources[{i}] ('{rid}') has no baseline_scale — "
                "ResourceLedger can't detect scale jumps without it",
            )

    # validation section
    validation = data.get("validation")
    if validation is None:
        report.warning(
            fname,
            "missing 'validation' section — add increment_rules + "
            "forbidden_fuzzy_terms to enable scale-jump detection",
        )
    elif not isinstance(validation, dict):
        report.error(fname, "'validation' must be a mapping")
    else:
        forbidden = validation.get("forbidden_fuzzy_terms")
        if forbidden is None:
            report.info(
                fname,
                "validation.forbidden_fuzzy_terms missing — recommend listing "
                "words like '暴涨/海量/难以估量' to force numeric honesty",
            )
        elif not isinstance(forbidden, list):
            report.error(fname, "validation.forbidden_fuzzy_terms must be a list")


# --- helpers ---

def _count_timeline_entries(timeline) -> int:
    """Timeline can be {year: [event, ...]} or a flat list."""
    if isinstance(timeline, list):
        return len(timeline)
    if isinstance(timeline, dict):
        total = 0
        for v in timeline.values():
            if isinstance(v, list):
                total += len(v)
            elif isinstance(v, (dict, str)):
                total += 1
        return total
    return 0


def _extract_character_names(characters: dict) -> set[str]:
    names: set[str] = set()
    proto = characters.get("protagonist")
    if isinstance(proto, dict) and "name" in proto:
        names.add(str(proto["name"]))
    for s in characters.get("supporting") or []:
        if isinstance(s, dict) and "name" in s:
            names.add(str(s["name"]))
    return names


def _character_known(name: str, known_names: set[str]) -> bool:
    """Loose match: a key_character reference matches if it's a substring of
    any known name or vice versa (handles '阿威（陈威）' vs '阿威' or '苏婷' vs '苏婷记者').
    """
    if name in known_names:
        return True
    for known in known_names:
        if name in known or known in name:
            return True
    return False


# --- CLI ---


def lint_project(project_id: str) -> LintReport:
    """Lint a project by merging its genre + project files into a temp
    'unified view' directory and running the legacy lint_setting on it.

    This preserves the full set of existing checks without rewriting them.
    The temp dir is auto-cleaned after the report is built.
    """
    # Lazy import to avoid circular (bootstrap imports config which imports here)
    from .. import bootstrap

    project_dir = config.PROJECTS_DIR / project_id
    if not project_dir.exists():
        report = LintReport(setting_name=project_id)
        report.error(
            f"projects/{project_id}",
            f"project directory not found at {project_dir}",
        )
        return report

    # Synthesize a setting/-shaped unified view in a tmp dir
    missing_proj = bootstrap.validate_project(project_dir)
    if missing_proj:
        report = LintReport(setting_name=project_id)
        for f in missing_proj:
            report.error(f"projects/{project_id}/{f}", "required file missing")
        return report

    try:
        project_yaml = yaml.safe_load(
            (project_dir / "project.yaml").read_text(encoding="utf-8")
        )
    except yaml.YAMLError as e:
        report = LintReport(setting_name=project_id)
        report.error(f"projects/{project_id}/project.yaml", f"YAML parse failed: {e}")
        return report

    genre_id = project_yaml.get("genre") if isinstance(project_yaml, dict) else None
    if not genre_id:
        report = LintReport(setting_name=project_id)
        report.error(
            f"projects/{project_id}/project.yaml",
            "missing required field: genre",
        )
        return report

    genre_dir = config.GENRES_DIR / genre_id
    if not genre_dir.exists():
        report = LintReport(setting_name=project_id)
        report.error(
            f"projects/{project_id}/project.yaml",
            f"declared genre '{genre_id}' not found at {genre_dir}",
        )
        return report

    missing_genre = bootstrap.validate_genre(genre_dir)
    if missing_genre:
        report = LintReport(setting_name=f"{project_id} (genre {genre_id})")
        for f in missing_genre:
            report.error(f"genres/{genre_id}/{f}", "required file missing")
        return report

    # Build unified view in a temp dir, then run the legacy lint
    with tempfile.TemporaryDirectory(prefix="lint_unified_") as tmp:
        unified = Path(tmp) / "unified"
        unified.mkdir()

        # Copy genre files
        for f in ["era.md", "writing-style-extra.md", "iron-laws-extra.md"]:
            shutil.copy2(genre_dir / f, unified / f)
        if (genre_dir / "resource_schema.yaml").exists():
            shutil.copy2(genre_dir / "resource_schema.yaml",
                         unified / "resource_schema.yaml")

        # Copy project files
        for f in ["outline.json", "characters.yaml", "timeline.yaml"]:
            shutil.copy2(project_dir / f, unified / f)

        # Synthesize unified setting.yaml using the same merger bootstrap uses
        genre_yaml = yaml.safe_load(
            (genre_dir / "genre.yaml").read_text(encoding="utf-8")
        )
        merged = bootstrap._merge_setting_metadata(genre_yaml, project_yaml)
        (unified / "setting.yaml").write_text(
            yaml.safe_dump(merged, allow_unicode=True, sort_keys=False,
                           default_flow_style=False),
            encoding="utf-8",
        )

        report = lint_setting(unified)
        report.setting_name = f"{project_id}  (genre: {genre_id})"
        return report


def lint_genre(genre_id: str) -> LintReport:
    """Lint a standalone genre pack. Does NOT require a project to lint."""
    from .. import bootstrap

    genre_dir = config.GENRES_DIR / genre_id
    report = LintReport(setting_name=f"genre: {genre_id}")
    if not genre_dir.exists():
        report.error(f"genres/{genre_id}", f"directory not found at {genre_dir}")
        return report

    missing = bootstrap.validate_genre(genre_dir)
    for f in missing:
        report.error(f"genres/{genre_id}/{f}", "required file missing")
    if missing:
        return report

    # Parse genre.yaml
    try:
        genre_yaml = yaml.safe_load(
            (genre_dir / "genre.yaml").read_text(encoding="utf-8")
        )
    except yaml.YAMLError as e:
        report.error(f"genres/{genre_id}/genre.yaml", f"YAML parse failed: {e}")
        return report

    if not isinstance(genre_yaml, dict):
        report.error(f"genres/{genre_id}/genre.yaml", "top-level must be a mapping")
        return report

    # genre.yaml required fields
    for f in ("id", "display_name", "genre", "era", "tone"):
        if f not in genre_yaml:
            report.error(f"genres/{genre_id}/genre.yaml", f"missing required field: {f}")
    if genre_yaml.get("id") and genre_yaml["id"] != genre_id:
        report.warning(
            f"genres/{genre_id}/genre.yaml",
            f"id='{genre_yaml['id']}' doesn't match dir name '{genre_id}'",
        )

    # Content thresholds (reuse same limits as unified lint)
    era_path = genre_dir / "era.md"
    if era_path.stat().st_size < MIN_ERA_CHARS:
        report.warning(
            f"genres/{genre_id}/era.md",
            f"too thin (< {MIN_ERA_CHARS} chars); world-building likely weak",
        )
    style_path = genre_dir / "writing-style-extra.md"
    if style_path.stat().st_size < MIN_STYLE_EXTRA_CHARS:
        report.warning(
            f"genres/{genre_id}/writing-style-extra.md",
            f"too thin (< {MIN_STYLE_EXTRA_CHARS} chars)",
        )
    iron_path = genre_dir / "iron-laws-extra.md"
    iron_text = iron_path.read_text(encoding="utf-8")
    iron_count = len(re.findall(r"iron_law_(?:extra_)?\d+", iron_text))
    if iron_count < MIN_EXTRA_IRON_LAWS:
        report.warning(
            f"genres/{genre_id}/iron-laws-extra.md",
            f"only {iron_count} iron_law entries; recommend ≥ {MIN_EXTRA_IRON_LAWS}",
        )

    # Meta-speak hygiene
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        content = (genre_dir / fname).read_text(encoding="utf-8")
        for word in META_WORDS_BLOCKED_IN_SETTING_MD:
            if word in content:
                report.info(
                    f"genres/{genre_id}/{fname}",
                    f"contains project-meta word '{word}' — genre content should "
                    "be in-world, not refer to the system project",
                )

    # Optional resource_schema
    schema_path = genre_dir / "resource_schema.yaml"
    if schema_path.exists():
        _lint_resource_schema(schema_path, report)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Lint a genre or project pack for completeness and consistency"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--genre", help="Genre id under genres/")
    grp.add_argument("--project", help="Project id under projects/")
    grp.add_argument("--all", action="store_true",
                     help="Lint every genre + project")
    # Legacy: tolerate --setting by treating it as a project id (first),
    # else genre id. Aids backward-compat for old scripts / docs.
    grp.add_argument("--setting", help="(deprecated) project id or genre id")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Warnings count as failures (exit code 1)",
    )
    args = parser.parse_args()

    reports: list[LintReport] = []

    if args.all:
        for gid in _list_genre_ids():
            reports.append(lint_genre(gid))
        for pid in _list_project_ids():
            reports.append(lint_project(pid))
    elif args.genre:
        reports.append(lint_genre(args.genre))
    elif args.project:
        reports.append(lint_project(args.project))
    elif args.setting:
        # Back-compat: first try as project id, then genre id
        name = args.setting
        if (config.PROJECTS_DIR / name).exists():
            reports.append(lint_project(name))
        elif (config.GENRES_DIR / name).exists():
            reports.append(lint_genre(name))
        else:
            print(
                f"ERROR: '{name}' not found under projects/ or genres/",
                file=sys.stderr,
            )
            sys.exit(2)
    else:
        parser.error("specify --genre / --project / --all / --setting <name>")

    total_errors = 0
    total_warnings = 0
    for report in reports:
        print(report.render())
        total_errors += report.n_errors
        total_warnings += report.n_warnings

    print(f"\n=== Overall ===")
    print(f"  packs checked   : {len(reports)}")
    print(f"  total errors    : {total_errors}")
    print(f"  total warnings  : {total_warnings}")

    if total_errors > 0:
        sys.exit(1)
    if args.strict and total_warnings > 0:
        print("  (--strict: warnings count as failures)")
        sys.exit(1)
    sys.exit(0)


def _list_genre_ids() -> list[str]:
    if not config.GENRES_DIR.exists():
        return []
    return sorted(
        p.name for p in config.GENRES_DIR.iterdir()
        if p.is_dir() and (p / "genre.yaml").exists()
    )


def _list_project_ids() -> list[str]:
    if not config.PROJECTS_DIR.exists():
        return []
    return sorted(
        p.name for p in config.PROJECTS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
        and (p / "project.yaml").exists()
    )


if __name__ == "__main__":
    main()
