# Preset 新建 · 三路径 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** 补齐 `/presets/new` 的三个 tab：从素材库拆 / 从描述生成 / 手动空壳。

**Spec:** `docs/superpowers/specs/preset-new-three-paths.md`

**Architecture:** 3 tab UI 页面（新）；2 个新 API 路由；1 个新 LLM agent 模块（`src/genre_extractor/from_description.py`）；1 个新同步 helper（`src/genre_extractor/blank_preset.py`）。

**Tech Stack:** 现有栈（Python + Flask + vanilla JS），无新依赖。

---

## 执行顺序

| Task | 文件 | 说明 |
|---|---|---|
| 1 | `src/genre_extractor/blank_preset.py` + test | 同步 helper（秒返回） |
| 2 | `src/genre_extractor/from_description.py` + test | LLM 单次调用产 blueprint |
| 3 | `web/app.py` 两个新路由 + test | `/api/presets/new-blank` + `/api/presets/new-from-description` |
| 4 | `web/templates/presets/new.html` + 路由 | 三 tab UI 页面 |
| 5 | `web/templates/presets/index.html` + `presets.js` | 删除内嵌表单，加 "+ 新建 preset" 按钮 |

**Phase Checkpoint:** `.venv/bin/python3 -m pytest tests/ -q` 全绿 + 手动验证 `/presets/new` 三 tab 都 work。

---

## Task 1 · `blank_preset.py` 同步创建空壳

**Files:**
- Create: `src/genre_extractor/blank_preset.py`
- Create: `tests/test_blank_preset.py`

- [ ] **Step 1:** 写测试 `tests/test_blank_preset.py`：

```python
"""create_blank_preset — sync scaffolding, no LLM."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


def test_create_blank_preset_writes_four_files(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    out = create_blank_preset("myblank", display_name="My Blank", tone="dry")
    preset_dir = fake_repo / "presets" / "myblank"
    assert out == preset_dir
    for fname in ("genre.yaml", "era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        assert (preset_dir / fname).exists(), f"{fname} missing"


def test_create_blank_preset_genre_yaml_shape(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("myblank", display_name="My Blank", tone="冷硬")
    data = yaml.safe_load(
        (fake_repo / "presets" / "myblank" / "genre.yaml").read_text(encoding="utf-8")
    )
    assert data["id"] == "myblank"
    assert data["display_name"] == "My Blank"
    assert data["tone"] == "冷硬"
    assert data["source"] == "blank"


def test_create_blank_preset_md_files_have_todo_placeholder(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        content = (fake_repo / "presets" / "p" / fname).read_text(encoding="utf-8")
        assert "TODO" in content or "待填写" in content


def test_create_blank_preset_creates_empty_novels_dir(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    novels = fake_repo / "presets" / "p" / "novels"
    assert novels.exists()
    assert (novels / ".gitkeep").exists()


def test_create_blank_preset_refuses_existing(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("dup", display_name="D", tone="")
    with pytest.raises(FileExistsError, match="already exists"):
        create_blank_preset("dup", display_name="D2", tone="")


def test_create_blank_preset_validates_id(fake_repo):
    from src.genre_extractor.blank_preset import create_blank_preset
    with pytest.raises(ValueError, match="id"):
        create_blank_preset("Bad Id", display_name="X", tone="")
    with pytest.raises(ValueError, match="id"):
        create_blank_preset("", display_name="X", tone="")


def test_create_blank_preset_no_resource_schema(fake_repo):
    """Blank preset deliberately omits resource_schema — user adds if needed."""
    from src.genre_extractor.blank_preset import create_blank_preset
    create_blank_preset("p", display_name="P", tone="")
    assert not (fake_repo / "presets" / "p" / "resource_schema.yaml").exists()
```

- [ ] **Step 2:** 跑红：
```bash
.venv/bin/python3 -m pytest tests/test_blank_preset.py -v 2>&1 | tail -10
```

- [ ] **Step 3:** 写实现 `src/genre_extractor/blank_preset.py`：

