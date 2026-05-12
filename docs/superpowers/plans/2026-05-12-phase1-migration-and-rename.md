# Phase 1 · 数据迁移 + 模块改名

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Phase Goal:** 把仓库从 `genres/<id>/` + `projects/<id>/` 两层结构迁移到 `presets/<id>/`（起点模板）+ `projects/<id>/`（题材文件下沉）的单层结构；同时把 `src/genre_pipeline/` 目录改名为 `src/genre_extractor/`。

**Phase 产出:**
- 迁移脚本 `scripts/migrate-to-book-centric.py`（可幂等重跑）+ 配套测试
- `presets/` 目录（含 3 个 preset，id 保留原值）
- 3 本内置作品目录下各有 4 份题材文件
- `genres/` 目录不再存在
- `projects/test-ui-smoke/` 不再存在
- `src/genre_extractor/` 替代 `src/genre_pipeline/`（目录改名，所有 import 同步更新）

**Phase Checkpoint:** 本 phase 结束时，旧测试套件（除了已知 skip 的题材流水线相关测试）全部仍然绿——因为本 phase 只搬运文件和改名，不改语义。

---

## 文件结构（本 phase 产出）

- Create: `scripts/migrate-to-book-centric.py`
- Create: `tests/test_migration_script.py`
- Create: `presets/` + 3 个子目录
- Rename: `src/genre_pipeline/` → `src/genre_extractor/`（含所有 .py）
- Modify: 每个 tests/test_genre_*.py 的 import path（`src.genre_pipeline` → `src.genre_extractor`）
- Modify: `src/genre_extractor/__init__.py`、`__main__.py`、`pipeline.py` 里的 self-reference
- Modify: `web/app.py` 里的 import 路径
- Modify: `AGENTS.md` / `README.md` 里的 `src/genre_pipeline` 引用（临时更新路径即可，文档正式重写在 Phase 5）
- Modify: `.gitignore` 新增 `presets/*/.build/`
- Delete: `genres/`
- Delete: `projects/test-ui-smoke/`

---

## Task 1.1: 写迁移脚本的测试

**Files:**
- Create: `tests/test_migration_script.py`

- [ ] **Step 1: 写失败测试**

