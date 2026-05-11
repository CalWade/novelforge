# Novelforge Web 端全流程化 · 实施规划

> **For agentic workers:** 执行时使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`。本文档是方案论证 + 分期计划，代码骨架放在各任务的"最小可行代码"块里供实施者参照，不是最终实现。

**Goal:** 让一个从零拿到代码的新人，除了跑一条宿主层启动命令外，所有配置和运行动作（填 key → 选题材 → 跑章节 → 批量 → 包装 → 切换小说）都在浏览器里完成。

**Architecture:** 在 `web/app.py` 上扩展 Flask 路由，复用 `src/bootstrap.py` 和 `src/pipeline.py` 的现有函数；前端 `index.html` + `main.js` 增加首次启动向导和运行控制面板。宿主层（克隆、装依赖、启 Flask 进程）通过一键脚本或 Docker 兜底 —— 这是"鸡生蛋"边界，不可能用 Web 消除。

**Tech Stack:** Flask（已有） · Python 3.11+ · vanilla JS（现有风格，不引入框架） · 可选 Docker。

---

## 0. 现状盘点（不是 TODO，是事实基础）

读过 `web/app.py:1-290`、`src/bootstrap.py:1-186`、`src/pipeline.py` 入口、`src/config.py:1-55`、`web/templates/index.html:1-147` 后的确认：

**Web 已有（沿用）：**
- `GET /api/state` — 进度/章节/bookkeeping 快照
- `GET /api/file` — 沙箱内读文件（`state/`、`rules/`、`AGENTS.md`）
- `GET /api/prompts|debt|issues` — 日志
- `POST /api/run|audit` — 跑单章（线程 + `_run_lock` 互斥）
- `GET /api/status` — 运行状态（通过 `state/pipeline_status.json`）

**Web 缺口（对应"从零跑通"的硬阻塞）：**
1. **选题材 / 激活题材**：`src/bootstrap.py` 的核心逻辑裹在 `main()` 里（`bootstrap.py:81-182`），还没被拆成可 import 的函数；前端没有入口。
2. **.env 配置**：目前只能编辑文件。`src/config.py:11` 在 import 时 `load_dotenv` 一次性加载，意味着运行时改 .env 不生效。
3. **批量章节**：`POST /api/run` 只接 `chapter`（`web/app.py:239-258`），不支持 `range`。
4. **包装**：`src.pipeline:331 run_packaging` 函数存在，但没有 Web 端点。
5. **首次启动引导**：前端直接假设 `state/outline.json` 存在，未配置时体验崩塌。

**宿主层无法 Web 化的部分（必须 CLI 或脚本）：**
- `git clone`、`python -m venv`、`pip install`、首次 `flask run`。
- 新人用浏览器打开一个还没启动的 Flask，物理上不可能。

---

## 1. 方案论证：宿主层三选项

你问"能否全部通过 web 端操作"—— 严格答案是"应用层能，宿主层不能"。宿主层有三种兜底策略，选哪个决定了"新人上手体验"的天花板。

### 选项 A · setup.sh 一键脚本（仅 macOS/Linux 开发者）

```
用户动作：
  git clone ...
  cd opencode
  ./setup.sh            # 装 venv + deps + 启 flask
  open http://127.0.0.1:5055
```

- **优点**：改动最小（新增 ~50 行 shell）；不引入 Docker 依赖；开发者热重载自然。
- **缺点**：Windows 用户要额外 `.bat`；Python 版本、pip 源、系统依赖不一致可能炸。
- **工作量**：0.5 天。
- **适用**：你自己和熟悉 Python 的协作者。

### 选项 B · Docker + docker-compose（分发友好）

```
用户动作：
  git clone ...
  cd opencode
  docker compose up -d
  open http://127.0.0.1:5055