```python
"""Create a blank preset — scaffolding only, no LLM.

Writes 4 files with TODO placeholders. User fills them in manually.
No novels/ content (empty dir with .gitkeep). No resource_schema.yaml
(user adds if needed).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from src import config


_STUB_ERA = """# Era (TODO)

在此描述这个题材的时代背景、地理范围、社会结构、关键真实事件等。

Novelforge 会把这份文件当作"世界观事实包"注入给 Generator 和 Evaluator。
写得越具体越好，例如：
- 时间跨度
- 城市 / 场景
- 政治格局
- 关键历史节点
- 日常细节（食物、交通、货币……）
"""

_STUB_WRITING_STYLE = """# Writing Style Extra (TODO)

在此描述这个题材**特有**的写作风格。通用风格已在 rules/writing-style-core.md。

常见补充点：
- 方言/口音（粤语俚语、北方话、吴语……）
- 叙述节奏（冷硬快切、抒情慢铺、对白驱动……）
- 场景密度
- 禁止风格（如"禁止使用古典仙侠八股"）
"""

_STUB_IRON_LAWS = """# Iron Laws Extra (TODO)

在此描述这个题材**不可违反**的铁律。Evaluator 会把这些作为硬检查项。

常见举例：
- 不可写超出时代的科技（如 1983 港综不能出现智能手机）
- 不可颠倒真实历史结果
- 主角不能犯特定低级错误
- 等等
"""


def create_blank_preset(
    preset_id: str,
    *,
    display_name: str,
    tone: str,
) -> Path:
    """Create `presets/<preset_id>/` with stub files.

    Raises:
        ValueError: preset_id is invalid (empty / wrong format).
        FileExistsError: preset already exists.
    """
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", preset_id):
        raise ValueError(f"invalid preset id: {preset_id!r}")

    preset_dir = config.PRESETS_DIR / preset_id
    if preset_dir.exists():
        raise FileExistsError(f"Preset already exists: {preset_id}")

    preset_dir.mkdir(parents=True)
    (preset_dir / "novels").mkdir()
    (preset_dir / "novels" / ".gitkeep").write_text("", encoding="utf-8")

    (preset_dir / "genre.yaml").write_text(
        yaml.safe_dump(
            {
                "id": preset_id,
                "display_name": display_name or preset_id,
                "tone": tone or "",
                "source": "blank",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (preset_dir / "era.md").write_text(_STUB_ERA, encoding="utf-8")
    (preset_dir / "writing-style-extra.md").write_text(_STUB_WRITING_STYLE, encoding="utf-8")
    (preset_dir / "iron-laws-extra.md").write_text(_STUB_IRON_LAWS, encoding="utf-8")

    return preset_dir
```

- [ ] **Step 4:** 跑绿：
```bash
.venv/bin/python3 -m pytest tests/test_blank_preset.py -v 2>&1 | tail -10
```
期望：7/7 pass

- [ ] **Step 5:** 全套回归：
```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：469 + 7 = 476 pass

- [ ] **Step 6:** Commit：
```bash
git add src/genre_extractor/blank_preset.py tests/test_blank_preset.py
git commit -m "feat(preset-new): blank_preset — sync scaffold with TODO stubs"
```

---

## Task 2 · `from_description.py` LLM 单次调用产 blueprint

**Files:**
- Create: `src/genre_extractor/from_description.py`
- Create: `tests/test_from_description.py`

- [ ] **Step 1:** 写测试 `tests/test_from_description.py`：

```python
"""extract_from_description — single LLM call, no novels."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    return tmp_path


@pytest.fixture
def stub_llm_valid(monkeypatch):
    """LLM returns a valid blueprint YAML."""
    canned = yaml.safe_dump({
        "era": "# 港综 1983\n\n1983 年香港，经济起飞前夜……",
        "writing_style_extra": "# Style\n粤语俚语 / 冷硬快切",
        "iron_laws_extra": "# Laws\n- 不许出现智能手机",
        "resource_schema": None,
    }, allow_unicode=True)

    def fake_chat(system, user, *, agent_name, **kwargs):
        return canned
    monkeypatch.setattr("src.llm.chat", fake_chat)


@pytest.fixture
def stub_llm_with_schema(monkeypatch):
    """LLM returns blueprint including resource_schema."""
    canned = yaml.safe_dump({
        "era": "# Xianxia era",
        "writing_style_extra": "# style",
        "iron_laws_extra": "# laws",
        "resource_schema": {
            "resources": [
                {"name": "spirit_stone", "unit": "颗", "visibility": "public"},
            ]
        },
    }, allow_unicode=True)
    def fake_chat(system, user, *, agent_name, **kwargs):
        return canned
    monkeypatch.setattr("src.llm.chat", fake_chat)


@pytest.fixture
def stub_llm_bad(monkeypatch):
    def fake_chat(system, user, *, agent_name, **kwargs):
        return "not valid yaml at all {[}"
    monkeypatch.setattr("src.llm.chat", fake_chat)


def test_extract_from_description_writes_three_md(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    result = extract_from_description(
        "port", display_name="Port HK", tone="hard-boiled",
        description="港综 1983 冷硬…",
    )
    preset_dir = fake_repo / "presets" / "port"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md", "genre.yaml"):
        assert (preset_dir / fname).exists()
    assert not (preset_dir / "resource_schema.yaml").exists()
    assert result["preset_id"] == "port"


def test_extract_from_description_produces_schema_when_llm_says_so(fake_repo, stub_llm_with_schema):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description(
        "xianxia", display_name="Xianxia", tone="仙侠",
        description="仙侠，有灵石可追踪",
    )
    preset_dir = fake_repo / "presets" / "xianxia"
    assert (preset_dir / "resource_schema.yaml").exists()
    schema = yaml.safe_load((preset_dir / "resource_schema.yaml").read_text(encoding="utf-8"))
    assert "resources" in schema


def test_extract_from_description_genre_yaml_source_field(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description(
        "p", display_name="P", tone="", description="…",
    )
    data = yaml.safe_load((fake_repo / "presets" / "p" / "genre.yaml").read_text(encoding="utf-8"))
    assert data["source"] == "description"


def test_extract_from_description_refuses_existing(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description("dup", display_name="D", tone="", description="a")
    with pytest.raises(FileExistsError):
        extract_from_description("dup", display_name="D2", tone="", description="b")


def test_extract_from_description_empty_desc_rejects(fake_repo):
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="description"):
        extract_from_description("p", display_name="P", tone="", description="")


def test_extract_from_description_validates_id(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="id"):
        extract_from_description("Bad Id", display_name="X", tone="", description="…")


def test_extract_from_description_llm_bad_output_raises(fake_repo, stub_llm_bad):
    """Bad LLM output must raise, not silently produce garbage."""
    from src.genre_extractor.from_description import extract_from_description
    with pytest.raises(ValueError, match="LLM output"):
        extract_from_description("p", display_name="P", tone="", description="…")
    # preset dir should NOT exist after failed call
    assert not (fake_repo / "presets" / "p").exists()


def test_extract_from_description_creates_empty_novels(fake_repo, stub_llm_valid):
    from src.genre_extractor.from_description import extract_from_description
    extract_from_description("p", display_name="P", tone="", description="…")
    assert (fake_repo / "presets" / "p" / "novels" / ".gitkeep").exists()
```

- [ ] **Step 2:** 跑红：
```bash
.venv/bin/python3 -m pytest tests/test_from_description.py -v 2>&1 | tail -10
```

- [ ] **Step 3:** 写实现 `src/genre_extractor/from_description.py`：

```python
"""Create a preset from a free-text description (single LLM call).

