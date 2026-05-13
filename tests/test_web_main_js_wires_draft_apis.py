"""P0-6: wizard must call /draft-outline and /draft-characters from the browser.

Backend verification is impossible: the draft calls happen in JS *after*
POST /api/projects/new returns. The pure-server test suite
(test_web_draft_endpoints.py) proves the endpoints work; this test proves
the wizard is actually wired to them.

We intentionally use ripgrep-style content checks over AST parsing:
  - simpler and quicker than shipping a JS parser
  - catches the common regression (someone deletes the fetch call)
  - the substrings we assert are the literal URL paths, which are stable
    API contracts shared with the backend

After P1-17: the old monolithic main.js was split into ES modules under
web/static/js/. `read_web_main_js()` (in conftest.py) concatenates them
so these substring checks still work without caring about module layout.
"""
from __future__ import annotations

from tests.conftest import read_web_main_js


def _read_main_js() -> str:
    return read_web_main_js()


def test_main_js_wires_draft_outline_endpoint():
    """main.js must reference /draft-outline so the wizard can POST to it."""
    src = _read_main_js()
    assert "/draft-outline" in src, (
        "main.js does not reference /api/projects/<pid>/draft-outline — "
        "the 4-step wizard's synopsis field is dead-end."
    )


def test_main_js_wires_draft_characters_endpoint():
    """main.js must reference /draft-characters so the wizard can POST to it."""
    src = _read_main_js()
    assert "/draft-characters" in src, (
        "main.js does not reference /api/projects/<pid>/draft-characters — "
        "the 4-step wizard's characters brief is dead-end."
    )


def test_main_js_always_sends_blank_outline_with_synopsis_path():
    """The wizard must NOT send outline_synopsis in the create payload —
    that would trigger double-drafting. Synopsis is kept client-side and
    posted to /draft-outline after create.
    """
    src = _read_main_js()
    # A raw 'payload.outline_synopsis = synopsis' assignment would mean the
    # frontend is still using the old one-shot contract.
    assert "payload.outline_synopsis =" not in src, (
        "payload.outline_synopsis found — wizard should always blank-create "
        "then call /draft-outline explicitly (avoids double LLM spend)."
    )
    assert "payload.characters_brief =" not in src, (
        "payload.characters_brief found — wizard should always blank-create "
        "then call /draft-characters explicitly."
    )


def test_main_js_poll_has_no_hard_iteration_cap():
    """The 600-iter / 10-min cap blocked 60-min extractions the docs promise.
    Verify it's gone.
    """
    src = _read_main_js()
    # Guard: the old pattern was `for (let i = 0; i < 600;`. Any literal
    # `< 600` in the polling function is a regression. We do a coarse check
    # that 600 doesn't appear as a bare numeric literal in the same region
    # as pollExtractProgress.
    poll_start = src.find("async function pollExtractProgress")
    assert poll_start >= 0, "pollExtractProgress function missing from main.js"
    # Scan the 2000 chars after the function start — that easily covers
    # the whole body even after the rewrite.
    region = src[poll_start:poll_start + 3000]
    assert "< 600" not in region, (
        "pollExtractProgress still has a '< 600' iteration cap — "
        "large-book extractions will time out spuriously."
    )


def test_main_js_wires_abort_button():
    """UI contract: clicking the abort button hits /extract-genre/abort."""
    src = _read_main_js()
    assert "/extract-genre/abort" in src, (
        "main.js never POSTs to /extract-genre/abort — "
        "the ⏹ 中断 button is decorative."
    )


def test_main_js_renders_phase_timeline():
    """The phase-timeline UI helper must be present (it's the whole point
    of P0-5: users need to see which of the 4 phases is live)."""
    src = _read_main_js()
    assert "renderPhaseTimeline" in src, "renderPhaseTimeline helper missing"
    # Must toggle is-active / is-done, or the CSS animation won't trigger.
    assert "is-active" in src and "is-done" in src