```

- **优点**：环境一致、跨平台、可直接部署到服务器或 Railway/Render；新人零心智负担。
- **缺点**：镜像约 200–400MB；开发时热重载要挂 volume，略麻烦；新人要装 Docker Desktop。
- **工作量**：1 天（Dockerfile + compose + state volume + 文档）。
- **适用**：要把项目分发给非工程人员、或准备托管部署。

### 选项 C · 组合（开发用 setup.sh，分发用 Docker）

- **优点**：两个场景都照顾到。
- **缺点**：维护两套启动路径，CI 里都要测。
- **工作量**：A + B ≈ 1.5 天。
- **适用**：如果你确认会同时有"开发者协作"和"对外分发"两条线。

### 选项 D · 不做宿主层

- **优点**：零改动。
- **缺点**：README 里要写 5 行命令，新人还是要懂 Python。
- **适用**：项目只有你自己用，或用户默认都是工程师。

**建议**：先只做 A（setup.sh），等真的有分发需求再加 B。不要同时上两个，避免过早优化。但这个决策我需要你最终拍板 —— 见 §6 待决策项。

---

## 2. 应用层分期计划

### P0 · 核心缺口（必做，半天到一天）

P0 三项解决"必须回 CLI"的刚需。完成后 Web 端能独立完成：填 key、切题材、批量跑章节。

---

#### Task P0-1：把 bootstrap 拆成可调用函数

**Files:**
- Modify: `src/bootstrap.py`（把 `main()` 里的激活逻辑抽出为 `activate_setting(name: str) -> dict`）

**为什么要做：**
当前 `bootstrap.py:81-182` 的所有激活逻辑（校验、拷文件、重置 progress、管理 optional 文件）都耦合在 `main()` 里，Web 只能 fork 子进程调用。拆出纯函数后 Web 能直接 `import` 并在同一进程内执行，状态立即可见、错误可捕获。

**最小可行改动：**

```python
# 新增函数，大部分逻辑从 main() 搬过来
def activate_setting(name: str) -> dict:
    """激活一个 Setting Pack，把它的 7 个必需文件 + 可选文件拷进 state/，
    重置 progress。返回执行摘要（供 Web API 展示）。
    抛 ValueError 如 name 不存在或文件不全。"""
    available = list_settings()
    if name not in available:
        raise ValueError(f"setting '{name}' not found. Available: {available}")

    setting_dir = config.PROJECT_ROOT / "settings" / name
    missing = validate_setting(setting_dir)
    if missing:
        raise ValueError(f"setting '{name}' incomplete, missing: {missing}")

    bb = Blackboard()
    copied, removed = [], []
    for fname in SETTING_FILES:
        shutil.copy2(setting_dir / fname, bb.root / fname)
        copied.append(fname)
    for fname in OPTIONAL_SETTING_FILES:
        src = setting_dir / fname
        dst = bb.root / fname
        if src.exists():
            shutil.copy2(src, dst); copied.append(fname)
        elif dst.exists():
            dst.unlink(); removed.append(fname)

    bb.write_json("progress.json", empty_progress())
    for f in ("issues.jsonl", "debt.jsonl"):
        p = bb._abs(f)
        if not p.exists(): p.touch()
    for sub in ("chapters", "summaries", "fixes"):
        (bb.root / sub).mkdir(exist_ok=True)

    prog = bb.read_json("progress.json")
    prog["active_setting"] = name
    prog["bootstrapped_at"] = datetime.now().isoformat(timespec="seconds")
    bb.write_json("progress.json", prog)

    return {"setting": name, "copied": copied, "removed": removed}

# main() 改为薄壳调用 activate_setting(args.setting) + 打印
```

**测试：**
- 单测：激活 3 个 setting、激活不存在的 setting（抛 ValueError）、激活后验证 `state/setting.yaml` 存在且内容匹配。
- 回归：CLI `python -m src.bootstrap --setting gangster-hk-1983` 行为不变。

---

#### Task P0-2：Web 新增 settings 相关端点

**Files:**
- Modify: `web/app.py`（新增 3 个路由）

**端点：**

```python
@app.get("/api/settings")
def api_settings():
    """列出所有可用的 setting pack。"""
    from src.bootstrap import list_settings
    progress = bb.read_json("progress.json") if bb.exists("progress.json") else {}
    return jsonify({
        "available": list_settings(),
        "active": progress.get("active_setting"),
        "bootstrapped_at": progress.get("bootstrapped_at"),
    })

@app.post("/api/bootstrap")
def api_bootstrap():
    """激活一个 setting。互斥：运行中的 pipeline 期间拒绝。"""
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    if not _run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "reason": "pipeline running"}), 409
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get("setting") or "").strip()
        if not name:
            return jsonify({"ok": False, "reason": "setting required"}), 400
        from src.bootstrap import activate_setting
        result = activate_setting(name)
        return jsonify({"ok": True, **result})
    except ValueError as e:
        return jsonify({"ok": False, "reason": str(e)}), 400
    finally:
        _run_lock.release()
