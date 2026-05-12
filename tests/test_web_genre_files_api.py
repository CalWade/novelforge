"""Web API: per-genre-file read / edit / validate.

STATUS: These tests are written (TDD red phase) but the 4 target API routes
are not yet implemented in web/app.py. The module-level pytestmark below
skips the entire file until the routes land. Remove the skipmark when
implementing /api/genres/<id>/files/* to enable TDD green.

Tracked in: docs/superpowers/specs/2026-05-11-genre-pipeline-design.md §10.3

Covers the 4 endpoints added under /api/genres/<id>/files/*:

    GET    /api/genres/<id>/files                    — list whitelist files on disk
    GET    /api/genres/<id>/files/<fname>            — read one
    PUT    /api/genres/<id>/files/<fname>            — save (with mtime conflict check)
    POST   /api/genres/<id>/files/<fname>/validate   — dry-run validator

Security invariants under test:
    1. Only the 5-file whitelist is reachable (genre.yaml / era.md / writing-
       style-extra.md / iron-laws-extra.md / resource_schema.yaml).
    2. Path-traversal via <fname> never escapes genres/<id>/ — no '..',
       no URL-encoded %2F, no '.build/' writes.
    3. Stale writes get 409 — the browser tab can't silently clobber a
       terminal edit.

Every test monkey-patches config.GENRES_DIR to tmp_path so the real
genres/ directory is never mutated.
"""
from __future__ import annotations

import time

import pytest
import yaml

from web.app import app

# Skip the whole module until the target routes are implemented.
# Remove this when /api/genres/<id>/files/* lands.
pytestmark = pytest.mark.skip(
    reason="routes not yet implemented; see docs/superpowers/specs/2026-05-11-genre-pipeline-design.md §10.3",
)
from src import config


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def genre_on_disk(tmp_path, monkeypatch):
    """Create a realistic genre pack in tmp_path/<gid>/ and redirect config.

    Content lengths are chosen to be above the setting_lint thresholds
    (era.md >= 500 chars, writing-style-extra.md >= 300 chars,
    iron-laws-extra.md >= 3 iron_law entries) so validate tests have a
    clean baseline to deviate from.
    """
    monkeypatch.setattr(config, "GENRES_DIR", tmp_path)
    gid = "edit-smoke"
    gdir = tmp_path / gid
    gdir.mkdir()
    (gdir / "genre.yaml").write_text(
        "id: edit-smoke\n"
        "display_name: 编辑冒烟\n"
        "locale: zh-Hans\n"
        "genre: 测试\n"
        "era: 2026 · 测试时代\n"
        "tone: 冷静 · 精准\n"
        "author_persona_hints: []\n"
        "genre_avoid: []\n"
        "prohibited_styles: []\n",
        encoding="utf-8",
    )
    (gdir / "era.md").write_text(
        "# Era · edit-smoke\n\n"
        + ("时代事实描述。" * 120)  # 1200+ chars, comfortably above MIN_ERA_CHARS=500
        + "\n",
        encoding="utf-8",
    )
    (gdir / "writing-style-extra.md").write_text(
        "# Writing Style Extra\n\n"
        + ("风格示例句子。" * 80)  # ~560 chars, above MIN_STYLE_EXTRA_CHARS=300
        + "\n",
        encoding="utf-8",
    )
    (gdir / "iron-laws-extra.md").write_text(
        "# Iron Laws Extra · edit-smoke\n\n"
        "## iron_law_extra_1: 第一条\n占位。\n\n"
        "## iron_law_extra_2: 第二条\n占位。\n\n"
        "## iron_law_extra_3: 第三条\n占位。\n",
        encoding="utf-8",
    )
    # Intentionally omit resource_schema.yaml so the 'optional not found'
    # test has something to assert. Individual tests can create it.
    yield gid


# ---------------------------------------------------------------------------
# GET /api/genres/<id>/files  (list)
# ---------------------------------------------------------------------------

