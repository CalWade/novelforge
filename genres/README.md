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