Unlike to_preset.extract_to_preset which reads novels, this path takes a
natural-language description and asks the LLM to synthesize the whole blueprint
in one shot. Useful when the user knows what they want but has no source
material to scan.

Output shape matches the other preset creation paths — 3 required md files,
optional resource_schema.yaml (LLM decides based on description content).
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import yaml

from src import config, llm
from src.genre_extractor import core

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是资深中文小说责编，擅长把一段题材需求描述转成完整的题材规范。

用户会给你：
- 一段自由文本描述（时代 / 地域 / 基调 / 禁忌 / 风格 / 可能的可追踪资源）

你要输出**严格的 YAML**（不要 markdown 代码块，不要注释），schema：

```
era: |
  # Era
  <时代/世界观事实包，markdown，≥ 400 字>

writing_style_extra: |
  # Writing Style
  <题材特有写作风格，markdown，≥ 200 字>

iron_laws_extra: |
  # Iron Laws
  <题材特有铁律列表，markdown，≥ 5 条>

resource_schema: null
# 或者，如果描述里提到了可追踪资源（灵石/金币/情报值/因果值 等），输出：
# resource_schema:
#   resources:
#     - name: spirit_stone
#       unit: 颗
#       visibility: public    # public / private
#     - ...
```

规则：
1. 三段 markdown 内容必须完整、具体、可落地。不要只写一句"TODO"。
2. 默认 resource_schema 为 null。只有用户描述里**明确提到**可追踪资源量时才填 schema。
3. 只输出 YAML。不要代码块。不要额外说明。
"""


def _parse_llm_output(raw: str) -> dict:
    """Parse LLM output into blueprint dict. Raise ValueError on bad output."""
    if not raw or not raw.strip():
        raise ValueError("LLM output is empty")
    # Strip accidental markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        _, _, text = text.partition("\n")
        text = text.rpartition("```")[0] if "```" in text else text
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"LLM output is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"LLM output is not a dict (got {type(data).__name__})")
    for key in ("era", "writing_style_extra", "iron_laws_extra"):
        if key not in data or not data[key]:
            raise ValueError(f"LLM output missing required field: {key}")
    return data


def _blueprint_from_parsed(parsed: dict) -> dict:
    """Shape parsed LLM dict into the format render_files_from_blueprint expects."""
    return {
        "era": {"content": str(parsed["era"]).strip() + "\n"},
        "writing_style_extra": {"content": str(parsed["writing_style_extra"]).strip() + "\n"},
        "iron_laws_extra": {"content": str(parsed["iron_laws_extra"]).strip() + "\n"},
        "resource_schema": parsed.get("resource_schema") or None,
    }


def extract_from_description(
    preset_id: str,
    *,
    display_name: str,
    tone: str,
    description: str,
) -> dict:
    """Generate a preset from a free-text description via a single LLM call.

    Raises:
        ValueError: invalid id / empty description / bad LLM output.
        FileExistsError: preset already exists.
    """
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", preset_id):
        raise ValueError(f"invalid preset id: {preset_id!r}")
    if not description or not description.strip():
        raise ValueError("description must not be empty")

    preset_dir = config.PRESETS_DIR / preset_id
    if preset_dir.exists():
        raise FileExistsError(f"Preset already exists: {preset_id}")

    # Call LLM
    user_prompt = (
        f"题材 id: {preset_id}\n"
        f"显示名: {display_name or preset_id}\n"
        f"基调: {tone or '(未指定)'}\n\n"
        f"题材描述：\n{description}\n"
    )
    raw = llm.chat(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        agent_name="preset_from_description",
        temperature=0.4,
        max_tokens=4000,
        response_format="text",
    )

    # Parse. If bad, abort cleanly — don't leave a half-built preset.
    try:
        parsed = _parse_llm_output(raw)
    except ValueError:
        raise

    # Write files
    preset_dir.mkdir(parents=True)
    try:
        (preset_dir / "novels").mkdir()
        (preset_dir / "novels" / ".gitkeep").write_text("", encoding="utf-8")

        (preset_dir / "genre.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": preset_id,
                    "display_name": display_name or preset_id,
                    "tone": tone or "",
                    "source": "description",
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        blueprint = _blueprint_from_parsed(parsed)
        core.render_files_from_blueprint(blueprint, out_dir=preset_dir)
    except Exception:
        # Clean up on any write failure
        if preset_dir.exists():
            shutil.rmtree(preset_dir)
        raise

    return {
        "preset_id": preset_id,
        "source": "description",
        "has_resource_schema": bool(blueprint.get("resource_schema")),
    }
```

- [ ] **Step 4:** 跑绿：
```bash
.venv/bin/python3 -m pytest tests/test_from_description.py -v 2>&1 | tail -10
```
期望：8/8 pass

- [ ] **Step 5:** 全套回归：
```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：476 + 8 = 484 pass

- [ ] **Step 6:** Commit：
```bash
git add src/genre_extractor/from_description.py tests/test_from_description.py
git commit -m "feat(preset-new): from_description — single LLM call produces blueprint"
```

---

## Task 3 · Web 路由 `/api/presets/new-blank` + `/api/presets/new-from-description`

**Files:**
- Modify: `web/app.py`
- Create: `tests/test_web_preset_new_routes.py`

- [ ] **Step 1:** 写测试 `tests/test_web_preset_new_routes.py`：

```python
"""POST /api/presets/new-blank + /api/presets/new-from-description."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def app_(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "ACTIVE_POINTER", tmp_path / "projects" / ".active")
    from web import app as web_app
    return web_app.app.test_client()