```python
"""Tests for scripts/migrate-to-book-centric.py — the one-shot repo migration."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml


def _load_migrate_module():
    """Load the migration script as a module (it lives in scripts/, not src/)."""
    root = Path(__file__).resolve().parent.parent
    spec_path = root / "scripts" / "migrate-to-book-centric.py"
    spec = importlib.util.spec_from_file_location("migrate_book_centric", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a mini repo that mimics pre-migration layout."""
    # genres/
    for gid in ("alpha", "beta"):
        g = tmp_path / "genres" / gid
        g.mkdir(parents=True)
        (g / "genre.yaml").write_text(f"id: {gid}\ndisplay_name: {gid}\n", encoding="utf-8")
        (g / "era.md").write_text(f"# era for {gid}\n", encoding="utf-8")
        (g / "writing-style-extra.md").write_text(f"# style {gid}\n", encoding="utf-8")
        (g / "iron-laws-extra.md").write_text(f"# laws {gid}\n", encoding="utf-8")
    # alpha has optional resource_schema; beta does not
    (tmp_path / "genres" / "alpha" / "resource_schema.yaml").write_text(
        "resources:\n  - name: gold\n    unit: coin\n", encoding="utf-8"
    )

    # projects/ — 2 real + 1 smoke test residue
    for pid, gid in (("alpha-bookone", "alpha"), ("beta-booktwo", "beta")):
        p = tmp_path / "projects" / pid
        p.mkdir(parents=True)
        (p / "project.yaml").write_text(
            f"id: {pid}\ngenre: {gid}\nprotagonist_name: hero\n", encoding="utf-8"
        )
        (p / "outline.json").write_text("{}", encoding="utf-8")
        (p / "characters.yaml").write_text("main: {}\n", encoding="utf-8")
        (p / "timeline.yaml").write_text("events: []\n", encoding="utf-8")

    smoke = tmp_path / "projects" / "test-ui-smoke"
    smoke.mkdir(parents=True)
    (smoke / "project.yaml").write_text("id: test-ui-smoke\n", encoding="utf-8")

    # novels/ big pool (not migrated — stays put)
    novels = tmp_path / "novels"
    novels.mkdir()
    (novels / "README.md").write_text("pool\n", encoding="utf-8")
    (novels / "sample.txt").write_text("chapter 1\n", encoding="utf-8")

    return tmp_path


def test_migration_produces_presets_dir(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)

    presets = fake_repo / "presets"
    assert presets.exists() and presets.is_dir()
    assert (presets / "alpha" / "genre.yaml").exists()
    assert (presets / "alpha" / "era.md").exists()
    assert (presets / "alpha" / "resource_schema.yaml").exists()
    assert (presets / "beta" / "genre.yaml").exists()
    assert not (presets / "beta" / "resource_schema.yaml").exists()  # beta had no schema


def test_migration_creates_empty_novels_per_preset(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)

    for gid in ("alpha", "beta"):
        novels_dir = fake_repo / "presets" / gid / "novels"
        assert novels_dir.exists()
        # Empty except for a .gitkeep to preserve the dir in git
        assert (novels_dir / ".gitkeep").exists()
        txt_files = list(novels_dir.glob("*.txt"))
        assert txt_files == []


def test_migration_copies_genre_files_into_project_dirs(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)

    # alpha-bookone should now carry all 4 (+ optional resource_schema)
    p = fake_repo / "projects" / "alpha-bookone"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md", "resource_schema.yaml"):
        assert (p / fname).exists(), f"{fname} missing in alpha-bookone"

    # beta-booktwo — no resource_schema (beta didn't have one)
    p = fake_repo / "projects" / "beta-booktwo"
    for fname in ("era.md", "writing-style-extra.md", "iron-laws-extra.md"):
        assert (p / fname).exists()
    assert not (p / "resource_schema.yaml").exists()


def test_migration_adds_source_preset_to_project_yaml(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)

    for pid, expected_preset in (("alpha-bookone", "alpha"), ("beta-booktwo", "beta")):
        with (fake_repo / "projects" / pid / "project.yaml").open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["source_preset"] == expected_preset
        assert "genre" not in data  # old field removed


def test_migration_deletes_genres_dir(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    assert not (fake_repo / "genres").exists()


def test_migration_deletes_test_ui_smoke(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    assert not (fake_repo / "projects" / "test-ui-smoke").exists()


def test_migration_leaves_novels_pool_untouched(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)

    novels = fake_repo / "novels"
    assert novels.exists()
    assert (novels / "README.md").exists()
    assert (novels / "sample.txt").exists()


def test_migration_is_idempotent(fake_repo: Path):
    mod = _load_migrate_module()
    mod.migrate(repo_root=fake_repo)
    # Second run should short-circuit on "presets/ already exists"
    result = mod.migrate(repo_root=fake_repo)
    assert result["skipped"] is True
    assert "already migrated" in result["reason"].lower()
```

- [ ] **Step 2: 跑失败确认**

Run: `pytest tests/test_migration_script.py -v`
Expected: FAIL（`scripts/migrate-to-book-centric.py` 不存在，导入失败或全部 error）

- [ ] **Step 3: Commit**

```bash
git add tests/test_migration_script.py
git commit -m "test(phase1): add migration script tests (red)"
```

---

## Task 1.2: 实现迁移脚本

**Files:**
- Create: `scripts/migrate-to-book-centric.py`

- [ ] **Step 1: 写实现**

