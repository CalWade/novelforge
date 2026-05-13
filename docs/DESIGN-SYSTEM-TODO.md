# CSS 风格治理 · 技术债清单

本文件记录 stylelint 守门启用时被临时加进 ignoreFiles 的 8 个历史文件，
以及它们里面**违反**设计系统的硬编码色。

每清理完一个文件就从 `.stylelintrc.json` 的 `ignoreFiles` 里删除它，
强制它进入守门范围，这样**新违规**永远不会被引入。

## 清理流程

1. 选一个 ignore 中的文件
2. `npx stylelint <file>` 列出所有违规
3. 挨个替换：把硬编码色换成 `var(--xxx)` token
   - 若 token 不存在，先在 `tokens.css` 加一个有语义的名字
4. 再跑 `npx stylelint <file>`，0 errors
5. 从 `.stylelintrc.json` 的 ignoreFiles 数组移除该文件
6. `npm run lint:css` 全量跑一次确认没副作用

## 待处理清单

### `web/static/css/base.css`
- 若干处 `#fff` 正文色 → 改 `var(--text)` 或 `var(--amber)`

### `web/static/css/layout.css`
- 若干结构色 → 对应 `var(--line)` / `var(--panel)`

### `web/static/css/components/button.css`
- `.btn-primary` 里的 `rgba(255, 180, 84, N)` 半透明琥珀 → 保留（tokens 目前没 alpha 变体）
- 其他硬编码 hex → 换 tokens

### `web/static/css/components/dialog.css`
- `#161c27` 深色背景 → 可能是介于 `--ink-2` 和 `--panel` 之间，若必要在 tokens 加 `--ink-3`

### `web/static/css/components/overlays.css`
- 加载遮罩里大量 `#141922` / `#232a36` / `#ffb454` / `#e6edf3` / `#9aa5b5` / `#1c2230`
  这些**都有对应的 token 变量**，直接替换即可（注释已列出对应名）

### `web/static/css/components/tabs.css`
- `#0d121a` 最深色 → 加 `--ink-3` 或用 `--ink`
- `#fff` → `var(--text)`

### `web/static/css/panels/lessons.css`
- `#e87a53` / `#b794ff` / `#62d97a` → 这些是课题对照的分类色
  应在 tokens 里新增语义命名（`--lesson-1` 等）或复用 `--ag-*` agent 色

### `web/static/css/pages/novels.css`
- 有一处 `!important` → 重构 specifity
- `#0c111a` 深色 → `var(--ink)` 或新增 token

## 优先级

低。现有 8 个文件里的硬编码色都是**正确的深色主题色**（肉眼看和 tokens 一致），
只是没走变量。不改也不会有视觉污染；改了是为了后续换主题时一键生效 +
让未来的 AI 改动不会漏掉这批。

建议在**下次接触相关面板时**顺手清理，不专门排工时。