```

**要点：**
- 激活时必须抢 `_run_lock`，避免 pipeline 跑一半被人切题材。
- 激活会 **重置 progress**，前端必须二次确认（见 P0-4 前端）。
- 不提供"备份当前 state"端点（P2 再加），先警告用户。

---

#### Task P0-3：Web 端 .env 读写 + 脱敏

**Files:**
- Modify: `web/app.py`（新增 `GET/POST /api/env`）
- Modify: `src/config.py`（新增 `reload_env()` 函数）

**关键设计：**

**读（GET）返回脱敏视图：**
```json
{
  "DEEPSEEK_API_KEY": {"set": true, "preview": "****abc1", "length": 51},
  "DEEPSEEK_BASE_URL": {"set": true, "value": "https://..."},   // 非敏感字段明文
  "DEEPSEEK_MODEL": {"set": true, "value": "deepseek-v4-pro"},
  "PERPLEXITY_API_KEY": {"set": false, "preview": null, "length": 0}
}
```

**写（POST）：**
- 请求体：`{"DEEPSEEK_API_KEY": "dc-sk-...", "PERPLEXITY_API_KEY": ""}`
- 空字符串表示清空该键。
- 未出现的键保留原值（不要求全量提交）。
- 写入后调用 `config.reload_env()` 让新值立即在本进程生效（关键：避免要求用户重启 flask）。
- 写入策略：**以 `.env` 文件为真源**，读回 → 合并 → 原子写回（写临时文件后 `os.replace`）。

**白名单（避免被当任意文件写入器滥用）：**
```python
_ENV_WRITABLE = {
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
    "PERPLEXITY_API_KEY", "PERPLEXITY_BASE_URL", "PERPLEXITY_MODEL",
}
_ENV_SENSITIVE = {"DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY"}
```

**`src/config.py` 的 reload 函数：**
```python
def reload_env() -> None:
    """重新从 .env 加载到环境变量 + module 级全局。"""
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    global PERPLEXITY_API_KEY, PERPLEXITY_BASE_URL, PERPLEXITY_MODEL
    load_dotenv(_PROJECT_ROOT / ".env", override=True)
    LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    LLM_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://work-api-srv.easyclaw.cn/v1").rstrip("/")
    LLM_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
    # ...
```

**需要注意：** `src/llm.py` 和 `src/tools/websearch.py` 如果在模块顶层捕获了 `config.LLM_API_KEY` 为局部变量，reload 会失效。要确认它们是每次调用都读 `config.X` 还是 import 时快照一次。**实施前必须 grep 一遍**：

```bash
rg -n "from\s+.*config\s+import|config\.(LLM_|PERPLEXITY_)" src/
```

如果有局部快照，一并改成惰性读取。

**测试：**
- GET 返回脱敏形式。
- POST 合法键、再 GET 看到新值。
- POST 白名单外的键被拒。
- POST 后 `src.config.LLM_API_KEY` 立即更新。

---

#### Task P0-4：`/api/run` 支持 range 参数

**Files:**
- Modify: `web/app.py`（`_chapter_arg` + `api_run`）

**设计：**
```python
# body: {"chapter": 3}  或  {"range": "1-3"}  或  {"range": [1,2,5]}
```

**语义：**
- 单章：沿用现状，`_spawn(run_chapter, ch, "full")`。
- 区间：在 worker 里串行循环，任意一章抛异常立即停并把剩余章节写入 `pipeline_status.json` 的 `pending`。
- `_run_lock` 仍然全局互斥（保持现有模型）。
- 返回 202 + `{"started": True, "chapters": [1,2,3]}`。

**关键改动（`_spawn` 泛化）：**
```python
def _spawn_range(chapters: list[int], kind: str):
    if not _run_lock.acquire(blocking=False): return False
    def _worker():
        done, failed = [], None
        for ch in chapters:
            _write_status({"running": True, "kind": kind, "chapter": ch,
                           "pending": [c for c in chapters if c > ch],
                           "done": done, "started_at": time.time()})
            try:
                pipeline.run_chapter(bb, chapter=ch)
                done.append(ch)
            except Exception as e:
                failed = {"chapter": ch, "error": f"{type(e).__name__}: {e}",
                          "traceback": traceback.format_exc()[-1200:]}
                break
        _write_status({"running": False, "kind": kind, "done": done,
                       "failed": failed, "finished_at": time.time(),
                       "ok": failed is None})
        _run_lock.release()
    threading.Thread(target=_worker, daemon=True).start()
    return True
