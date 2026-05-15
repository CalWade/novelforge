"""CastUpdater — maintain state/characters-cast.yaml.

Background
----------
`characters.yaml` 是**作者意图宪法**（不可变）：作品的初始 traits / redlines /
relations。但 LLM 在写作过程中会自然引入新角色（老刘、赵铁城、方洪……），
这些"先例人物"如果不被记录，CharacterGuard 就无法判断"本章某个出现在第 3
章的配角现在性格是否漂移"。

CastUpdater 解决这个问题：每章末尾覆盖式更新 `characters-cast.yaml`，
作为**运行时演员表**（已建立的先例库）。基线宪法仍以 characters.yaml 为准；
cast 文件只记录 LLM 自创角色 + 标注哪些条目镜像自基线（`in_baseline=true`）。

Reads
~~~~~
- state/chapters/ch{N:03d}.md            — 本章正文（ground truth）
- state/characters-cast.yaml             — 上一版（首次跑可不存在）
- state/characters.yaml                  — 基线宪法（用于打 in_baseline 标志）

Writes
~~~~~~
- state/characters-cast.yaml             — 完整 yaml，覆盖式

Boundary（Lesson 3）
~~~~~~~~~~~~~~~~~~~~
- 只读章节正文，不读 plan / verdict / issues：cast 是事实派生，不是策划意图。
- 永不删除条目；永不修改基线人物的 traits/redlines（如发现冲突，写进 _baseline_drift 等人审）。

Temperature 0.2 — bookkeeping，不创造。
"""
from __future__ import annotations

import yaml

from ._base import BaseAgent
from ..blackboard import Blackboard


# 给 LLM 看的 schema 文档段（在 system prompt 内引用）。
CAST_SCHEMA_DOC = """\
schema_version: 1                # 固定 1（未来 schema 演进时递增）
last_updated_chapter: <int>      # 当前刚处理完的章节号
cast:
  - name: <str>                  # 角色姓名（人名，不写代称）
    role: <str>                  # 主角 / 配角 / 反派 / 路人
    first_appeared_ch: <int>     # 首次出现的章节
    last_appeared_ch: <int>      # 最近一次出现的章节
    status: <str>                # active / offstage / dead / unknown
    one_line: <str>              # 一句话定位（身份+核心动机）
    traits: [<str>, ...]         # 累积观察到的性格特征
    redlines: [<str>, ...]       # 角色"绝不会做"的事（来自正文行为反推）
    relations:
      - to: <str>                # 关系对象（另一个角色名）
        kind: <str>              # 盟友/敌人/上下级/亲属/暧昧/中立
        evolution: <str>         # 一句话描述关系当前阶段
    voice_tags: [<str>, ...]     # 说话风格标签（口头禅、句式特征）
    aliases: [<str>, ...]        # 别名 / 绰号
    in_baseline: <bool>          # 是否出现在 characters.yaml 中
    _baseline_drift: [<str>, ...]  # 仅 in_baseline=true 时可能出现：
                                   # 正文行为与基线 traits 冲突的描述（等人审）
notes:
  pruning_policy: <str>          # 关于"何时删条目"的当前策略备注（默认：永不删）
"""


