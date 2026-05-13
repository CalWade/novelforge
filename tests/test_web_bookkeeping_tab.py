"""Structural assertions for the Bookkeeping tab (Lesson-3 三件套).

P1-9 — verify the index dashboard exposes a dedicated tab that aggregates
the three overwrite-style snapshots (current_status_card.md, pending_hooks.md,
resource_ledger.md) so a Context Reset reader can see them side-by-side.

These tests are intentionally shallow / structural — they assert the contract
(tab exists, panes exist, JS wires the known file paths, CSS declares the
grid selectors). Visual QA is out of scope for unit tests.

After P1-17: main.js was split into ES modules; `read_web_main_js()` from
conftest.py concatenates them for content-based assertions.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import read_web_main_js

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "web" / "templates" / "index.html"
# P2 #14: main.css was split into layered files under web/static/css/.
# Concatenate all of them (plus any residual main.css manifest) so
# content-based assertions still work across the split.
_CSS_ROOT = REPO / "web" / "static"


def _all_css_text() -> str:
    parts: list[str] = []
    main = _CSS_ROOT / "main.css"
    if main.exists():
        parts.append(main.read_text(encoding="utf-8"))
    for p in sorted((_CSS_ROOT / "css").rglob("*.css")):
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ---------- template ----------

def test_index_has_bookkeeping_tab_button():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert 'data-tab="bookkeeping"' in text, "bookkeeping tab button missing"
    # Tab must carry a badge span so JS can populate "n/3" progress.
    assert 'id="tab-bookkeeping-badge"' in text, "bookkeeping badge span missing"


def test_index_has_bookkeeping_pane_with_three_cards():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert 'data-pane="bookkeeping"' in text, "bookkeeping tab-pane missing"
    for key in ("status", "hooks", "ledger"):
        assert f'data-bk="{key}"' in text, f"bk-card data-bk={key!r} missing"
    # The three filenames must be referenced in the pane header subtitles,
    # so the UI self-documents what file each card represents.
    assert "current_status_card.md" in text
    assert "pending_hooks.md" in text
    assert "resource_ledger.md" in text


def test_index_bookkeeping_tab_has_aria_attributes():
    """Accessibility: all center tabs must declare role + aria-selected."""
    text = TEMPLATE.read_text(encoding="utf-8")
    # Grab the tab line and verify it's role=tab (the template uses role="tab"
    # on every tab button, we just verify the bookkeeping one conforms).
    import re
    line = next(
        (ln for ln in text.splitlines() if 'data-tab="bookkeeping"' in ln),
        None,
    )
    assert line is not None
    assert 'role="tab"' in line
    assert 'aria-selected' in line


# ---------- JS wiring ----------

def test_main_js_defines_render_bookkeeping():
    src = read_web_main_js()
    assert "function renderBookkeeping" in src, "renderBookkeeping() not defined"


def test_main_js_references_three_bookkeeping_files():
    src = read_web_main_js()
    for path in (
        "state/current_status_card.md",
        "state/pending_hooks.md",
        "state/resource_ledger.md",
    ):
        assert path in src, f"main.js must reference {path}"


def test_main_js_tab_bookkeeping_triggers_render():
    """setCenterTab('bookkeeping') must call renderBookkeeping."""
    src = read_web_main_js()
    # Cheap contract check: presence of both tokens in the same file,
    # and an explicit dispatch branch.
    assert "if (name === 'bookkeeping')" in src, (
        "setCenterTab must branch on 'bookkeeping' to trigger renderBookkeeping"
    )


def test_main_js_detects_resource_schema_for_ledger_disabled_state():
    """Books without resource_schema.yaml intentionally opt out of the ledger.
    The UI must surface that (not just show a broken card)."""
    src = read_web_main_js()
    assert "has_resource_schema" in src


def test_main_js_updates_bookkeeping_badge():
    src = read_web_main_js()
    assert "tab-bookkeeping-badge" in src


# ---------- CSS ----------

def test_main_css_has_bookkeeping_selectors():
    css = _all_css_text()
    for sel in (".bookkeeping-view", ".bk-card", ".bk-card-head", ".bk-card-body"):
        assert sel in css, f"main.css missing selector {sel!r}"


def test_main_css_bookkeeping_has_responsive_fallback():
    """At narrow viewports the 3-column grid must collapse to 1 column."""
    css = _all_css_text()
    # Rough check: there is a media query that mentions bk-grid OR a single-column
    # redefinition of bk-grid.
    assert "bk-grid" in css
    # P2 #13: responsive breakpoints unified to 1440 / 1280 / 1024. The
    # bookkeeping 3-col→1-col fold used to live at @900; it's now folded
    # into the ≤1024 block (nearest standard breakpoint).
    assert "max-width: 1024px" in css or "max-width:1024px" in css
    # And bk-grid must actually switch to 1fr somewhere under a media query.
    assert ".bk-grid { grid-template-columns: 1fr" in css or \
           ".bk-grid{grid-template-columns:1fr" in css


def test_main_css_bookkeeping_has_disabled_state():
    """Ledger card needs a visually-distinct disabled state for opt-out books."""
    css = _all_css_text()
    assert ".bk-card.is-disabled" in css or ".is-disabled" in css
