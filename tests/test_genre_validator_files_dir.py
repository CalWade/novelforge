"""P0-3 regression: GenreValidator must honour `files_dir` and stop
hard-coding ``config.PRESETS_DIR / genre_id``.

Two temp directories (one posing as a preset, one posing as a project) are
given different era.md content. We call the Tier-1 deny-phrase scan directly
with each files_dir and verify it scans the file actually pointed at.
"""
from __future__ import annotations

from pathlib import Path


def test_tier1_deny_scan_uses_files_dir_not_presets_dir(tmp_path: Path, monkeypatch):
    """Passing files_dir -> scan that dir. Passing a preset_id but no files_dir
    keeps the legacy PRESETS_DIR behaviour (covered by other tests)."""
    from src import config
    from src.genre_extractor.agents.validator import GenreValidator

    preset_dir = tmp_path / "presets" / "pA"
    preset_dir.mkdir(parents=True)
    (preset_dir / "era.md").write_text("clean preset content\n", encoding="utf-8")
    (preset_dir / "writing-style-extra.md").write_text("neutral\n", encoding="utf-8")
    (preset_dir / "iron-laws-extra.md").write_text("neutral\n", encoding="utf-8")

    project_dir = tmp_path / "projects" / "bA"
    project_dir.mkdir(parents=True)
    # Use a deny-phrase that exists in rules/deny-phrases-zh.txt
    (project_dir / "era.md").write_text(
        "这一段写得很含糊，从某种意义上说没有交代清楚。\n", encoding="utf-8",
    )
    (project_dir / "writing-style-extra.md").write_text("\n", encoding="utf-8")
    (project_dir / "iron-laws-extra.md").write_text("\n", encoding="utf-8")

    # Don't touch PRESETS_DIR globally — we're explicitly passing files_dir so
    # the scanner must use that, not config.PRESETS_DIR / genre_id.
    v = GenreValidator()

    preset_issues = v._tier1_deny_scan(files_dir=preset_dir, scope_id="pA")
    project_issues = v._tier1_deny_scan(files_dir=project_dir, scope_id="bA")

    # Preset content is clean → 0 hits. Project content has a deny-phrase → ≥1.
    assert preset_issues == []
    assert len(project_issues) >= 1
    assert any("某种意义" in i.get("quote", "") for i in project_issues)
    # severity is always "warning" at Tier-1
    for issue in project_issues:
        assert issue["severity"] == "warning"
        assert issue["source"] == "tier1-deny-scan"


def test_tier1_deny_scan_legacy_fallback_to_presets_dir(tmp_path: Path, monkeypatch):
    """When run() is called without files_dir, we fall back to
    ``config.PRESETS_DIR / genre_id`` — preserves audit_preset / run_phase."""
    from src import config
    from src.genre_extractor.agents.validator import GenreValidator

    fake_presets = tmp_path / "presets"
    fake_presets.mkdir()
    (fake_presets / "legacy").mkdir()
    (fake_presets / "legacy" / "era.md").write_text(
        "值得注意的是，此处完全是套话。\n", encoding="utf-8",
    )
    monkeypatch.setattr(config, "PRESETS_DIR", fake_presets)

    v = GenreValidator()
    issues = v._tier1_deny_scan(files_dir=fake_presets / "legacy", scope_id="legacy")
    assert len(issues) >= 1
    assert any("值得注意" in i.get("quote", "") for i in issues)
