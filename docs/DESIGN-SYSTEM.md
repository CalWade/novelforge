# Novelforge 设计系统

> **AI Agent 注意：改动任何 CSS 之前，先读完本文件。**
> 本文是写 CSS 的唯一入口。不读此文件直接动 CSS = 必出风格污染。

## 核心：Archive Console

视觉关键词：**深色墨蓝背景、琥珀色 accent、发丝级边框、档案感**。

- 深色墨蓝底（`#0a0e14` 附近）+ 冷色层叠
- 琥珀色 `#ffb454` 作为唯一暖色 accent —— 用于交互激活状态、primary 按钮
- 发丝边框 `#232a36`（1px，不加 shadow）
- 衬线 Fraunces 用在 display 标题
- JetBrains Mono 用在所有"LLM 数字"（latency、tokens、时间戳）
- 圆角保守：`--radius: 7px` / `--radius-sm: 4px`

❌ **永远不要**：白底、灰底、Material shadow、Bootstrap 风格的 primary 蓝、emoji 化的配色。

## Tokens — 唯一真源

**所有颜色 / 圆角 / 字体必须用 `web/static/css/tokens.css` 的 CSS 变量。**

禁止在 `tokens.css` 以外的任何文件写 `#xxx` / `rgb(...)` / `hsl(...)` / 命名色（`white`/`black`）。stylelint 会在 pre-commit 和 CI 拒绝。

### 颜色 tokens

| 变量 | 值 | 用途 |
|---|---|---|
| `--ink` | #0a0e14 | page bg（最底层） |
| `--ink-2` | #0f141c | 比 page 深一档的凹陷背景（如 view-switcher 容器） |
| `--panel` | #141922 | 卡片 / 按钮默认背景 |
| `--panel-2` | #1a2030 | 卡片 hover / 激活态面板 |
| `--line` | #232a36 | 发丝边框（标准） |
| `--line-soft` | #1c2230 | 发丝边框（更淡） |
| `--text` | #e6edf3 | 正文文字 |
| `--text-dim` | #9aa5b5 | 次要文字（标签、meta） |
| `--text-soft` | #7a8593 | 三级文字（占位符、hint） |
| `--amber` | #ffb454 | **唯一暖色 accent**（primary、active、hover 悬停态） |
| `--amber-dim` | #d48a2a | 琥珀色的边框版 |
| `--cyan` | #7fdbff | info 态（很少用） |
| `--green` | #62d97a | success |
| `--red` | #f85149 | error |
| `--red-soft` | #ff8a80 | error hover |

### Agent 调色板（prompt inspector 专用）

每个 agent 有固定色：`--ag-planner` #5aa7ff / `--ag-generator` #62d97a / `--ag-evaluator` #f85149 / `--ag-fixer` #ffb454 / `--ag-summarizer` #9aa5b5 / `--ag-ai_slop_guard` #b78dff / `--ag-character_guard` #3dd5c8。新增 genre agent 时参考 `state.js::AGENT_LABEL`。

### 字体 + 圆角

| 变量 | 用途 |
|---|---|
| `--font-ui` | UI 默认字体（Inter Tight） |
| `--font-mono` | 等宽（JetBrains Mono）— **所有数字、路径、agent 名** |
| `--font-display` | 衬线 Fraunces — h1 级别的档案标题 |
| `--radius` | 标准 7px |
| `--radius-sm` | 小圆角 4px（内嵌 tab 类） |

## 组件词汇表

写新组件前，**先 grep 有没有现成的**。下表是当前组件清单，每个文件只负责一件事：

### `web/static/css/components/`

| 文件 | 职责 | 典型用法 |
|---|---|---|
| `button.css` | `.btn` `.btn-primary` `.btn-ghost` | 所有可点击的文字按钮 |
| `pill.css` | `.pill` 状态胶囊 | 顶栏"章节 / 运行中"数字指标 |
| `tabs.css` | `.tab` / `.tab-active` | 中栏左右 tab 切换 |
| `form.css` | `.form-field` `.form-input` `.form-hint` | 表单控件 |
| `card.css` | `.card` 卡片容器 | 列表条目、dialog 内容块 |
| `dialog.css` | `.dlg` native `<dialog>` 样式 | 弹窗 |
| `toast.css` | `.toast` 临时消息 | 右下角 3s 消失通知 |
| `placeholder.css` | `.placeholder` 空态占位 | viewer 未选文件时 |
| `overlays.css` | 加载遮罩、背景蒙版 | init 首屏 |
| `view-switcher.css` | `.view-switcher` + `.view-btn` | 顶栏"作品/题材"切换 |