# -------- new-blank (sync) --------

def test_new_blank_creates_preset(app_):
    r = app_.post("/api/presets/new-blank", json={
        "id": "myblank", "display_name": "My Blank", "tone": "dry",
    })
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["preset_id"] == "myblank"


def test_new_blank_409_on_duplicate(app_):
    r1 = app_.post("/api/presets/new-blank", json={"id": "dup", "display_name": "D", "tone": ""})
    assert r1.status_code == 200
    r2 = app_.post("/api/presets/new-blank", json={"id": "dup", "display_name": "D", "tone": ""})
    assert r2.status_code == 409


def test_new_blank_400_on_missing_id(app_):
    r = app_.post("/api/presets/new-blank", json={"display_name": "X", "tone": ""})
    assert r.status_code == 400


def test_new_blank_400_on_invalid_id(app_):
    r = app_.post("/api/presets/new-blank", json={
        "id": "Bad Id", "display_name": "X", "tone": "",
    })
    assert r.status_code == 400


# -------- new-from-description (async) --------

def test_new_from_description_schedules_job(app_, monkeypatch):
    captured = {}
    def fake_extract(pid, *, display_name, tone, description):
        captured.update(pid=pid, description=description)
        return {"preset_id": pid, "source": "description", "has_resource_schema": False}
    monkeypatch.setattr(
        "src.genre_extractor.from_description.extract_from_description",
        fake_extract,
    )
    r = app_.post("/api/presets/new-from-description", json={
        "id": "mypd", "display_name": "My PD", "tone": "dark",
        "description": "港综 1983 冷硬 …",
    })
    assert r.status_code == 202
    # Wait for background
    for _ in range(40):
        s = app_.get("/api/presets/mypd/status").get_json()
        if s.get("state") in ("done", "failed"):
            break
        time.sleep(0.05)
    assert captured.get("pid") == "mypd"


def test_new_from_description_400_on_empty_description(app_):
    r = app_.post("/api/presets/new-from-description", json={
        "id": "x", "display_name": "X", "tone": "", "description": "",
    })
    assert r.status_code == 400


def test_new_from_description_400_on_missing_fields(app_):
    r = app_.post("/api/presets/new-from-description", json={"id": "x"})
    assert r.status_code == 400


def test_new_from_description_409_on_existing(app_):
    # Pre-create
    (app_.application.root_path).__str__()  # noop
    from src import config
    (config.PRESETS_DIR / "dup").mkdir()
    (config.PRESETS_DIR / "dup" / "genre.yaml").write_text("id: dup\n", encoding="utf-8")

    r = app_.post("/api/presets/new-from-description", json={
        "id": "dup", "display_name": "D", "tone": "", "description": "…",
    })
    assert r.status_code == 409