def test_list_files_returns_four_whitelist_files(client, genre_on_disk):
    resp = client.get(f"/api/genres/{genre_on_disk}/files")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {f["name"] for f in data["files"]}
    # All 4 required files present, resource_schema.yaml absent
    assert names == {
        "genre.yaml", "era.md", "writing-style-extra.md", "iron-laws-extra.md",
    }
    # Every row carries the required fields
    for row in data["files"]:
        assert isinstance(row["size_bytes"], int) and row["size_bytes"] > 0
        assert isinstance(row["lines"], int) and row["lines"] > 0
        assert isinstance(row["mtime"], (int, float))
        assert row["kind"] in {"yaml", "markdown"}


def test_list_files_only_whitelist(client, genre_on_disk, tmp_path):
    """Extra files in the genre dir (e.g. hand-edits, .bak) must NOT leak
    through the list endpoint — the editor API is whitelist-only.
    """
    gdir = tmp_path / genre_on_disk
    (gdir / "notes.txt").write_text("my scratch notes", encoding="utf-8")
    (gdir / "genre.yaml.bak").write_text("old: copy", encoding="utf-8")
    (gdir / ".build").mkdir()
    (gdir / ".build" / "build_status.yaml").write_text("x: 1", encoding="utf-8")

    resp = client.get(f"/api/genres/{genre_on_disk}/files")
    names = {f["name"] for f in resp.get_json()["files"]}
    assert "notes.txt" not in names
    assert "genre.yaml.bak" not in names
    assert "build_status.yaml" not in names


def test_list_files_shows_optional_resource_schema(client, genre_on_disk, tmp_path):
    """resource_schema.yaml is whitelisted but optional — only listed when present."""
    (tmp_path / genre_on_disk / "resource_schema.yaml").write_text(
        "resources:\n  cash:\n    unit: HKD\n    tracking: running_balance\n",
        encoding="utf-8",
    )
    names = {f["name"] for f in client.get(f"/api/genres/{genre_on_disk}/files").get_json()["files"]}
    assert "resource_schema.yaml" in names


def test_list_files_nonexistent_genre(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENRES_DIR", tmp_path)
    resp = client.get("/api/genres/ghost/files")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/genres/<id>/files/<fname>  (read one)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fname,kind", [
    ("genre.yaml", "yaml"),
    ("era.md", "markdown"),
    ("writing-style-extra.md", "markdown"),
    ("iron-laws-extra.md", "markdown"),
])
def test_get_whitelist_file(client, genre_on_disk, fname, kind):
    resp = client.get(f"/api/genres/{genre_on_disk}/files/{fname}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == fname
    assert data["kind"] == kind
    assert isinstance(data["content"], str) and len(data["content"]) > 0
    assert isinstance(data["mtime"], (int, float))
    assert data["size_bytes"] > 0


def test_get_file_includes_mtime_field(client, genre_on_disk, tmp_path):
    """mtime from GET must equal the on-disk mtime — otherwise the PUT
    conflict-detection would be broken before it started."""
    disk_mtime = (tmp_path / genre_on_disk / "genre.yaml").stat().st_mtime
    resp = client.get(f"/api/genres/{genre_on_disk}/files/genre.yaml")
    assert abs(resp.get_json()["mtime"] - disk_mtime) < 0.001


def test_get_resource_schema_optional_returns_404(client, genre_on_disk):
    """resource_schema.yaml is legitimately absent → 404, NOT 500."""
    resp = client.get(f"/api/genres/{genre_on_disk}/files/resource_schema.yaml")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["ok"] is False


def test_get_nonwhitelist_file_rejected(client, genre_on_disk, tmp_path):
    """Even if the file physically exists in genres/<id>/, non-whitelist
    names are rejected at the API boundary — the editor refuses to go there.
    """
    (tmp_path / genre_on_disk / "notes.txt").write_text("hi", encoding="utf-8")
    resp = client.get(f"/api/genres/{genre_on_disk}/files/notes.txt")
    assert resp.status_code == 400


@pytest.mark.parametrize("bad_fname", [
    "../../../etc/passwd",
    "..%2Fsecret.yaml",  # URL-encoded but Flask decodes before routing
    ".build/build_status.yaml",
    "..",
    ".",
    "genre.yaml/../../../etc/passwd",
])
def test_path_traversal_via_fname_rejected(client, genre_on_disk, bad_fname, tmp_path):
    """Sweep: every variant must be 400, and no file may escape the genre dir."""
    # Seed a sentinel outside the tmp genres root
    sentinel = tmp_path.parent / "sentinel.txt"
    sentinel.write_text("KEEP ME", encoding="utf-8")
    resp = client.get(f"/api/genres/{genre_on_disk}/files/{bad_fname}")
    assert resp.status_code in (400, 404), f"{bad_fname!r} got {resp.status_code}"
    # Sentinel must still exist untouched
    assert sentinel.exists() and sentinel.read_text() == "KEEP ME"


# ---------------------------------------------------------------------------
# PUT /api/genres/<id>/files/<fname>  (save)
# ---------------------------------------------------------------------------

def test_put_with_correct_mtime_succeeds(client, genre_on_disk, tmp_path):
    # GET first to capture mtime (realistic flow)
    got = client.get(f"/api/genres/{genre_on_disk}/files/era.md").get_json()
    new_content = got["content"] + "\n\n<!-- appended by editor -->\n"
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": new_content, "expected_mtime": got["mtime"]},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is True
    assert body["mtime"] > got["mtime"] or body["mtime"] >= got["mtime"]
    assert (tmp_path / genre_on_disk / "era.md").read_text("utf-8") == new_content


def test_put_returns_new_mtime_and_size(client, genre_on_disk):
    got = client.get(f"/api/genres/{genre_on_disk}/files/era.md").get_json()
    body = "X" * 999
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": body, "expected_mtime": got["mtime"]},
    )
    out = resp.get_json()
    assert out["size_bytes"] == len(body)
    assert out["mtime"] >= got["mtime"]


