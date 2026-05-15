"""Backfill characters-cast.yaml from existing chapter prose.

Used once on legacy projects (e.g. book-e3f4fc9b) where the pipeline ran
many chapters BEFORE CastUpdater existed. Reads chapters/ch001..chN.md,
runs a SINGLE LLM call (CastUpdater with concatenated prose) to bootstrap
the running演员表, and writes state/characters-cast.yaml.

Usage:
    python -m src.tools.backfill_cast --project <id>
    python -m src.tools.backfill_cast --project <id> --through 30
    python -m src.tools.backfill_cast --project <id> --dry-run     # 不调 LLM

不修改作品目录（projects/<id>/）。只写 state/characters-cast.yaml。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import bootstrap, config
from ..agents.cast_updater import CastUpdater
from ..blackboard import Blackboard


CHUNK_SEP = "\n\n---\n\n"


def _gather_chapters(bb: Blackboard, through: int) -> tuple[str, list[int]]:
    """Concatenate ch001..chN.md, returning (text, list_of_present_chapters)."""
    parts: list[str] = []
    present: list[int] = []
    for n in range(1, through + 1):
        p = f"chapters/ch{n:03d}.md"
        if not bb.exists(p):
            continue
        present.append(n)
        body = bb.read_text(p).strip()
        parts.append(f"# 第 {n} 章\n\n{body}")
    return CHUNK_SEP.join(parts), present


def _resolve_through(project_id: str, requested: int | None) -> int:
    """Default --through = chapter_count_target from project.yaml."""
    if requested is not None:
        return requested
    project_dir = config.PROJECTS_DIR / project_id
    import yaml as _yaml
    pdata = _yaml.safe_load(
        (project_dir / "project.yaml").read_text(encoding="utf-8")
    ) or {}
    return int(pdata.get("chapter_count_target", 50))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill characters-cast.yaml")
    parser.add_argument("--project", required=True, help="project id")
    parser.add_argument(
        "--through",
        type=int,
        default=None,
        help="last chapter to read (default: chapter_count_target)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build prompt + report token estimate; do NOT call LLM",
    )
    args = parser.parse_args(argv)

    # Activate project so STATE_DIR points at the right place.
    try:
        bootstrap.bootstrap_project(args.project, preserve_progress=True)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    bb = Blackboard()
    through = _resolve_through(args.project, args.through)
    concat, present = _gather_chapters(bb, through)

    if not present:
        print(f"No chapter files found under state/chapters/. Nothing to backfill.")
        return 1

    # Synthesize a "fake current chapter" = max(present); we feed all prose
    # into the user prompt slot normally reserved for ONE chapter, with a
    # banner explaining the backfill semantics.
    fake_chapter = present[-1]

    # Re-purpose CastUpdater. We override the chapter-text input by writing
    # to a scratch path the agent will read; cleanest way is to write the
    # concatenated prose to chapters/ch{fake_chapter:03d}.md.bk-tmp and
    # patch the agent. Simpler: build a prompt directly using the same
    # template logic, but flag the input as a multi-chapter blob.
    #
    # Since the agent's _build_prompts reads `chapters/ch{N:03d}.md`, the
    # easiest approach is: write the concat to a scratch file, point the
    # agent at it via monkey-patching read_text. We avoid that by building
    # the prompt manually mirroring CastUpdater._build_prompts but with
    # a custom user message.
    agent = CastUpdater()

    # Reuse CastUpdater's system prompt logic: temporarily write a synthesized
    # "chapter" file at chapters/ch{fake:03d}.md.backfill-blob and call
    # _build_prompts? Too entangled. Just build prompt manually here.
    baseline = bb.read_text("characters.yaml")
    if bb.exists("characters-cast.yaml"):
        prior_cast = bb.read_text("characters-cast.yaml")
        prior_note = "（已存在 cast，将基于此累积更新）"
    else:
        prior_cast = "(首次运行，演员表为空)"
        prior_note = "（首次运行）"

    from ..agents.cast_updater import CAST_SCHEMA_DOC

    system = (
        "你是 cast 维护员。**特殊任务：一次性回填**。\n"
        "本次输入是 ch1..chN 的**全部正文**（用 `---` 分隔），不是单章。\n"
        "你的任务是基于这 N 章累积证据，**一次性产出**完整的 characters-cast.yaml。\n"
        "\n"
        "# 核心规则（与逐章模式一致）\n"
        "\n"
        "1. **新角色识别**：抽具名 + 有台词或行为的角色。不抽路人。\n"
        "2. **基线对照**：在 characters.yaml 里 → `in_baseline: true`；不在 → `false`。\n"
        "3. **first_appeared_ch / last_appeared_ch**：扫所有章节标记，记录该角色的首次/最近出现章号。\n"
        "4. **基线保护**：基线人物的 traits/redlines 只能添加，不能修改。冲突写进 _baseline_drift。\n"
        "5. **永不删除条目**。已退场角色 status=offstage 或 dead，仍保留。\n"
        "6. **不创造正文里没出现的角色**。\n"
        "7. 输出**完整 yaml**，不是 diff。\n"
        "\n"
        "# Schema\n"
        "\n"
        "```yaml\n"
        f"{CAST_SCHEMA_DOC}"
        "```\n"
        "\n"
        "# 输出要求\n"
        "- 严格 yaml，从 `schema_version: 1` 开始。\n"
        "- 不写散文、不写 markdown、不加 ```yaml ``` 围栏。\n"
        f"- `last_updated_chapter: {fake_chapter}`\n"
    )

    user = (
        f"# ch1..ch{fake_chapter} 全部正文（已存在的 {len(present)} 章，事实基准）\n\n"
        f"{concat}\n\n"
        f"# 基线宪法 characters.yaml\n\n```yaml\n{baseline}\n```\n\n"
        f"# 上一版 characters-cast.yaml {prior_note}\n\n```yaml\n{prior_cast}\n```\n\n"
        f"# 任务\n\n"
        f"输出累积版 `characters-cast.yaml`（覆盖式）。`last_updated_chapter: {fake_chapter}`。"
    )

    # Token estimate (rough: 1 token ≈ 1.5 Chinese chars)
    total_chars = len(system) + len(user)
    est_tokens = total_chars // 2  # 保守估
    print(f"Project        : {args.project}")
    print(f"State dir      : {config.STATE_DIR}")
    print(f"Chapters present: {len(present)} (ch{present[0]}..ch{present[-1]})")
    print(f"Total prompt chars: {total_chars}")
    print(f"Estimated tokens : ~{est_tokens}")
    print(f"Output target  : state/characters-cast.yaml")

    if args.dry_run:
        print("\n[DRY-RUN] LLM not called. Prompt built successfully.")
        # Sample the head of the user prompt so the user can sanity-check
        head = user[:600].replace("\n", " ⏎ ")
        print(f"\nPrompt head: {head}...")
        return 0

    # Real call path (kept for future use; per task spec we do NOT trigger it now).
    from .. import llm
    print("\nCalling LLM (this is the real path; consider --dry-run first)...")
    raw = llm.chat(
        system=system,
        user=user,
        agent_name="cast_updater_backfill",
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        response_format="text",
        inputs_read=[
            f"state/chapters/ch{n:03d}.md" for n in present
        ] + ["state/characters.yaml"],
    )
    agent._handle_output(bb, raw, chapter=fake_chapter)
    print(f"✓ Wrote state/characters-cast.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