```

- [ ] **Step 2:** 跑红：
```bash
.venv/bin/python3 -m pytest tests/test_web_preset_new_routes.py -v 2>&1 | tail -15
```

- [ ] **Step 3:** 编辑 `web/app.py` 添加两个路由。定位到现有 `api_preset_new_from_novel`（`@app.post("/api/presets/new-from-novel")`）附近插入：

```python
# ---- New blank preset (sync) ----

@app.post("/api/presets/new-blank")
def api_preset_new_blank():
    body = request.get_json(silent=True) or {}
    pid = (body.get("id") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    tone = body.get("tone") or ""
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    if not display_name:
        return jsonify({"ok": False, "reason": "display_name required"}), 400
    try:
        from src.genre_extractor.blank_preset import create_blank_preset
        create_blank_preset(pid, display_name=display_name, tone=tone)
    except ValueError as e:
        return jsonify({"ok": False, "reason": str(e)}), 400
    except FileExistsError as e:
        return jsonify({"ok": False, "reason": str(e)}), 409
    return jsonify({"ok": True, "preset_id": pid})


# ---- New preset from description (async) ----

@app.post("/api/presets/new-from-description")
def api_preset_new_from_description():
    body = request.get_json(silent=True) or {}
    pid = (body.get("id") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    tone = body.get("tone") or ""
    description = (body.get("description") or "").strip()
    if not pid:
        return jsonify({"ok": False, "reason": "id required"}), 400
    if not display_name:
        return jsonify({"ok": False, "reason": "display_name required"}), 400
    if not description:
        return jsonify({"ok": False, "reason": "description required"}), 400
    if _preset_dir(pid).exists():
        return jsonify({"ok": False, "reason": "preset already exists"}), 409

    with _PRESET_JOB_LOCK:
        if pid in _PRESET_JOBS and _PRESET_JOBS[pid].get("state") == "running":
            return jsonify({"ok": False, "reason": "job already running"}), 409
        _PRESET_JOBS[pid] = {"state": "running", "error": None}

    def worker():
        try:
            from src.genre_extractor import from_description
            from_description.extract_from_description(
                pid,
                display_name=display_name,
                tone=tone,
                description=description,
            )
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid] = {"state": "done", "error": None}
        except Exception as e:
            with _PRESET_JOB_LOCK:
                _PRESET_JOBS[pid] = {"state": "failed", "error": str(e)}

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"ok": True, "preset_id": pid, "state": "running"}), 202
```

- [ ] **Step 4:** 跑绿：
```bash
.venv/bin/python3 -m pytest tests/test_web_preset_new_routes.py -v 2>&1 | tail -15
```
期望：8/8 pass

- [ ] **Step 5:** 全套回归：
```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：484 + 8 = 492 pass

- [ ] **Step 6:** Commit：
```bash
git add web/app.py tests/test_web_preset_new_routes.py
git commit -m "feat(preset-new): /api/presets/new-blank + /api/presets/new-from-description"
```

---

## Task 4 · `/presets/new` 三 tab UI 页面

**Files:**
- Create: `web/templates/presets/new.html`
- Modify: `web/app.py`（加 `GET /presets/new` 路由）
- Modify: `web/static/presets.js`（加三 tab 的 JS 逻辑）

- [ ] **Step 1:** 写 DOM 结构断言 `tests/test_preset_new_page.py`：

```python
"""GET /presets/new renders a 3-tab page."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app_(tmp_path: Path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    from web import app as web_app
    return web_app.app.test_client()


def test_get_presets_new_200(app_):
    r = app_.get("/presets/new")
    assert r.status_code == 200


def test_presets_new_has_three_tabs(app_):
    r = app_.get("/presets/new")
    body = r.get_data(as_text=True)
    for tab_id in ("from-novel", "from-description", "blank"):
        assert f'data-tab="{tab_id}"' in body, f"missing tab data-tab=\"{tab_id}\""


def test_presets_new_has_three_panels(app_):
    r = app_.get("/presets/new")
    body = r.get_data(as_text=True)
    for panel_id in ("from-novel", "from-description", "blank"):
        assert f'data-panel="{panel_id}"' in body


def test_presets_new_panels_have_required_fields(app_):
    r = app_.get("/presets/new")
    body = r.get_data(as_text=True)
    # Each panel has an id input
    assert body.count('name="id"') >= 3
    # from-description panel has description textarea
    assert 'name="description"' in body
    # from-novel panel loads novels list (has a target div)
    assert 'id="picker-body"' in body or 'novels-pool-checkboxes' in body


def test_presets_js_wires_three_tabs():
    REPO = Path(__file__).resolve().parent.parent
    text = (REPO / "web" / "static" / "presets.js").read_text(encoding="utf-8")
    # Must call all three new endpoints
    assert "/api/presets/new-from-novel" in text
    assert "/api/presets/new-from-description" in text
    assert "/api/presets/new-blank" in text
```

