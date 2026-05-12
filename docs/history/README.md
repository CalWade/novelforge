# docs/history/ · 历史决策档案

本目录收录 **Novelforge** 在成型过程中产出的 roadmap / 校准报告 / 借鉴审计类文档。

这些文档保留了项目的**决策脉络**——某个 Agent 为什么这么切分、某条铁律为什么这么写、某次长跑验证了哪些假设——但**不是当前系统状态的权威描述**。

## 当前系统状态的权威文档在哪里

| 想了解的东西 | 看这个文件 |
|---|---|
| 项目总览 / 如何跑 / 项目结构 | 根目录 [`README.md`](../../README.md) |
| 运行时 state 目录与 Agent 名册 | 根目录 [`AGENTS.md`](../../AGENTS.md) |
| Web UI 所有页面与 API | [`docs/web-ui-guide.md`](../web-ui-guide.md) |
| 题材流水线完整设计 | [`docs/superpowers/specs/genre-pipeline-design.md`](../superpowers/specs/genre-pipeline-design.md) |
| 5 条长链路 Agent 经验 | [`docs/Agent 搭建难题.md`](../Agent%20搭建难题.md) |
| 题材层 / 作品层规范 | [`genres/README.md`](../../genres/README.md) / [`projects/README.md`](../../projects/README.md) |
| 发布变更日志 | 根目录 [`CHANGELOG.md`](../../CHANGELOG.md) |

## 本目录内容

| 文件 | 说明 |
|---|---|
| `gap-analysis-post-mvp.md` | 从 MVP 升级到通用系统时的差距分析与路线图（32 个 C-N 任务取舍记录） |
| `skill-borrowings-plan.md` | 外部可跑 Skill → 系统借鉴计划（C-22..C-32 的来源） |
| `tutorial-borrowings-audit.md` | 教程贴 108 条 ↔ 系统落点的逐条审计 |
| `c5-10ch-validation-report.md` | 港综题材 10 章端到端长跑验证报告 |
| `c10-evaluator-calibration-report.md` | Evaluator 三轮校准到 100% pass 一致性的过程报告 |

## 这些文档不会主动更新

如果本目录描述的系统状态与当前代码产生冲突，**以代码和上述权威文档为准**。