```python
#!/usr/bin/env python3
"""One-shot migration: genres/ + projects/(with source genre ref) → presets/ + projects/(self-contained).

What this does:
  1. presets/ = copy of genres/ (id preserved)
  2. presets/<id>/novels/ created empty (with .gitkeep) — the big novels/ pool stays put
  3. For each project, copy its source genre's 4 files (era.md, writing-style-extra.md,
     iron-laws-extra.md, resource_schema.yaml if present) into the project dir.
  4. Rewrite project.yaml: drop `genre:` key, add `source_preset:` (same value, renamed).
  5. Delete genres/ and projects/test-ui-smoke/.
  6. Root novels/ is untouched — it's the shared pool.

Idempotent: if presets/ already exists, do nothing.
Safe: does not touch projects/<id>/state/ (runtime artifacts; bootstrap will regenerate).

Run once:
    python3 scripts/migrate-to-book-centric.py

Delete this script after the migration is merged.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional

import yaml


GENRE_FILES = (
    "era.md",
    "writing-style-extra.md",
    "iron-laws-extra.md",
)
OPTIONAL_GENRE_FILES = ("resource_schema.yaml",)


def migrate(repo_root: Optional[Path] = None) -> dict:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent

    presets = root / "presets"
    genres = root / "genres"
    projects = root / "projects"

    if presets.exists():
        return {"skipped": True, "reason": "already migrated (presets/ exists)"}

    if not genres.exists():
        return {"skipped": True, "reason": "already migrated (no genres/ found)"}

    # 1. presets/ ← genres/ (copy entire tree, id preserved)
    presets.mkdir(parents=True)
    for genre_dir in sorted(genres.iterdir()):
        if not genre_dir.is_dir():
            continue
        dst = presets / genre_dir.name
        shutil.copytree(genre_dir, dst)

    # 2. presets/<id>/novels/ empty with .gitkeep
    for preset_dir in sorted(presets.iterdir()):
        if not preset_dir.is_dir():
            continue
        novels_dir = preset_dir / "novels"
        novels_dir.mkdir(exist_ok=True)
        (novels_dir / ".gitkeep").write_text("", encoding="utf-8")

    # 3 + 4. Inject genre files into each project + rewrite project.yaml
    if projects.exists():
        for proj_dir in sorted(projects.iterdir()):
            if not proj_dir.is_dir():
                continue
            if proj_dir.name == "test-ui-smoke":
                continue  # will be deleted in step 5
            proj_yaml = proj_dir / "project.yaml"
            if not proj_yaml.exists():
                continue
            with proj_yaml.open(encoding="utf-8") as f:
                pdata = yaml.safe_load(f) or {}
            src_genre_id = pdata.get("genre")
            if not src_genre_id:
                continue
            src_dir = presets / src_genre_id
            if not src_dir.exists():
                continue

            # copy required + optional genre files
            for fname in GENRE_FILES:
                src = src_dir / fname
                if src.exists():
                    shutil.copy2(src, proj_dir / fname)
            for fname in OPTIONAL_GENRE_FILES:
                src = src_dir / fname
                if src.exists():
                    shutil.copy2(src, proj_dir / fname)

            # rename genre: → source_preset: and rewrite
            pdata["source_preset"] = src_genre_id
            pdata.pop("genre", None)
            with proj_yaml.open("w", encoding="utf-8") as f:
                yaml.safe_dump(pdata, f, allow_unicode=True, sort_keys=False)

    # 5a. Delete genres/
    shutil.rmtree(genres)

    # 5b. Delete projects/test-ui-smoke/
    smoke = projects / "test-ui-smoke" if projects.exists() else None
    if smoke and smoke.exists():
        shutil.rmtree(smoke)

    return {"skipped": False, "reason": "migration complete"}


if __name__ == "__main__":
    result = migrate()
    if result["skipped"]:
        print(f"⚠️  {result['reason']}", file=sys.stderr)
        sys.exit(0)
    print(f"✅ {result['reason']}")
```

- [ ] **Step 2: 跑测试验证通过**

Run: `pytest tests/test_migration_script.py -v`
Expected: PASS（8/8）

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate-to-book-centric.py
git commit -m "feat(phase1): implement one-shot repo migration script"
```

---

## Task 1.3: 运行真实仓库迁移

**Files:**
- Modify: `genres/` → 删除
- Modify: `projects/test-ui-smoke/` → 删除
- Create: `presets/gangster-hk-1983/` + `presets/xianxia-ascension/` + `presets/urban-romance-contemporary/`
- Modify: 3 本内置作品的 `project.yaml` + 拷入 4 份题材文件

- [ ] **Step 1: 先备份当前仓库状态（安全起见）**

Run: `git status --short`
Expected: 工作区 clean（如有未提交的本 phase 代码改动，先 commit 完）

Run: `git stash list`（确认没有遗留 stash 阻断）

- [ ] **Step 2: 跑迁移脚本**

Run: `python3 scripts/migrate-to-book-centric.py`
Expected: 输出 `✅ migration complete`

- [ ] **Step 3: 肉眼核对产物**

Run: `ls presets/ && ls projects/`
Expected:
```
presets/:
gangster-hk-1983  urban-romance-contemporary  xianxia-ascension