```

**测试：**
- POST `{"range": "1-2"}` → 两章顺序跑完，status 体现进度。
- POST `{"range": "1-3"}` 人为在第 2 章注入异常 → 停在第 2 章，status.failed 有值，第 3 章不跑。

---

#### Task P0-5：前端首次启动向导 + 运行面板

**Files:**
- Modify: `web/templates/index.html`（加顶部向导条 / 模态）
- Modify: `web/static/main.js`（检测状态 → 渲染向导 → 接 P0-2/P0-3/P0-4 端点）
- Modify: `web/static/main.css`（向导样式，复用现有 token）

**流程：**

```
init() 启动时调 /api/state 和 /api/env:
  ├─ 如果 .env 没配 DEEPSEEK_API_KEY → 弹步骤 1：填 API Key
  ├─ 如果 progress.active_setting 为空 → 弹步骤 2：选 Setting
  └─ 都齐 → 直接进主界面，但顶栏加"当前题材"徽章 + 切换入口
```

**组件：**
- 顶部状态条新增"当前题材 [gangster-hk-1983] ▾"，点击弹出切换面板（列 `/api/settings`，选后 POST `/api/bootstrap`，二次确认"会重置进度，是否继续"）。
- "生成下一章" 按钮旁加"批量生成…"，点击弹输入（`1-3` / `2,5,8`），提交到 `/api/run` 带 `range`。
- 设置齿轮图标 → 打开 .env 编辑面板（两栏：DEEPSEEK 必填、PERPLEXITY 可选；敏感字段占位符显示 `****abc1`，聚焦清空占位提示"留空保留原值"）。

**复用现有风格：** 不引入新 CSS 框架。现有 `main.css` 已有 1161 行含完整设计 token，新组件用同样的 pill/card/modal 模式。

---

### P1 · 体验优化（建议做，1-2 天）

按优先级排，可选择性做：

| # | 任务 | 价值 | 成本 |
|---|---|---|---|
| P1-1 | `POST /api/packaging`（出版包装走 Web） | 补齐唯一缺失的 pipeline 动作 | 0.2 天 |
| P1-2 | SSE 实时 prompt 流（替换 `/api/prompts` 轮询） | 跑章节时实时看 LLM 产出，体验质变 | 0.5 天 |
| P1-3 | 首次启动健康检查 `/api/health`（Python 版本 / 包齐不齐 / state 可写 / key 是否 live） | 出问题早定位 | 0.3 天 |
| P1-4 | 多小说工作区：`state/<project>/` + 切换 API | 同时维护多本书 | 0.5 天 |
| P1-5 | `/api/logs` 聚合 issues + debt + prompts 的时间线视图 | 回溯调试更方便 | 0.3 天 |

**不展开细节**，等 P0 跑通、实际体验后再决定哪些值得做。

---

### P2 · 安全 & 分发（按需）

| # | 任务 | 触发条件 |
|---|---|---|
| P2-1 | Bearer token 鉴权 | Web 不再仅本机用（暴露到局域网/公网） |
| P2-2 | state 备份下载 / 导入导出 zip | 跨机迁移或灾备需求 |
| P2-3 | `/api/state/reset` 确认式清空 | 用户要求或测试频繁 |

---

## 3. 宿主层任务（取决于 §6 决策）

**若选 A（setup.sh）：**

- Create: `scripts/setup.sh`（检 Python 3.11+ → `python -m venv .venv` → `pip install -r requirements.txt` → 拷 `.env.example` 到 `.env` 如果不存在 → 启 `flask --app web.app run --port 5055`）
- Create: `scripts/setup.bat`（Windows 对应，可选）
- Modify: `README.md`（更新"如何运行"章节，从 4 行命令压到 1 行 `./scripts/setup.sh`）

**若选 B（Docker）：**

- Create: `Dockerfile`（`python:3.11-slim` + 装依赖 + `CMD flask run`）
- Create: `docker-compose.yml`（挂 `./state` 和 `./.env` 为 volume，暴露 5055）
- Create: `.dockerignore`（排除 `.venv`、`state/*.jsonl` 等运行时产物 —— 但要允许 `state/` 目录存在）
- Modify: `README.md`

**若选 C：** A + B 都做。

---

## 4. 任务依赖图

```
P0-1 (bootstrap 可调用)  ─┐
                         ├─► P0-5 (前端向导) ─► P0 完成
P0-2 (settings API)      ─┤
P0-3 (env API)           ─┤
P0-4 (range 支持)        ─┘

P1-1~P1-5  互相独立，任选
P2 全部可后置
宿主层任务 不依赖应用层，可并行
```

**可并行的 P0 组合**：P0-1/P0-3/P0-4 完全独立，可同时开工（如果用多个 fixer 并行）；P0-2 依赖 P0-1；P0-5 依赖 P0-2/P0-3/P0-4 全部完成。

---

## 5. 验收标准（定义 "done"）

P0 做完后，**在一个全新 checkout 的 repo 上**，跑下列脚本应能完整跑通：

```bash
# 前置：假设宿主层已起来（./scripts/setup.sh 或 docker compose up）
# 打开浏览器 http://127.0.0.1:5055

# 1. 首次进入 → 向导要求填 DEEPSEEK_API_KEY ✓
# 2. 向导列出 3 个 setting，点击 gangster-hk-1983 激活 ✓
# 3. 点"批量生成" → 输入 "1-2" → 两章顺序跑完 ✓
# 4. Prompt Inspector 看到每一次 LLM 调用 ✓
# 5. 点齿轮 → 切换 setting 到 xianxia-ascension（二次确认）→ 进度重置 ✓
# 6. 再次批量生成 1-1 → 仙侠题材章节产出 ✓

# 全程不打开任何终端。
```

---

## 6. 待决策项（阻塞执行）

在开工前你需要拍板：

1. **宿主层选哪个**：A（setup.sh） / B（Docker） / C（两者都做） / D（不做）
   - 我的建议：**先做 A**，分发需求出现时再补 B。
2. **切题材的 state 保留策略**：
   - 当前 `activate_setting` 保留 `chapters/` / `summaries/` / `fixes/`（沿用 CLI 行为），但 `progress.json` 被重置。结果是：切回旧题材后，旧章节文件还在，但 UI 显示从第 1 章重新开始。可能造成困惑。
   - 选项：(a) 沿用现状，前端加醒目警告；(b) `activate_setting` 接 `--archive` 把旧 state 移到 `state/archive/<timestamp>/`；(c) 强制要求先 archive 再激活。
   - 我的建议：**(a) 现状 + 前端警告**，P2 再加 archive 功能。
3. **.env 是否真的要让 Web 可写**：
   - 风险：即便脱敏显示，只要 Web 被第三方访问到（比如你忘了绑 127.0.0.1），攻击者可以覆写 API key 为自己的转发端点，白嫖你的 opencode key。
   - 选项：(a) 允许读写（脱敏，最方便）；(b) 只读 + 检测缺失（修改仍走文件）；(c) 仅在 `127.0.0.1` binding 下允许写（Flask 启动时检查）。
   - 你已选 (a) 脱敏显示，但如果 §6.1 选了 Docker，建议加 (c) 层保险。

---

## 7. 本 plan 不做的事

避免 scope creep，明确排除：

- 不引入前端框架（保持 vanilla JS）。
- 不做用户系统 / 多人协作 / 协作编辑。
- 不做 LLM 供应商切换 UI（仍只支持 DeepSeek，要改就改 .env）。
- 不做 state 的 SQL 化（文件即真源是架构原则，`AGENTS.md` 明确）。
- 不做章节编辑器（Web 只读，编辑章节请开 `state/chapters/chNNN.md`）。

---

## 自审

- **覆盖**：§0 缺口清单 5 项 ↔ P0 五个任务一一对应 ✓
- **placeholders**：检查完毕，没有 TBD/TODO；所有关键接口有最小代码示范 ✓
- **类型一致**：`activate_setting` 返回 dict 的 schema 在 P0-1 和 P0-2 一致；`.env` API 的脱敏 schema 在 P0-3 自洽 ✓
- **依赖**：§4 图标清了先后 ✓

---

## 执行交付

本 plan 已保存到 `docs/superpowers/plans/2026-05-11-web-full-onboarding.md`。

**执行前 3 个决策（§6）必须先定**。定完我可以用以下任一模式推进：

1. **Subagent-Driven**（推荐）—— 我为每个 P0 任务派独立 fixer，review 后再下一个。
2. **Inline Execution** —— 我在当前会话顺序做，关键节点 checkpoint。

或者你看完 plan 后要求改方案，再迭代这一版。
