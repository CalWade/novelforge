"""新向导（3 步）结构断言 — 2026-05-14 重构后.

新架构：
  - 向导 3 步（题材 / 作品信息 / 起草）
  - Step 1 只有 preset 下拉（没有 extract / blank radio）
  - Step 2 不再问用户要 id（后端 auto_generate_project_id）
  - 旧的"从原著拆"radio + extract-to-project kind + ⎇ 覆盖按钮已删
  - post-creation /draft-outline + /draft-characters 链已合并进 /api/projects/new
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import read_web_main_js

REPO = Path(__file__).resolve().parent.parent


def _index_html() -> str:
    return (REPO / "web/templates/index.html").read_text(encoding="utf-8")


def _wizard_html() -> str:
    return (REPO / "web/templates/_partials/dialogs/new_project.html").read_text(encoding="utf-8")


# ---------- 新架构：向导 3 步 ----------

def test_wizard_has_exactly_three_steps():
    html = _wizard_html()
    for step in ("1", "2", "3"):
        assert f'data-wizard-step="{step}"' in html, f"step {step} 缺失"
    assert 'data-wizard-step="4"' not in html, "第 4 步应该在重构中被删掉"


def test_wizard_step1_only_has_preset_picker():
    """Step 1 只剩 from_preset select，不再有 genre_starter radio."""
    html = _wizard_html()
    assert 'id="select-from-preset"' in html
    # 旧的 3 选 radio 应全部消失
    assert 'genre_starter' not in html
    assert 'data-genre-panel="extract"' not in html
    assert 'data-genre-panel="blank"' not in html


def test_wizard_step2_no_user_facing_id_field():
    """id 不再展示给用户，后端 auto-generate."""
    html = _wizard_html()
    # name="id" 的 input 应该不存在
    assert 'name="id"' not in html


def test_wizard_step3_has_outline_and_characters_textareas():
    html = _wizard_html()
    assert 'name="outline_synopsis"' in html
    assert 'name="characters_brief"' in html


def test_wizard_step1_links_to_preset_new_when_empty():
    """Step 1 有 '去题材库新建一个 preset' 的按钮."""
    html = _wizard_html()
    assert 'href="/presets/new"' in html
    assert 'wizard-preset-empty-hint' in html


# ---------- 新架构：顶栏不再有 ⎇ 覆盖题材按钮 ----------

def test_no_extract_genre_override_button():
    html = _index_html()
    assert 'btn-extract-genre-override' not in html


def test_no_extract_override_dialog_include():
    html = _index_html()
    assert 'extract_override.html' not in html


# ---------- 新架构：main.js 清理了 initExtractOverride 引用 ----------

def test_main_js_does_not_import_extract_override():
    js = read_web_main_js()
    # extractOverride.js 本身已删，所以 import 会 404；
    # 确保 main.js 里没有这个 import 语句残留
    assert 'extractOverride.js' not in js
    assert 'initExtractOverride' not in js


# ---------- 新架构：wizard 不再发 extract-to-project job ----------

def test_wizard_does_not_send_extract_to_project_kind():
    js = read_web_main_js()
    assert 'extract-to-project' not in js, (
        "新建作品向导不应再提交 kind='extract-to-project' — "
        "这个 kind 已被后端白名单移除。"
    )


def test_wizard_does_not_separately_call_post_creation_drafts():
    """合并后的流程：synopsis/brief 直接进 /api/projects/new payload，
    不再有 post-creation 的 /draft-outline + /draft-characters 串联调用."""
    js = read_web_main_js()
    # 向导内部不再显式调这两个 endpoint；它们仅作为 backend warnings 的重试
    # endpoint 在 warnings.retry_endpoint 里引用，但 wizard JS 不主动 fetch
    assert 'runPostCreationDrafts' not in js


def test_wizard_sends_outline_synopsis_to_create_endpoint():
    """新流程：synopsis 直接在 POST /api/projects/new payload 里传."""
    js = read_web_main_js()
    assert 'outline_synopsis' in js
    assert 'characters_brief' in js


# ---------- 新架构：后端 auto_generate_project_id 存在 ----------

def test_backend_has_auto_generate_project_id():
    bootstrap_py = (REPO / "src/bootstrap.py").read_text(encoding="utf-8")
    assert 'def auto_generate_project_id' in bootstrap_py