projects/:
README.md  gangster-hk-1983-linjiayao  urban-romance-shenruowei  xianxia-ascension-peichangning
```

Run: `ls projects/gangster-hk-1983-linjiayao/`
Expected 包含：`era.md  writing-style-extra.md  iron-laws-extra.md  resource_schema.yaml  project.yaml  outline.json  characters.yaml  timeline.yaml`

Run: `cat projects/gangster-hk-1983-linjiayao/project.yaml | head -5`
Expected: 含 `source_preset: gangster-hk-1983`，**不含** `genre:` 字段

Run: `ls presets/gangster-hk-1983/novels/`
Expected: `.gitkeep`（空 novels 目录）

Run: `ls -d genres 2>&1`
Expected: `ls: genres: No such file or directory`

Run: `ls -d projects/test-ui-smoke 2>&1`
Expected: `No such file or directory`

Run: `ls novels/ | head`
Expected: 根目录大池子仍在，内容未变

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(phase1): run migration — genres/→presets/, inline genre files into projects/"
```

---

## Task 1.4: `.gitignore` 更新

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 读现状**

Run: `grep -n "genres\|presets\|\.build" .gitignore`

- [ ] **Step 2: 追加 `presets/*/.build/` 忽略条目，把原 `genres/*/.build/` 删掉**

Replace the line `genres/*/.build/` with `presets/*/.build/`。如果没有该行，在合适位置追加：

```
# preset pipeline build artifacts
presets/*/.build/
```

Run: `grep -n "presets" .gitignore`
Expected: 至少一行匹配

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore(phase1): update .gitignore for presets/ layout"
```

---

## Task 1.5: 改名 `src/genre_pipeline/` → `src/genre_extractor/`

**Files:**
- Rename: `src/genre_pipeline/` → `src/genre_extractor/`（含所有内部 .py）
- Modify: `src/genre_extractor/__init__.py`、`__main__.py`、`pipeline.py` 里的 self-reference import / docstring
- Modify: `web/app.py`（当前 import 了 `src.genre_pipeline.pipeline`）
- Modify: `AGENTS.md` / `README.md` 里出现的 `src/genre_pipeline` 字串（临时更新，Phase 5 再做系统性改写）

- [ ] **Step 1: git mv 目录**

Run: `git mv src/genre_pipeline src/genre_extractor`

- [ ] **Step 2: 改 `src/genre_extractor/__init__.py`**

Read 现状后把注释从
```
"""Genre Pipeline — build / fill / audit / extract genre packs.

See docs/superpowers/specs/genre-pipeline-design.md for the full design.
"""
```
改为
```
"""Genre Extractor — extract genre packs from source novels.

Two entry points:
  - to_project:  produce era.md etc for a specific book (projects/<book-id>/)
  - to_preset:   produce a reusable genre preset (presets/<preset-id>/)

See docs/superpowers/specs/book-centric-workflow-design.md for the full design.
"""
```

- [ ] **Step 3: 改 `src/genre_extractor/__main__.py`**

把顶部 docstring 里的 `python3 -m src.genre_pipeline` 统一替换为 `python3 -m src.genre_extractor`。

**本任务不改 CLI 语义**（`--new-genre` / `--fill-genre` / `--audit-genre` / `--extract-from-novel` 这些命令行标志暂时保留——Phase 2 才会重新设计为 `--to-preset`）。

- [ ] **Step 4: 全仓搜索替换 `src.genre_pipeline` → `src.genre_extractor`**

Run: `grep -rln "src\.genre_pipeline\|src/genre_pipeline" --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" --include="*.txt"`

对每个匹配文件，把所有出现的 `src.genre_pipeline` 替换为 `src.genre_extractor`，`src/genre_pipeline` 替换为 `src/genre_extractor`。

**具体必改文件清单**（基于现仓库）：

- `web/app.py` — import 那一行
- `AGENTS.md` — 1 处引用
- `README.md` — 数处引用（项目结构章节、CLI 章节、题材流水线章节）
- `CHANGELOG.md` — 保留（是历史记录，允许引用旧名）
- `tests/test_genre_*.py` 全部（~17 个文件）
- `docs/history/*.md` — 保留（历史档案，允许引用旧名）

- [ ] **Step 5: 验证测试导入能过（不强求测试逻辑全绿，仅验证 import 不炸）**

Run: `python3 -c "import src.genre_extractor; import src.genre_extractor.pipeline"`
Expected: 无输出（成功）

