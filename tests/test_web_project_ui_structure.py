"""Structural assertions for the project-home HTML (wizard 4-step + override-genre button).

Phase 4 · Task 4.7 — verify the index page exposes:
  - 4 wizard-step sections (data-wizard-step="1..4")
  - three genre-starter radio options (preset / extract / blank)
  - the 覆盖题材 override button + its supporting form fields
  - main.js wires the new endpoints

After P1-17: main.js was split into ES modules; read_web_main_js() from
conftest.py concatenates them for content-based assertions.

After P2-10: the 6 dialog blocks were split into
``web/templates/_partials/dialogs/*.html`` partials; assertions that check
for markers *inside* those dialogs now render the page through the Flask
test client and inspect the final HTML. The header-only marker
(``btn-extract-genre-override``) lives in ``index.html`` itself so the
raw-file read still works for that one.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import read_web_main_js

REPO = Path(__file__).resolve().parent.parent


def _rendered_index_html() -> str:
    """Render index.html through Flask so included partials are expanded."""
    from web.app import app
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200, f"GET / returned {resp.status_code}"
    return resp.get_data(as_text=True)


def test_index_html_has_wizard_4_steps():
    html = _rendered_index_html()
    for step in (1, 2, 3, 4):
        assert f'data-wizard-step="{step}"' in html, f"wizard step {step} marker missing"


def test_index_html_has_three_genre_starter_options():
    html = _rendered_index_html()
    for marker in ('data-genre-starter="preset"',
                   'data-genre-starter="extract"',
                   'data-genre-starter="blank"'):
        assert marker in html, f"genre-starter option {marker} missing"


def test_index_html_has_extract_genre_override_button():
    # This one lives in index.html's header, not in a partial.
    text = (REPO / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-extract-genre-override"' in text


def test_index_html_wizard_has_outline_and_characters_textareas():
    html = _rendered_index_html()
    assert 'name="outline_synopsis"' in html
    assert 'name="characters_brief"' in html
    assert 'name="blank_outline"' in html
    assert 'name="blank_characters"' in html


def test_main_js_wires_wizard_and_override():
    text = read_web_main_js()
    # Wizard submission
    assert "/api/projects/new" in text
    # Override
    assert "/extract-genre" in text
    # Reads presets and novels list
    assert "/api/presets" in text
    assert "/api/novels" in text


def test_no_stale_genres_urls_in_web():
    """Web layer must fully use /presets routes after Phase 4."""
    import subprocess
    result = subprocess.run(
        ["git", "grep", "-l", "-E", r"/api/genres|href=\"/genres\""],
        capture_output=True, text=True, cwd=REPO,
    )
    hits = [ln for ln in result.stdout.splitlines() if ln and ln.startswith("web/")]
    assert hits == [], f"stale /genres URLs in web/: {hits}"


def test_preset_detail_template_uses_preset_id_not_gid():
    """Phase 5 cleanup: the detail template's view passes `preset_id`, not `gid`."""
    text = (REPO / "web" / "templates" / "presets" / "detail.html").read_text(encoding="utf-8")
    assert "{{ gid }}" not in text, "detail.html still references {{ gid }} (view passes preset_id)"
    assert "{{ preset_id }}" in text, "detail.html should render {{ preset_id }} at least once"


def test_preset_templates_have_no_dead_routes():
    """Phase 5 cleanup: no links to removed routes (/presets/<id>/extract).

    Scope is web/ only (docs/plans may still mention historical routes).
    Excludes /api/presets/new-from-novel / new-blank / new-from-description
    which are valid current endpoints. /presets/new is also a valid current
    page (the 3-tab creation wizard added in Task 4).
    """
    import subprocess
    # Look only inside web/ and match ONLY the dead routes as HREFs or URL literals.
    # Patterns:
    #   href="/presets/<anything>/extract..."  — old extract flow
    #   /api/presets/new"  or  /api/presets/new'  (exact /new, not /new-from-novel etc.)
    result = subprocess.run(
        ["git", "grep", "-nE",
         r"href=\"/presets/[^\"]+/extract|/api/presets/new[\"']",
         "--", "web/"],
        capture_output=True, text=True, cwd=REPO,
    )
    hits = [ln for ln in result.stdout.splitlines() if ln]
    assert hits == [], f"references to deleted routes in web/: {hits}"