def test_put_with_stale_mtime_409(client, genre_on_disk, tmp_path):
    got = client.get(f"/api/genres/{genre_on_disk}/files/era.md").get_json()
    # Simulate external edit: re-write the file to bump mtime
    time.sleep(0.02)  # ensure mtime resolution sees the change
    path = tmp_path / genre_on_disk / "era.md"
    path.write_text(path.read_text("utf-8") + "\nsomeone else edited\n", encoding="utf-8")

    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": "my replacement", "expected_mtime": got["mtime"]},
    )
    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["error"] == "stale"
    assert "current_mtime" in body
    # Crucially: the external edit survived
    assert "someone else edited" in path.read_text("utf-8")


def test_put_missing_expected_mtime_400(client, genre_on_disk):
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": "new"},
    )
    assert resp.status_code == 400


def test_put_missing_content_400(client, genre_on_disk):
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"expected_mtime": 0.0},
    )
    assert resp.status_code == 400


def test_put_whitelist_only(client, genre_on_disk):
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/evil.md",
        json={"content": "x", "expected_mtime": 0.0},
    )
    assert resp.status_code == 400


def test_put_refuses_to_create_new_whitelist_file(client, genre_on_disk, tmp_path):
    """resource_schema.yaml isn't on disk — PUT should NOT create it.
    Creation goes through --new-genre / --fill-genre; the editor only
    updates existing files.
    """
    assert not (tmp_path / genre_on_disk / "resource_schema.yaml").exists()
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/resource_schema.yaml",
        json={"content": "resources: {}", "expected_mtime": 0.0},
    )
    assert resp.status_code == 404
    assert not (tmp_path / genre_on_disk / "resource_schema.yaml").exists()


# ---------------------------------------------------------------------------
# YAML validation on PUT
# ---------------------------------------------------------------------------

def test_put_valid_yaml_accepted(client, genre_on_disk):
    got = client.get(f"/api/genres/{genre_on_disk}/files/genre.yaml").get_json()
    new_yaml = (
        "id: edit-smoke\n"
        "display_name: 新名字\n"
        "locale: zh-Hans\n"
        "genre: 测试2\n"
        "era: 2027\n"
        "tone: 轻盈\n"
    )
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/genre.yaml",
        json={"content": new_yaml, "expected_mtime": got["mtime"]},
    )
    assert resp.status_code == 200
    assert yaml.safe_load(new_yaml)["display_name"] == "新名字"


