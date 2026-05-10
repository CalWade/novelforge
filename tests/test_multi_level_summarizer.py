"""Tests for multi-level summarizer boundary logic and context assembly."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.multi_level_summarizer import (
    ARC_SIZE,
    VOLUME_SIZE,
    arc_filename,
    arc_index_for_chapter,
    assemble_long_chain_context,
    is_arc_boundary,
    is_volume_boundary,
    most_recent_completed_arc,
    most_recent_completed_volume,
    volume_filename,
    volume_index_for_chapter,
)
from src.blackboard import Blackboard


# --- pure boundary / index functions ---

def test_arc_size_is_5():
    assert ARC_SIZE == 5


def test_volume_size_is_20():
    assert VOLUME_SIZE == 20


@pytest.mark.parametrize("ch,expected", [
    (1, 1), (4, 1), (5, 1),
    (6, 2), (10, 2),
    (11, 3), (15, 3),
    (25, 5),
])
def test_arc_index_for_chapter(ch, expected):
    assert arc_index_for_chapter(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    (1, 1), (19, 1), (20, 1),
    (21, 2), (40, 2),
    (41, 3), (60, 3),
])
def test_volume_index_for_chapter(ch, expected):
    assert volume_index_for_chapter(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    (1, False), (4, False), (5, True),
    (6, False), (9, False), (10, True),
    (15, True), (20, True),
])
def test_is_arc_boundary(ch, expected):
    assert is_arc_boundary(ch) is expected


@pytest.mark.parametrize("ch,expected", [
    (1, False), (19, False), (20, True),
    (21, False), (40, True), (60, True),
])
def test_is_volume_boundary(ch, expected):
    assert is_volume_boundary(ch) is expected


@pytest.mark.parametrize("current_ch,expected", [
    (1, None),   # nothing completed
    (5, None),   # ch5 currently writing — arc 1 not yet done
    (6, 1),      # ch1-5 complete, arc 1 available
    (10, 1),     # still arc 1 (arc 2 not done)
    (11, 2),     # ch6-10 complete
    (26, 5),     # ch21-25 complete
])
def test_most_recent_completed_arc(current_ch, expected):
    assert most_recent_completed_arc(current_ch) == expected


@pytest.mark.parametrize("current_ch,expected", [
    (1, None),
    (20, None),   # writing ch20, volume 1 not yet done
    (21, 1),
    (40, 1),
    (41, 2),
])
def test_most_recent_completed_volume(current_ch, expected):
    assert most_recent_completed_volume(current_ch) == expected


def test_arc_filename():
    assert arc_filename(1) == "summaries/arcs/arc-01.md"
    assert arc_filename(10) == "summaries/arcs/arc-10.md"


def test_volume_filename():
    assert volume_filename(1) == "summaries/volumes/vol-01.md"
    assert volume_filename(5) == "summaries/volumes/vol-05.md"


# --- context assembly integration ---

@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    return Blackboard(root=tmp_path)


def _write_ch_summary(bb: Blackboard, n: int, body: str) -> None:
    bb.write_text(f"summaries/ch{n:03d}.md", body)


def _write_arc_summary(bb: Blackboard, a: int, body: str) -> None:
    bb.write_text(arc_filename(a), body)


def _write_vol_summary(bb: Blackboard, v: int, body: str) -> None:
    bb.write_text(volume_filename(v), body)


def test_ch1_no_context(bb):
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=1)
    assert "首章" in ctx
    assert inputs == []


def test_ch2_only_l1(bb):
    _write_ch_summary(bb, 1, "ch1 summary content")
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=2)
    assert "第 1 章摘要（L1）" in ctx
    assert "ch1 summary content" in ctx
    assert "L2" not in ctx
    assert "L3" not in ctx


def test_ch3_reads_last_2_l1(bb):
    _write_ch_summary(bb, 1, "A")
    _write_ch_summary(bb, 2, "B")
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=3)
    assert "第 1 章摘要" in ctx
    assert "第 2 章摘要" in ctx


def test_ch6_pulls_in_arc1(bb):
    """After ch5 complete, writing ch6 should read L1[4] + L1[5] + L2[arc 1]."""
    for n in range(1, 6):
        _write_ch_summary(bb, n, f"ch{n}")
    _write_arc_summary(bb, 1, "arc 1 summary")
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=6)
    assert "第 4 章摘要（L1）" in ctx
    assert "第 5 章摘要（L1）" in ctx
    assert "第 1 弧摘要（L2" in ctx
    assert "arc 1 summary" in ctx
    assert "L3" not in ctx


def test_ch21_pulls_in_vol1(bb):
    """After ch20 complete, writing ch21 should read L1[19]+L1[20] + most-recent L2 + L3[vol 1]."""
    for n in (19, 20):
        _write_ch_summary(bb, n, f"ch{n}")
    _write_arc_summary(bb, 4, "arc 4 summary (covers ch16-20)")
    _write_vol_summary(bb, 1, "vol 1 summary (covers ch1-20)")
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=21)
    assert "第 19 章摘要（L1）" in ctx
    assert "第 20 章摘要（L1）" in ctx
    assert "第 4 弧摘要（L2" in ctx
    assert "arc 4 summary" in ctx
    assert "第 1 卷摘要（L3" in ctx
    assert "vol 1 summary" in ctx


def test_context_paths_are_returned(bb):
    for n in range(1, 6):
        _write_ch_summary(bb, n, f"ch{n}")
    _write_arc_summary(bb, 1, "arc")
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=6)
    assert "state/summaries/ch004.md" in inputs
    assert "state/summaries/ch005.md" in inputs
    assert "state/summaries/arcs/arc-01.md" in inputs


def test_missing_arc_file_gracefully_skipped(bb):
    """If pipeline skipped an arc boundary (e.g., crashed), don't blow up."""
    _write_ch_summary(bb, 5, "ch5")
    _write_ch_summary(bb, 6, "ch6")
    # No arc file written
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=7)
    assert "第 5 章摘要" in ctx
    assert "L2" not in ctx
    # No crash


def test_context_size_bounded_regardless_of_chapter_number(bb):
    """Even at ch100, context stays ~2400 chars not ~30000."""
    # Seed 100 chapter summaries (each 300 chars)
    for n in range(1, 101):
        _write_ch_summary(bb, n, "x" * 300)
    # Seed all completed arcs and volumes
    for a in range(1, 21):  # arcs 1..20 (covers ch1-100)
        _write_arc_summary(bb, a, "y" * 600)
    for v in range(1, 6):   # volumes 1..5 (covers ch1-100)
        _write_vol_summary(bb, v, "z" * 1200)
    ctx, inputs = assemble_long_chain_context(bb, current_chapter=101)
    # L1[99] + L1[100] + L2[arc 20, ch 96-100] + L3[vol 5, ch 81-100]
    # Expected ≈ 300 + 300 + 600 + 1200 = 2400 + some section headers
    size = len(ctx)
    assert 2400 <= size <= 3200, f"context size {size} outside expected bounds"
    # Critical: not ~30,000 (which is what naive N summaries would give)
    assert size < 5000