- [ ] **Step 2:** 跑红：
```bash
.venv/bin/python3 -m pytest tests/test_preset_new_page.py -v 2>&1 | tail -10
```

- [ ] **Step 3:** 写 `web/templates/presets/new.html`：

```html
{% extends "presets/_base.html" %}
{% block title %}新建 preset · Novelforge{% endblock %}

{% block content %}
<section class="genre-hero">
  <div class="genre-hero-mark">+</div>
  <h1 class="genre-hero-title">新建 preset</h1>
  <p class="genre-hero-sub">三条路径：读原著拆解 / 描述生成 / 手动空壳。</p>
</section>

<nav class="tabs tabs-preset-new" role="tablist">
  <button class="tab tab-active" data-tab="from-novel" role="tab">从素材库拆</button>
  <button class="tab" data-tab="from-description" role="tab">从描述生成</button>
  <button class="tab" data-tab="blank" role="tab">手动空壳</button>
</nav>

<!-- Panel 1: from-novel -->
<section class="genre-panel" data-panel="from-novel">
  <form id="form-from-novel" class="extract-form">
    <div class="form-row">
      <label for="fn-id">新 preset id</label>
      <input type="text" id="fn-id" name="id" required
             placeholder="e.g. wuxia-jianghu"
             pattern="[a-z0-9][a-z0-9-]*"
             title="小写字母 / 数字 / 连字符" />
    </div>
    <div class="form-row">
      <label>选择原著源文件</label>
      <div class="picker-summary" id="picker-summary">加载中…</div>
      <div class="picker-body" id="picker-body">
        <div class="placeholder"><div class="placeholder-title">加载 /api/novels…</div></div>
      </div>
    </div>
    <div class="form-row form-row-check">
      <label class="check-line">
        <input type="checkbox" id="fn-with-trial" name="with_trial" />
        <span>with_trial — 拆解后立刻跑 3 章试验书</span>
      </label>
    </div>
    <div class="form-row form-row-actions">
      <button type="submit" class="btn btn-primary" id="fn-submit" disabled>
        <span class="btn-glyph">⎇</span><span id="fn-submit-label">启动拆解</span>
      </button>
      <div class="form-error" id="fn-error" hidden></div>
    </div>
  </form>
</section>

<!-- Panel 2: from-description -->
<section class="genre-panel" data-panel="from-description" hidden>
  <form id="form-from-description" class="extract-form">
    <div class="form-row">
      <label for="fd-id">新 preset id</label>
      <input type="text" id="fd-id" name="id" required
             pattern="[a-z0-9][a-z0-9-]*" />
    </div>
    <div class="form-row">
      <label for="fd-display-name">显示名</label>
      <input type="text" id="fd-display-name" name="display_name" required />
    </div>
    <div class="form-row">
      <label for="fd-tone">基调（可选）</label>
      <input type="text" id="fd-tone" name="tone"
             placeholder="一句话描述整体基调" />
    </div>
    <div class="form-row">
      <label for="fd-description">题材描述（必填）</label>
      <textarea id="fd-description" name="description" rows="12" required
                placeholder="描述这个题材的时代、地域、风格、禁忌、可追踪资源等…"></textarea>
    </div>
    <div class="form-row form-row-actions">
      <button type="submit" class="btn btn-primary" id="fd-submit">
        <span class="btn-glyph">▶</span>生成 preset
      </button>
      <div class="form-error" id="fd-error" hidden></div>
    </div>
  </form>
</section>

<!-- Panel 3: blank -->
<section class="genre-panel" data-panel="blank" hidden>
  <form id="form-blank" class="extract-form">
    <div class="form-row">
      <label for="fb-id">新 preset id</label>
      <input type="text" id="fb-id" name="id" required
             pattern="[a-z0-9][a-z0-9-]*" />
    </div>
    <div class="form-row">
      <label for="fb-display-name">显示名</label>
      <input type="text" id="fb-display-name" name="display_name" required />
    </div>
    <div class="form-row">
      <label for="fb-tone">基调（可选）</label>
      <input type="text" id="fb-tone" name="tone" />
    </div>
    <div class="form-row form-row-actions">
      <button type="submit" class="btn btn-primary" id="fb-submit">
        <span class="btn-glyph">+</span>创建空壳
      </button>
      <div class="form-error" id="fb-error" hidden></div>
    </div>
  </form>
</section>

<div class="progress-box" id="progress-box" hidden>
  <div class="progress-line">
    <strong id="progress-title">启动中…</strong>
    <span id="progress-detail">等待后台响应</span>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='presets.js') }}" defer></script>
<script defer>
  document.addEventListener('DOMContentLoaded', () => {
    if (window.GenreUI && window.GenreUI.initNewPage) window.GenreUI.initNewPage();
  });
</script>
{% endblock %}
```

