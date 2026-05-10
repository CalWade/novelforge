"""Tests for dashboard tool — specifically the Bookkeeping section (C-23..C-25)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools.dashboard import render_md


@pytest.fixture
def minimal_snapshot(tmp_path: Path) -> Path:
    """Build a minimal snapshot dir dashboard can read."""
    # Required inputs
    (tmp_path / "outline.json").write_text(
        json.dumps({
            "title": "Test",
            "protagonist": "Alice",
            "chapters": [{"ch": 1, "title": "t", "key_characters": ["Alice"]}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "setting.yaml").write_text(
        "id: test\ngenre: test\n", encoding="utf-8"
    )
    (tmp_path / "progress.json").write_text(
        json.dumps({"completed_chapters": [], "total_llm_calls": 0}),
        encoding="utf-8",
    )
    (tmp_path / "issues.jsonl").touch()
    (tmp_path / "debt.jsonl").touch()
    (tmp_path / "prompts_log.jsonl").touch()
    (tmp_path / "chapters").mkdir()
    (tmp_path / "summaries").mkdir()
    (tmp_path / "fixes").mkdir()
    return tmp_path


def test_dashboard_reports_missing_bookkeeping_when_none(minimal_snapshot):
    md = render_md(minimal_snapshot)
    assert "Bookkeeping 账本" in md
    # No bookkeeping files = explicit "empty" notice
    assert "当前无 bookkeeping 账本产出" in md or "pre-C-23" in md


def test_dashboard_shows_bookkeeping_files_when_present(minimal_snapshot):
    # Drop in all 4 bookkeeping files with non-trivial content
    (minimal_snapshot / "current_status_card.md").write_text("# 当前状态卡\n\n| a | b |", encoding="utf-8")
    (minimal_snapshot / "pending_hooks.md").write_text("# 待回收伏笔池\n\n| a | b |", encoding="utf-8")
    (minimal_snapshot / "resource_schema.yaml").write_text("resources: []\n", encoding="utf-8")
    (minimal_snapshot / "resource_ledger.md").write_text("# 资源账本\n\n| a | b |", encoding="utf-8")

    md = render_md(minimal_snapshot)
    assert "Bookkeeping 账本" in md
    for fname in (
        "current_status_card.md",
        "pending_hooks.md",
        "resource_schema.yaml",
        "resource_ledger.md",
    ):
        assert f"`{fname}`" in md, f"bookkeeping table should reference {fname}"
    # All four present → ✅ marker appears
    assert "✅" in md


def test_dashboard_hides_resource_ledger_row_when_schema_absent(minimal_snapshot):
    """Non-numeric settings (urban-romance-style) have no schema AND no
    ledger. The ledger row should be silently omitted, not shown as ❌."""
    # Status + hooks exist; schema + ledger both absent
    (minimal_snapshot / "current_status_card.md").write_text("# 当前状态卡", encoding="utf-8")
    (minimal_snapshot / "pending_hooks.md").write_text("# 待回收伏笔池", encoding="utf-8")

    md = render_md(minimal_snapshot)
    # Table present with what IS there
    assert "current_status_card.md" in md
    assert "pending_hooks.md" in md
    # resource_ledger.md is legitimately absent — should not appear as ❌ row
    # (avoid scaring readers of non-numeric-genre snapshots)
    lines = [ln for ln in md.splitlines() if "resource_ledger" in ln]
    if lines:
        # If it does appear, it MUST NOT be marked as a failure
        for ln in lines:
            assert "❌" not in ln, f"resource_ledger.md should not be marked ❌ when schema absent: {ln}"


def test_dashboard_shows_ledger_missing_when_schema_present_but_ledger_absent(minimal_snapshot):
    """Schema exists but ledger missing = real bug (ResourceLedger didn't run).
    Dashboard should surface this as ❌."""
    (minimal_snapshot / "resource_schema.yaml").write_text("resources: []\n", encoding="utf-8")
    md = render_md(minimal_snapshot)
    # resource_ledger.md row should now be present and marked ❌
    ledger_lines = [ln for ln in md.splitlines() if "resource_ledger.md" in ln]
    assert ledger_lines
    assert any("❌" in ln for ln in ledger_lines), (
        "When schema exists but ledger does not, dashboard should mark ledger as missing"
    )


def test_dashboard_section_header_named_clearly(minimal_snapshot):
    md = render_md(minimal_snapshot)
    # Section heading mentions Lesson 3 layer so readers understand the purpose
    assert "## Bookkeeping 账本" in md
    assert "Lesson-3" in md
