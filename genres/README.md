# genres/ — 题材包（Genre Pack）

这是 **Novelforge** 项目的题材定义层。

## 作用

题材包**描述"什么是这个题材"**，不描述任何具体的一本书。所有基于同一题材的
`projects/` 共享一份题材包的 `era.md` / `writing-style-extra.md` /
`iron-laws-extra.md` / 可选的 `resource_schema.yaml`。

### 举例

`genres/gangster-hk-1983/` 描述的是"1983 年港综同人这个题材应该怎么写"：
- 粤语俚语怎么用
- 英籍警察应被写成利用对象而非救世主
- 真名代指化规则
- 港币物价水平
- 14K / 和胜和 / 新义安 等社团的客观现状

这些事实**不是林家耀这本书特有的**——任何人写 1983 港综都可以复用。

## 目录约定

每个题材包是 `genres/<genre-id>/` 下的一个文件夹：

```
genres/<genre-id>/
├── genre.yaml              # 必需 · 题材元信息 + author_persona_hints + prohibited_styles
├── era.md                  # 必需 · 时代/世界观事实包
├── writing-style-extra.md  # 必需 · 题材特有风格规范
├── iron-laws-extra.md      # 必需 · 题材特有铁律
└── resource_schema.yaml    # 可选 · 可追踪资源定义（仙侠/港综有；都市言情无）
```

## 如何新增一个题材

下面五种方式从最简单到最精细，按需选择。前 3 种只产出空壳/半成品，后续仍要手工填充或用
`--extract-from-novel` 从已有小说拆解。

### 方式 1（推荐）：Web UI

启动 `flask --app web.app run --port 5055`，浏览器打开 <http://127.0.0.1:5055/genres/new>，
按表单填 id / 名称 / 时代 / 基调等字段，提交后自动产出 4 份 stub 文件。

### 方式 2：CLI 问卷式脚手架

`python3 -m src.genre_pipeline --new-genre <id> --interactive` — 8 个问题 + 3 个多行列表
（作者声音 / 禁用风格 / 避雷），产出比纯 stub 更丰富的初稿。

### 方式 3：CLI 最小脚手架

`python3 -m src.genre_pipeline --new-genre <id> --name "..." --era "..."` — 非交互，一行产出 4 份最小 stub。

### 方式 4：从已有小说拆解（推荐给有样本的场景）

```bash
python3 -m src.genre_pipeline --extract-from-novel <id> \
    --sources novels/a.txt,novels/b.txt
```

Extractor 两步法 + 滑窗 25 章/批扫描样本书，产出带 `evidence_chapters` / `confidence`
的 4 份题材文件。加 `--with-trial` 可真跑 3 章试验书验证。

### 方式 5：手工复制模板（高级）

1. 复制任意现有题材目录作为模板
2. 修改 `genre.yaml`：题材名 / 基调 / `author_persona_hints` / `genre_avoid` / `prohibited_styles`
3. 改 4 份规则文件：`era.md` / `writing-style-extra.md` / `iron-laws-extra.md`（+ 可选 schema）
4. `python -m src.tools.setting_lint --genre <genre-id>` 验证无 error
5. 基于这个题材创建第一本书：`python -m src.bootstrap --new-project <project-id> --genre <genre-id>`

## 已提供的题材

| 题材 id | 描述 | 资源定义 |
|---|---|---|
| `gangster-hk-1983` | 港综同人，1983 香港 | ✅ 情报值/黑金/人情/仇家 |
| `xianxia-ascension` | 仙侠修真，灵气复苏时代 | ✅ 灵石/灵草/境界/法器/因果 |
| `urban-romance-contemporary` | 都市言情，2024-2026 一线城市 | ❌ 故意不数值化 |

## 题材层 vs 作品层

| 项 | 位置 | 谁改 | 改动影响 |
|---|---|---|---|
| era.md / writing-style-extra / iron-laws-extra / resource_schema | `genres/` | 系统维护者 · 走 git | 影响所有使用该题材的作品 |
| outline / characters / timeline / 主角设定 | `projects/<id>/` | 作者 · Web UI 或手改 | 仅影响自己这一本书 |

详见根目录 [`AGENTS.md`](../AGENTS.md) 的"Genre + Project 分层"章节。
