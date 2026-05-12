# Changelog

All notable changes to **Novelforge · 小说锻造厂**.

Format based on [Keep a Changelog](https://keepachangelog.com/). Dates are local (Asia/Shanghai).

## [Unreleased]

- 题材文件的 Web 端结构化编辑器（`era.md` / `iron-laws-extra.md` / `writing-style-extra.md`）
- Web UI 布局重构（首页 / 作品视图 / 题材视图三栏对齐）
- CI 集成 `--audit-genre` 冒烟（当前仅跑 pytest + snapshot schema 校验）

---

## 2026-05-12 — 素材库 + 编码兜底

### Added
- Web **素材库** `/novels`：批量上传 txt、拖拽支持、列表/删除 API （`42b3a1f`, `29d5c7b`）
- 题材提取页面默认从素材库选文件，不再要求手动填服务器绝对路径（`56e4ea4`）
- 上传时自动识别 **UTF-8 / GB18030 / GBK / GB2312 / Big5 / Shift-JIS / EUC-JP / EUC-KR**，统一转 UTF-8 落盘（`76cc639`, `2650413`）
- ChapterStream 下游编码兜底：CLI 绕过 Web 直接喂 GBK / Big5 文件也能正确读（`0b59b20`）
- 首页 header 加 `◎ 题材库` / `📚 素材库` 跨模块跳转按钮（`b1744a9`）

### Fixed
- `[hidden]` 属性被 `.readonly-banner { display: flex }` 规则覆盖，导致只读演示 banner 在可写环境误显（`049e7b2`）

### Infrastructure
- 建立 `novels/` 目录规范：gitignore + README 白名单（`04b8e37`）

---

## 2026-05-12 早些时候 — 题材流水线 v2（超额完成）

原计划 10 个 TDD 任务，实际合并落地为 20+ commits。

### Added — Genre Pipeline 核心
- **Extractor 两步法** prompt：Step 1 自由笔记（temp 0.3）→ Step 2 verbatim JSON 提取（temp 0.0），schema 合规率显著提升（`32f6b21`）
- **Drafter Chain-of-Density 3-pass** 迭代（可选 `cod_passes` 参数），生产级 prompt（`fc34057`）
- **Validator 扇出并行 3 Auditor**：FactChecker / ConsistencyGuard / StyleGuard，对齐作品流水线对抗人设（`279c3f2`, `678bc66`）
- **Validator → Fixer ≤2 次 retry loop** + `ship_with_debt`，沿用 Lesson 4 带伤上线约定（`a80a754`）
- **Tier-1 deny-phrase 正则扫描**：中英清单 `rules/deny-phrases-{zh,en}.txt`，不耗 token 先筛一遍（`203939a`, `3d9cefd`）
- **3-tier merge**：batch (25 章) → arc (每 4 批) → book distill（全量）。新增 `GenreArcMerger` / `GenreBookDistiller` 两个 Agent（`cbb997c`, `47b4224`, `8004eaf`）
- **6 种章节格式识别**：zh-standard / en-standard / zh-ordinal / roman / numeric / separator（`37e2c67`, `c9f3dbd`, `b4fe554`）
- **ChapterStream** 流式读 >5MB 大文件，自动滑窗（`a6f1441`, `4a053fb`）
- **自适应 batch 规模**：≤50:10 / 51-600:25 / >600:40 三档（`ff195f1`）
- `--new-genre --interactive` 问卷式脚手架（8 字段 + 3 多行列表）（`6fc9aea`）
- `--with-trial` 复用 `bootstrap_project` 的 scratch 隔离，真跑 3 章试验书（`7ae51d6`）
- `extraction_tally.md` 健康报告自动生成 + 挂进 `_run_merge`（`a52250d`, `a4217b4`）
- 4 Agent 骨架 + 主 orchestrator + CLI `new/fill/audit/extract` + Intent Router（`f4a3223`, `77c68fa`, `73c2494`）
- schemas：extraction_notes / build_status / blueprint（`c46016f`）
- Web UI 完整入口：`/genres`、`/genres/new`、`/genres/<id>`、`/genres/<id>/extract`、进度页（`cde3f3e`）

### Fixed
- 并行 merge 之后 `CANCEL_EVENT` 状态没 reset，导致串联流水线误判已取消（`280f591`）

### Tests
- pytest 用例从 **460 → 634**（净增 174，含 build_status helpers / chapter-aware split / deny-phrase / 编码兜底）

---

## 2026-05-11 — 题材流水线 v1 + 两层架构重构

### Changed — BREAKING
- **架构重构**：单层 `settings/<name>/` 拆为两层 —— `genres/<genre-id>/`（题材共享）+ `projects/<project-id>/`（作品独立）。切换作品重跑 `bootstrap`，代码无感（`a8017f0`）
- `src/core/` 下沉：`Blackboard` + `BaseAgent`，原路径保留 shim 向后兼容（`f4acfb7`, `bfc7399`）
- 错误响应统一为 `{ok: false, reason: str}` envelope，Web 前后端对齐（`9ad9823`）

### Added — Genre Pipeline v1
- `src/genre_pipeline/` 独立流水线 + CLI 四入口：`--new-genre` / `--fill-genre` / `--audit-genre` / `--extract-from-novel`（`84ed199`, `77c68fa`）
- Intent Router：`--extract-only` / `--merge-only` / `--draft-only` / `--validate-only` 断点续跑
- `genres/<id>/.build/` 构建期工作目录（进 gitignore）

### Added — Web 完整 onboarding
- `/api/genres` / `/api/projects` 列表 + activate + new 端点（`baac19f`）
- `/api/env` GET/POST（敏感字段遮罩 + 保留非白名单 key + 注入过滤 + 实时 reload）（`798aa2f`, `43077f4`, `ea2b428`, `f07f0f9`）
- `/api/project-files` GET/PUT 源文件编辑 + `preserve_progress` 重播种（`9dbba44`）
- `/api/run` 支持 **9 种模式**：chapter / range / packaging / plan-only / write-only / evaluate-only / fix-only / audit-only / bookkeeping-only + `/api/abort`（`3536963`）
- **onboarding 覆盖层**：首次访问无 API key → 引导填写；new-project 6 步向导（`7411136`）
- `CANCEL_EVENT` 协作式取消贯穿 pipeline（`d8ba6bc`）
- 请求时解析 Blackboard/status/sandbox，解决 STATE_DIR 泄漏（`2881dff`, `63fa152`）

### Security
- `bootstrap` 校验 project/genre id 防 path traversal（`3a3cf64`）
- `/api/env` 拒绝换行/null 注入（`ea2b428`）
- `Thread.start()` 失败不再泄漏 `_run_lock`（`d80aa20`）

### Infrastructure
- GitHub Actions CI + `demo_snapshot/` schema 漂移文档（`ebfe7fb`）
- 根目录 `demo_snapshot` 重复拷贝清理，10ch 快照接入 Pages（`f1f86cb`）

---

## 2026-05-10 — 小说流水线 v1（功能完整 + 长跑验证）

### Added — 新 Agent
- **FactChecker (A-1)**：按需触发的事实核查 Agent，Perplexity Sonar 后端，仅在 Evaluator 命中 `landmine_13 medium+` 时触发（`bad8eea`）
- **Multi-level Summarizer (C-12)**：L1 章摘 → L2 弧摘 → L3 卷摘三级（`e4f0eef`）
- **Lesson-3 Bookkeeping 三层账本 (C-23/24/25)**：`current_status_card.md` / `pending_hooks.md` / `resource_ledger.md`，每章末尾覆盖式更新（`1b86923`）

### Added — Prompt & Protocol
- **Cross-agent hard floor (B-1/C-32)**：信息优先级 + 风格锁，防 Generator/Fixer 漂移（`a9b83d8`）
- **Planner→Generator 协议 (C-29/A-5/C-31)**：`chapter_type` + self-check + golden-three 节拍契约（`3fea7fb`）
- **Intent Router (C-22)**：per-stage CLI 子命令（`0728a89`）

### Added — 运维工具
- `Setting Lint` 工具 + 11 单测（C-2）（`4a10a1c`）
- `Quality Dashboard` 工具（C-8）（`71e9843`）
- `urban-romance-contemporary` setting pack（C-1a）（`8706e7f`）

### Changed
- **Rebrand**：项目命名为 **Novelforge · 小说锻造厂**（`4a4d093`）
- `AGENTS.md` 从"百科全书"改为≤100 行"目录页"（`252f097`, `fec8d50`）

### Validated
- **C-5 10 章长跑**（港综 `gangster-hk-1983`）：10/10 首过 · 0 hits · 0 Fixer retry · 4098s · 92 次 LLM 调用 · 753K tokens · 45,113 字（均章 4511 字，见 `docs/c5-10ch-validation-report.md`）（`7c61529`, `c061b95`）

### Added — UX
- Loading overlay + 并行章节探测（`a8df88d`）

---

## 2026-05-09 — 首版骨架 + Evaluator 校准

### Added — Agent 体系
- 5 个创作 Agent：**Planner / Generator / Evaluator / Fixer / Summarizer**
- 2 个审计 Agent：**AISlopGuard / CharacterGuard**
- **Blackboard + BaseAgent** 抽象
- `state/` 文件系统 + `prompts_log.jsonl` 审计
- 基础 Web UI（文件树 / 章节查看器 / prompt inspector）

### Added — Evaluator 硬化 (C-10/C-17)
- **Evaluator schema 校验 + skeleton detector**：拒绝 Evaluator 回填 JSON 示例骨架，防"看似通过但 verdict 全空"（`69f6444`）
- **Evaluator 校准集**：10 case 覆盖 clean-pass / ai-slop / OOC / timeline-drift 等（`cf95eb7`）
- **三轮调优到 100% pass 对齐 · 100% recall · 58.6% precision**（见 `docs/c10-evaluator-calibration-report.md`）（`d776e6f`, `800e5f7`）

### Added — 题材与功能
- `xianxia-ascension` 题材 + Pages demo 切换器（`72078ce`）
- 5 项 skill-borrowing quick wins（C-26/27/28/30 + A-9 升级）（`9512db0`）

### Docs
- tutorial-borrowings audit（`3ac3b8b`）
- gap analysis（Oracle round 3）：MVP → 通用系统（`bb79531`）
- skill-borrowings plan（`a51f8f0`, `623c6ec`）
- 清理 MVP 黑客松脚手架，定位为通用系统（`8155fad`）

### i18n
- UI 英文标签翻译为中文，保留行业术语（`c590076`）