- [ ] **Step 4:** 加 Flask 路由到 `web/app.py`（找 `view_preset_detail` 附近）：

```python
@app.get("/presets/new")
def view_preset_new():
    return render_template("presets/new.html")
```

- [ ] **Step 5:** 在 `web/static/presets.js` 加 `initNewPage()` + 三 tab 切换 + 三个 form 的提交逻辑。先读现有文件看结构：

```bash
grep -n "window.GenreUI\|initIndex\|initNewFromNovel\|pollJobStatus" web/static/presets.js | head
```

然后在 `window.GenreUI = {...}` 里增加 `initNewPage`。核心内容：

```javascript
function initNewPage() {
  // Tab switching
  const tabs = document.querySelectorAll('.tabs-preset-new .tab');
  const panels = document.querySelectorAll('[data-panel]');
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.toggle('tab-active', x === t));
    const active = t.dataset.tab;
    panels.forEach(p => p.hidden = p.dataset.panel !== active);
  }));

  initFromNovelForm();
  initFromDescriptionForm();
  initBlankForm();
}

function initFromNovelForm() {
  const form = document.getElementById('form-from-novel');
  if (!form) return;
  // Load novels pool into picker-body
  fetch('/api/novels').then(r => r.json()).then(data => {
    const body = document.getElementById('picker-body');
    const summary = document.getElementById('picker-summary');
    body.innerHTML = '';
    summary.textContent = data.novels.length + ' 份素材';
    for (const n of data.novels) {
      const lbl = document.createElement('label');
      lbl.className = 'check-line';
      lbl.innerHTML = `<input type="checkbox" name="source" value="${n.name}"> ${n.name}`;
      body.appendChild(lbl);
    }
    // Enable submit when ≥1 checked
    body.addEventListener('change', () => {
      const checked = body.querySelectorAll('input[name=source]:checked').length;
      document.getElementById('fn-submit').disabled = checked === 0;
    });
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const sources = fd.getAll('source');
    const payload = {
      id: fd.get('id'),
      sources,
      with_trial: fd.get('with_trial') === 'on',
    };
    const err = document.getElementById('fn-error');
    err.hidden = true;
    try {
      const r = await fetch('/api/presets/new-from-novel', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (r.status === 202) {
        const data = await r.json();
        pollPresetJob(data.preset_id);
      } else {
        const d = await r.json();
        err.textContent = d.reason || r.status;
        err.hidden = false;
      }
    } catch (e) {
      err.textContent = String(e);
      err.hidden = false;
    }
  });
}

function initFromDescriptionForm() {
  const form = document.getElementById('form-from-description');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {
      id: fd.get('id'),
      display_name: fd.get('display_name'),
      tone: fd.get('tone') || '',
      description: fd.get('description'),
    };
    const err = document.getElementById('fd-error');
    err.hidden = true;
    try {
      const r = await fetch('/api/presets/new-from-description', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (r.status === 202) {
        const data = await r.json();
        pollPresetJob(data.preset_id);
      } else {
        const d = await r.json();
        err.textContent = d.reason || r.status;
        err.hidden = false;
      }
    } catch (e) {
      err.textContent = String(e);
      err.hidden = false;
    }
  });
}

function initBlankForm() {
  const form = document.getElementById('form-blank');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {
      id: fd.get('id'),
      display_name: fd.get('display_name'),
      tone: fd.get('tone') || '',
    };
    const err = document.getElementById('fb-error');
    err.hidden = true;
    try {
      const r = await fetch('/api/presets/new-blank', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        const data = await r.json();
        location.href = '/presets/' + data.preset_id;
      } else {
        const d = await r.json();
        err.textContent = d.reason || r.status;
        err.hidden = false;
      }
    } catch (e) {
      err.textContent = String(e);
      err.hidden = false;
    }
  });
}

async function pollPresetJob(pid) {
  const box = document.getElementById('progress-box');
  const title = document.getElementById('progress-title');
  box.hidden = false;
  title.textContent = '正在处理：' + pid;
  for (let i = 0; i < 600; i++) {
    const r = await fetch(`/api/presets/${pid}/status`);
    const s = await r.json();
    if (s.state === 'done') {
      location.href = '/presets/' + pid;
      return;
    }
    if (s.state === 'failed') {
      title.textContent = '失败：' + (s.error || '');
      return;
    }
    await new Promise(res => setTimeout(res, 1000));
  }
}

// Export
window.GenreUI = window.GenreUI || {};
window.GenreUI.initNewPage = initNewPage;
```

注意：如果 `window.GenreUI.initNewFromNovel` / `pollJobStatus` 等老函数还在 `presets.js`，保留；它们在 `/presets` 列表页仍被 `initIndex` 用（Task 5 会删除列表页的内嵌表单后再清理）。

- [ ] **Step 6:** 跑绿：
```bash
.venv/bin/python3 -m pytest tests/test_preset_new_page.py -v 2>&1 | tail -10
```
期望：5/5 pass