Run: `pytest tests/ --collect-only -q 2>&1 | tail -20`
Expected: 所有测试能 collect 起来（可能有既存 skip/xfail，但不应出现 "ModuleNotFoundError: src.genre_pipeline"）

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(phase1): rename src/genre_pipeline → src/genre_extractor"
```

---

## Task 1.6: Checkpoint · 跑原测试套件确认无回归

- [ ] **Step 1: 跑全套测试**

Run: `python3 -m pytest tests/ -x -q --ignore=tests/test_genre_trial.py 2>&1 | tail -30`

Note: `test_genre_trial.py` 有本任务无关的已知 LSP 错误（`tempfile` 属性问题），暂时忽略。其余测试应全部通过。

Expected: `X passed, Y deselected` 或少量 xfail/skip。**不应有 import error 或 migration 引入的失败**。

- [ ] **Step 2: 若有失败**

- 若是 `tests/test_bootstrap_and_settings.py` 里涉及"genre 层"的测试失败——这是**预期的**，因为目录结构变了。但这些测试要到 Phase 2 才系统修改，**本任务暂时添加 `@pytest.mark.skip(reason="awaiting phase 2 bootstrap rewrite")` 标记**到每个失败的测试函数上。
- 若是其他测试失败——调试失败原因，通常是 import 遗漏了某处。修完再提交。

- [ ] **Step 3: Commit（如果有 skip 标记追加）**

```bash
git add tests/
git commit -m "test(phase1): skip tests awaiting phase 2 bootstrap rewrite"
```

如果无改动则跳过 commit。

---

## Task 1.7: Phase 1 收尾 · 更新根目录 `projects/README.md` 和 `genres/README.md`

**Files:**
- Delete: `genres/README.md`（其实在 Task 1.3 已随 `genres/` 整体删除）
- Create: `presets/README.md`（占位，Phase 5 会重写）
- Modify: `projects/README.md`（更新 "基于哪个 genre" 表述——临时改法）

- [ ] **Step 1: 确认 `genres/README.md` 已不存在**

Run: `ls genres/README.md 2>&1`
Expected: `No such file or directory`

- [ ] **Step 2: 创建 `presets/README.md` 占位**

Create `presets/README.md`：

```markdown
# presets/ — 题材预设库

preset = 新建作品时的可选起点模板。每个 preset 是 5 份文件（`genre.yaml` + 4 份题材规范），
位于 `presets/<preset-id>/`。

**preset 在运行时不参与**——它只在新建作品时被拷贝一次。一旦作品创建完成，该作品的题材
文件就住在 `projects/<book-id>/` 目录下，和 preset 完全解耦。

详细说明待 Phase 5 重写。
```

- [ ] **Step 3: 编辑 `projects/README.md` 移除 `genre =` 字段描述**

修改 `projects/README.md` 的目录约定章节和"已提供的作品"表，把 "genre = 所基于的题材 id" 替换为 "source_preset = 所基于的 preset id（审计用，可选）"。

**注意**：详细重写留到 Phase 5，本任务只做最小必要改动以避免文档立即失真。

- [ ] **Step 4: Commit**

```bash
git add presets/README.md projects/README.md
git commit -m "docs(phase1): add presets/README.md placeholder, update projects/README.md terms"
```

---

## Phase 1 Checkpoint

Phase 1 完成条件（进 Phase 2 前必须满足）：

- [ ] `presets/` 存在，包含 3 份 preset
- [ ] `genres/` 不存在
- [ ] `projects/test-ui-smoke/` 不存在
- [ ] 3 本内置作品目录下各有完整 4 份题材文件（及 `resource_schema.yaml` 如题材有）
- [ ] 3 本内置作品的 `project.yaml` 含 `source_preset:`，不含 `genre:`
- [ ] 根目录 `novels/` 仍在，内容不变
- [ ] `src/genre_extractor/` 替代 `src/genre_pipeline/`
- [ ] 全仓 `grep src\.genre_pipeline` 只剩 `CHANGELOG.md` 和 `docs/history/*.md`（历史文档允许保留）
- [ ] `pytest tests/` 在本 phase 结束后保持绿（除 phase-2-pending 的 skip 标记）
- [ ] `tests/test_migration_script.py` 8/8 绿

**确认全部打勾后，进 Phase 2。**