### `web/static/css/panels/`

| 文件 | 职责 |
|---|---|
| `tree.css` | 左侧文件树 |
| `viewer.css` | 中栏内容 viewer |
| `inspector.css` | 右栏 prompt inspector |
| `debt.css` | 技术债面板 |
| `bookkeeping.css` | 三层 bookkeeping 卡片 |
| `lessons.css` | 5 条课题对照 |

### `web/static/css/pages/`

专属于单个页面的样式（`onboarding-wizard.css` / `presets.css`）。跨页面复用的抽到 `components/`。

## 新增组件 checklist

改 CSS 前必须逐条过：

- [ ] **是否已有现成组件**？`rg "classname" web/static/css/` 过一遍。能复用就不新增。
- [ ] **只使用 tokens**？任何 `#` 颜色、`rgb()`、命名色都是错的。
- [ ] **hover / active / disabled 三态齐全**？默认 → hover（边框 `--amber-dim` + 色 `--amber`）→ active / disabled（opacity 0.4）。
- [ ] **文件归类正确**？通用组件 → `components/`；三栏面板 → `panels/`；页面专属 → `pages/`。
- [ ] **在 `index.html` 或 `presets/_base.html` 的 `<link>` 链里显式 import**？没人会发现不 import 的文件。
- [ ] **字体语义对吗**？数字/路径用 `var(--font-mono)`，大标题用 `var(--font-display)`，其余默认 `--font-ui`（继承）。
- [ ] **圆角用 tokens**？`var(--radius)` / `var(--radius-sm)`，不要 `border-radius: 8px` 自定义。

## 锚点参考组件

写任何新组件时，**照抄最接近的现有组件的结构**：

- **双档切换器** → 参考 `view-switcher.css`（容器 bg=`--ink-2` + 激活按钮用 `.btn-primary` 同款渐变）
- **数字胶囊** → 参考 `pill.css`（圆角 999px + `--font-mono`）
- **交互按钮** → 参考 `button.css` 里 `.btn` + `.btn-primary` 的渐变公式：
  ```css
  background: linear-gradient(180deg, rgba(255, 180, 84, 0.15), rgba(255, 180, 84, 0.06));
  ```
  —— hover 时 alpha 从 0.15→0.25、0.06→0.10。
- **深色下拉** → 参考 `#genre-job-selector`（`bg: --panel; border: --line; hover border: --amber-dim`）

## 反面教材（永远不要这样写）

```css
/* ❌ 白底 + Material 灰，和 archive-console 背道而驰 */
.view-btn { background: #f5f5f5; color: #666; }
.view-btn.is-active { background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

/* ❌ Bootstrap 蓝当 primary */
.btn-primary { background: #007bff; }

/* ❌ 给可点击元素加 box-shadow 当"浮起" */
.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
```

正确版本（看 `view-switcher.css` 实现）：

```css
.view-switcher { background: var(--ink-2); border: 1px solid var(--line); }
.view-btn { color: var(--text-dim); }
.view-btn:hover:not(.is-active) { color: var(--amber); background: var(--panel); }
.view-btn.is-active {
  background: linear-gradient(180deg, rgba(255, 180, 84, 0.18), rgba(255, 180, 84, 0.06));
  border-color: var(--amber-dim);
  color: var(--amber);
}
```

## 响应式

断点写在 `web/static/css/responsive.css`（必须放在 cascade 末尾）。移动端只做"能用"不做"惊艳"，Novelforge 是桌面 demo 为主。

## 自动化保障

`package.json` 有两条守门：

1. **pre-commit**：`npx stylelint "web/static/css/**/*.css"` 会拒绝：
   - 在 `tokens.css` 以外出现 `#xxx` / `rgb()` / `named-color`
   - 使用 `!important`
   - 用了未声明的 CSS 变量
2. **CI / `npm run lint:css`**：同一套规则，push 前本地跑一次更稳。

如果 lint 误报，先想"它是不是真的对了"，再考虑改 tokens；**不要**加 `/* stylelint-disable */` 绕过。