- [ ] **Step 7:** 全套回归：
```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：492 + 5 = 497 pass

- [ ] **Step 8:** 手动烟测（在本地浏览器）：
```bash
# 重启 web
scripts/web-stop.sh 2>/dev/null || true
scripts/web-start.sh
# 浏览器打开 http://localhost:5055/presets/new，三个 tab 都能切换
```

- [ ] **Step 9:** Commit：
```bash
git add web/templates/presets/new.html web/app.py web/static/presets.js tests/test_preset_new_page.py
git commit -m "feat(preset-new): /presets/new 3-tab page wires three creation paths"
```

---

## Task 5 · 清理 `/presets` 列表页 + 加 "+ 新建 preset" 按钮

**Files:**
- Modify: `web/templates/presets/index.html`
- Modify: `web/static/presets.js`（清理列表页不再需要的 initNewFromNovel 等）

- [ ] **Step 1:** 写断言测试 `tests/test_presets_index_cleaned.py`：

```python
"""After Task 5, /presets index has a single '+ 新建 preset' button pointing to /presets/new."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app_(tmp_path, monkeypatch):
    from src import config
    (tmp_path / "presets").mkdir()
    (tmp_path / "novels").mkdir()
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    from web import app as web_app
    return web_app.app.test_client()


def test_presets_index_has_new_button(app_):
    r = app_.get("/presets")
    body = r.get_data(as_text=True)
    assert 'href="/presets/new"' in body


def test_presets_index_does_not_embed_new_form(app_):
    """The legacy embedded 'new-from-novel-form' block should be gone."""
    r = app_.get("/presets")
    body = r.get_data(as_text=True)
    assert 'new-from-novel-form' not in body
    assert 'extract-form-section' not in body
```

- [ ] **Step 2:** 跑红：
```bash
.venv/bin/python3 -m pytest tests/test_presets_index_cleaned.py -v 2>&1 | tail -10
```

- [ ] **Step 3:** 编辑 `web/templates/presets/index.html`：删除 `<section id="extract-form-section">` 整块（含 `<form id="new-from-novel-form">` + `<div class="progress-box">`）。在 hero 下方加一个简洁按钮：

```html
<section class="genre-hero-cta">
  <a href="/presets/new" class="btn btn-primary btn-lg">
    <span class="btn-glyph">+</span>新建 preset
  </a>
</section>
```

同时清理 `{% block scripts %}` 里对 `initNewFromNovel` 的调用，只保留 `initIndex`：

```html
{% block scripts %}
<script src="{{ url_for('static', filename='presets.js') }}" defer></script>
<script defer>
  document.addEventListener('DOMContentLoaded', () => {
    if (window.GenreUI && window.GenreUI.initIndex) window.GenreUI.initIndex();
  });
</script>
{% endblock %}
```

- [ ] **Step 4:** 清理 `presets.js`：删除仅被列表页使用的函数（原 `initNewFromNovel` + 它的 helpers），只保留 `initIndex` / `initDetail` / `initNewPage` + 共享的 `pollPresetJob`。

用 grep 确认：
```bash
grep -n "function initNewFromNovel\|function pollJobStatus\|function setSubmitEnabled" web/static/presets.js
```
把 `initNewFromNovel` 和只被它调用的私有 helper 删掉。保留 `pollPresetJob`（Task 4 已加，用于三 tab 全部）。

- [ ] **Step 5:** 跑绿：
```bash
.venv/bin/python3 -m pytest tests/test_presets_index_cleaned.py tests/test_preset_new_page.py tests/test_web_preset_new_routes.py -v 2>&1 | tail -15
```

- [ ] **Step 6:** 全套回归：
```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：497 + 2 = 499 pass

- [ ] **Step 7:** 手动烟测：
```bash
# 浏览器：/presets 列表页上有"+ 新建 preset"按钮，没有内嵌表单
# 点按钮跳到 /presets/new，三 tab 都 work
```

- [ ] **Step 8:** Commit：
```bash
git add web/templates/presets/index.html web/static/presets.js tests/test_presets_index_cleaned.py
git commit -m "chore(preset-new): move '新建' off /presets index, into dedicated /presets/new"
```

---

## 最终验收

```bash
.venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```
期望：~499 pass。

**手动烟测清单**：
- [ ] GET `/presets` → 有 "+ 新建 preset" 按钮，没有内嵌表单
- [ ] GET `/presets/new` → 三 tab 可切换
- [ ] Tab "手动空壳" 填完提交 → 秒跳 `/presets/<id>`
- [ ] Tab "从描述生成" 填完提交 → 显示进度条 → 完成后跳 `/presets/<id>`
- [ ] Tab "从素材库拆" 勾选 novel + 提交 → 同进度条 → 完成后跳
- [ ] `/presets/<id>` 详情页正确显示新 preset 内容

最后 push：
```bash
git push
```
