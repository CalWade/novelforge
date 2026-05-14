"""P1-17: web/static/main.js was split into ES modules under web/static/js/.

These tests verify the split landed cleanly:
  - the entry `main.js` is small (≤200 lines)
  - every expected module exists
  - the template loads the new entry as type="module"
  - key functions still live somewhere in the concatenated source
    (regression guard: "did we lose a function during the split?")
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import read_web_main_js

REPO = Path(__file__).resolve().parent.parent
JS_DIR = REPO / "web" / "static" / "js"
TEMPLATE = REPO / "web" / "templates" / "index.html"


# ---------- file layout ----------

def test_js_module_directory_exists():
    assert JS_DIR.is_dir(), "web/static/js/ module directory missing"


def test_js_entry_main_js_exists_and_small():
    entry = JS_DIR / "main.js"
    assert entry.exists(), "web/static/js/main.js entry missing"
    lines = entry.read_text(encoding="utf-8").count("\n")
    assert lines <= 200, (
        f"web/static/js/main.js is {lines} lines — entry should stay ≤200 "
        "(add imports or extract logic to a feature module, not inline)"
    )


def test_expected_core_modules_exist():
    expected = [
        "main.js",
        "state.js",
        "utils.js",
        "api.js",
        "ui/tabs.js",
        "ui/tree.js",
        "ui/viewer.js",
        "ui/pills.js",
        "ui/lessons.js",
        "ui/debt.js",
        "ui/inspector.js",
        "ui/bookkeeping.js",
        "ui/polling.js",
        "ui/runControls.js",
        "features/projectPicker.js",
        "features/projectWizard.js",
        "features/sourceEditor.js",
        "features/settings.js",
        "features/onboarding.js",
    ]
    missing = [p for p in expected if not (JS_DIR / p).exists()]
    assert not missing, f"missing ES modules: {missing}"


def test_no_module_over_400_lines():
    """Keep individual modules readable — roughly ≤300 ideal, ≤400 hard cap.
    The 4-step project wizard is the one expected stretch (~357 lines) and
    stays under 400 because step navigation + validation + submission are
    tightly coupled."""
    too_big = []
    for p in sorted(JS_DIR.rglob("*.js")):
        n = p.read_text(encoding="utf-8").count("\n")
        if n > 400:
            too_big.append((p.relative_to(REPO), n))
    assert not too_big, (
        f"these modules are over 400 lines — consider splitting: {too_big}"
    )


# ---------- template wiring ----------

def test_template_loads_entry_as_module():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'type="module"' in html, (
        'index.html must load the entry with type="module" — ES module imports '
        'will 404 otherwise.'
    )
    assert "js/main.js" in html, (
        "index.html must reference the new entry at static/js/main.js"
    )


def test_template_no_longer_references_old_main_js():
    """Make sure we don't ship both old + new (which would load the IIFE
    version with duplicate global state)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    # Template should reference `js/main.js`, NOT bare `static/main.js`.
    # A bare `filename='main.js'` load would pull in the old monolith.
    assert "filename='main.js'" not in html
    assert 'filename="main.js"' not in html


# ---------- regression guard: key symbols still present ----------

def test_key_functions_still_defined_somewhere():
    """Search the concatenated modules for critical public functions.
    If any of these disappear during a future refactor, this test fails loudly.
    """
    src = read_web_main_js()
    must_have = [
        # entry / boot
        "function init",
        "DOMContentLoaded",
        # polling
        "function pollState", "function pollStatus", "function pollPrompts",
        # pills + tree + viewer
        "function renderPills", "function renderTree", "function openFile",
        # tabs
        "function setCenterTab", "function setRightTab", "function wireTabs",
        # inspector + log
        "function refreshPrompts", "function renderInspector",
        # run controls
        "function doRun", "function doAbort", "function syncRunFields",
        # features
        "function openProjectPicker", "function openNewProjectWizard",
        "function openSettingsDialog", "function openSourceEditor",
        "function checkOnboarding", "function showOnboarding",
        # bookkeeping (P1-9)
        "function renderBookkeeping",
    ]
    missing = [name for name in must_have if name not in src]
    assert not missing, (
        f"these public functions vanished after the split: {missing} — "
        "module names may have changed but the exported symbols are part "
        "of the implicit contract the rest of the test suite relies on."
    )


def test_state_module_exports_singleton():
    """state.js must export the mutable `state` object and the agent colour
    tables — other modules `import { state, AGENT_LABEL } from './state.js'`.
    """
    src = (JS_DIR / "state.js").read_text(encoding="utf-8")
    assert "export const state" in src
    assert "export const AGENT_LABEL" in src
    assert "export const AGENT_COLORS" in src
    assert "export const LESSONS" in src


def test_old_monolithic_main_js_is_gone():
    """Once the split ships, the legacy web/static/main.js must go away to
    avoid confusion (two sources of truth) and to ensure nothing in the
    codebase still points at the old path."""
    legacy = REPO / "web" / "static" / "main.js"
    assert not legacy.exists(), (
        "web/static/main.js still present — delete it after confirming "
        "the ES-module split under web/static/js/ is wired correctly."
    )