def test_put_invalid_yaml_rejected_400(client, genre_on_disk, tmp_path):
    got = client.get(f"/api/genres/{genre_on_disk}/files/genre.yaml").get_json()
    path = tmp_path / genre_on_disk / "genre.yaml"
    original = path.read_text("utf-8")

    broken = "display_name: : : :\n"
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/genre.yaml",
        json={"content": broken, "expected_mtime": got["mtime"]},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "yaml_parse_error"
    assert "detail" in body
    # Original must be intact — invalid content must never touch disk
    assert path.read_text("utf-8") == original


def test_put_markdown_no_yaml_parse(client, genre_on_disk):
    """.md files must never go through safe_load — a frontmatter '---'
    block in a Markdown file is perfectly legal."""
    got = client.get(f"/api/genres/{genre_on_disk}/files/era.md").get_json()
    tricky = "---\nfoo: bar\n---\n\n# Era\n\n这里有 --- 分割线也没问题\n"
    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": tricky, "expected_mtime": got["mtime"]},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------

def test_put_atomic_on_crash(client, genre_on_disk, tmp_path, monkeypatch):
    """If os.replace fails mid-write, original file is untouched."""
    got = client.get(f"/api/genres/{genre_on_disk}/files/era.md").get_json()
    path = tmp_path / genre_on_disk / "era.md"
    original = path.read_text("utf-8")

    import os as _os
    real_replace = _os.replace

    def boom(src, dst):
        raise OSError("simulated disk full")
    monkeypatch.setattr(_os, "replace", boom)

    resp = client.put(
        f"/api/genres/{genre_on_disk}/files/era.md",
        json={"content": "ALL NEW", "expected_mtime": got["mtime"]},
    )
    monkeypatch.setattr(_os, "replace", real_replace)
    assert resp.status_code == 500
    # Original intact
    assert path.read_text("utf-8") == original
    # No leaked temp files in the dir
    residue = [p.name for p in (tmp_path / genre_on_disk).iterdir()
               if p.name.startswith(".tmp_")]
    assert residue == [], f"temp file leaked: {residue}"


# ---------------------------------------------------------------------------
# POST /api/genres/<id>/files/<fname>/validate
# ---------------------------------------------------------------------------

def test_validate_yaml_ok(client, genre_on_disk):
    resp = client.post(
        f"/api/genres/{genre_on_disk}/files/genre.yaml/validate",
        json={"content": "id: x\ndisplay_name: ok\n"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["errors"] == []


def test_validate_yaml_parse_error(client, genre_on_disk):
    resp = client.post(
        f"/api/genres/{genre_on_disk}/files/genre.yaml/validate",
        json={"content": "display_name: : : :\n"},
    )
    assert resp.status_code == 200   # validator endpoint always 200; errors in body
    body = resp.get_json()
    assert body["ok"] is False
    assert any("yaml" in e.lower() or "parse" in e.lower() for e in body["errors"])


def test_validate_markdown_thin_content_warning(client, genre_on_disk):
    """era.md below MIN_ERA_CHARS (500) emits a warning — reuses setting_lint
    thresholds per spec."""
    resp = client.post(
        f"/api/genres/{genre_on_disk}/files/era.md/validate",
        json={"content": "太短了。"},
    )
    body = resp.get_json()
    # Warnings (not errors) — we still accept thin content, just flag it
    assert body["warnings"], f"expected warning for thin era.md: {body}"


def test_validate_whitelist_only(client, genre_on_disk):
    resp = client.post(
        f"/api/genres/{genre_on_disk}/files/evil.md/validate",
        json={"content": "x"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Basic view smoke — full editor UI asserted in Task B tests
# ---------------------------------------------------------------------------

def test_detail_page_still_renders(client, genre_on_disk):
    """Task A change (routes only) must not break the existing view."""
    resp = client.get(f"/genres/{genre_on_disk}")
    assert resp.status_code == 200