class CastUpdater(BaseAgent):
    name = "cast_updater"
    temperature = 0.2
    response_format = "text"  # 自己 yaml.safe_load 校验
    max_tokens = 4000

    def _build_prompts(self, bb: Blackboard, *, chapter: int, **_):
        chapter_path = f"chapters/ch{chapter:03d}.md"
        chapter_text = bb.read_text(chapter_path)

        baseline = bb.read_text("characters.yaml")

        if bb.exists("characters-cast.yaml"):
            prior_cast = bb.read_text("characters-cast.yaml")
            prior_note = "（下方是上一版演员表，请保留所有现有条目，只在必要处更新/新增）"
        else:
            prior_cast = "(首次运行，演员表为空 — 请基于本章正文 + 基线宪法构建)"
            prior_note = "（这是首次生成 cast 文件）"

        inputs_read = [
            f"state/{chapter_path}",
            "state/characters.yaml",
        ]
        if bb.exists("characters-cast.yaml"):
            inputs_read.append("state/characters-cast.yaml")

        system = (
            "你是 cast 维护员。每章末跑一次。读本章正文 + 上一版 cast + 基线 yaml，\n"
            "覆盖式输出**完整的** characters-cast.yaml。\n"
            "\n"
            "# 核心规则\n"
            "\n"
            "1. **新角色识别**：从本章正文里抽取『有名字、有台词或有具体行为』的角色。\n"
            "   - **不抽**：路人 A/B/C、群众、未命名的『那个男人』、街上的小贩。\n"
            "   - **抽**：林家耀、老刘、赵铁城、方洪、阿 Sir 等具名且有动作/对白的角色。\n"
            "\n"
            "2. **基线对照**：\n"
            "   - 出现在 characters.yaml（基线宪法）的角色 → `in_baseline: true`\n"
            "   - 不在基线、由 LLM 自创的角色 → `in_baseline: false`\n"
            "\n"
            "3. **更新策略**：\n"
            "   - 已存条目本章再次出现 → 更新 `last_appeared_ch`；按需补 traits / voice_tags / relations\n"
            "   - 本章首次出现 → 新增条目，`first_appeared_ch=N`，`last_appeared_ch=N`\n"
            "   - 本章死亡/退场 → `status: dead` 或 `offstage`，仍**保留条目**\n"
            "   - **永不删除条目**（哪怕 10 章未出场也保留）\n"
            "\n"
            "4. **基线保护（最关键）**：\n"
            "   - `in_baseline: true` 的角色，其 `traits` / `redlines` **只能添加，不能修改或删除**\n"
            "   - 如果本章正文行为与基线 traits 冲突 → 写进 `_baseline_drift` 数组等人审，\n"
            "     **不要悄悄改 yaml**\n"
            "\n"
            "5. **不创造正文里没出现的角色**。如果某个基线人物本章没登场，沿用上一版条目即可\n"
            "   （`last_appeared_ch` 保持原值）。\n"
            "\n"
            "6. 输出**完整 yaml**（覆盖式），不是 diff、不是 patch。\n"
            "\n"
            "# Schema\n"
            "\n"
            "```yaml\n"
            f"{CAST_SCHEMA_DOC}"
            "```\n"
            "\n"
            "# 输出要求\n"
            "\n"
            "- 严格 yaml 文档，从 `schema_version: 1` 开始。\n"
            "- **不写**散文、markdown 标题、解释性文字、```yaml ``` 代码围栏。\n"
            "- 中文使用简体；人名不加引号（YAML 字符串规范允许）。\n"
            "- 字段顺序按 schema；缺省字段写空数组 `[]` 或省略，不要写 `null`。\n"
        )

        user = (
            f"# 第 {chapter} 章正文（事实基准）\n\n"
            f"{chapter_text}\n\n"
            f"# 基线宪法 characters.yaml（不可变；用于决定 in_baseline 标志）\n\n"
            f"```yaml\n{baseline}\n```\n\n"
            f"# 上一版 characters-cast.yaml {prior_note}\n\n"
            f"```yaml\n{prior_cast}\n```\n\n"
            f"# 任务\n\n"
            f"输出更新后的完整 `characters-cast.yaml`。`last_updated_chapter: {chapter}`。"
            f"严格 yaml，无散文，无围栏。"
        )
        return system, user, inputs_read

    def _handle_output(self, bb: Blackboard, raw: str, *, chapter: int, **_):
        text = raw.strip()
        # 兼容 LLM 偶尔加的 ```yaml ... ``` 围栏
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            obj = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ValueError(f"CastUpdater LLM output is not valid YAML: {e}")

        if not isinstance(obj, dict):
            raise ValueError(
                f"CastUpdater LLM output must be a YAML mapping; got {type(obj).__name__}"
            )

        # 必需字段校验
        if "schema_version" not in obj or not isinstance(obj["schema_version"], int):
            raise ValueError("CastUpdater output missing/invalid 'schema_version' (int)")
        if "last_updated_chapter" not in obj or not isinstance(obj["last_updated_chapter"], int):
            raise ValueError(
                "CastUpdater output missing/invalid 'last_updated_chapter' (int)"
            )
        if "cast" not in obj or not isinstance(obj["cast"], list):
            raise ValueError("CastUpdater output missing/invalid 'cast' (list)")

        bb.write_yaml("characters-cast.yaml", obj)


def read_characters_cast(bb: Blackboard) -> tuple[str, list[str]]:
    """Helper for downstream auditors (CharacterGuard).

    Returns (cast_text, inputs_read). When the file does not exist yet, returns
    ('(尚无演员表——本章是首章或 cast tracking 未启用)', [])。
    """
    if bb.exists("characters-cast.yaml"):
        return bb.read_text("characters-cast.yaml"), ["state/characters-cast.yaml"]
    return "（尚无演员表——本章是首章或 cast tracking 未启用）", []
