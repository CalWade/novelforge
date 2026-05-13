# Genre-Mining v2: 反转式架构 · 第 1 步 SensoryKitMiner

## 背景

上一轮评审（4 轮）结论，Oracle 实测：

1. **iron-laws-extra.md 召回率 = 0**（10 章 Evaluator output 中 `iron_law_extra` 字串出现次数 = 0）
2. **writing-style-extra.md 是墙纸**（Generator 的粤语气来自 `setting.tone` 而非这份文件）
3. **Planner 的核心维度全 Python 硬编码**（chapter_type/advances/writing_self_check），题材层对其**不可见**
4. **当前 4 文件骨架（era/style-extra/iron-laws-extra/resource_schema）实测无效**

根因：把"从素材**考古**（归纳事实）"和"为 Generator **立法**（规约禁令）"两件不同任务，塞进同一条 extract→merge→draft→validate 管道、用同一套 4 维桶硬吃。

## 新骨架方向（逐步替换，不一次性推翻）

从"4 文件笼统规范"→"**专用 state 文件 × 专用 miner × 生产端 agent 真消费**"的三元组。每个文件对应生产端一个具体"瞎编点"：

| 新 state 文件 | 对应 agent 瞎编点 | 产出 miner |
|---|---|---|
| `era_sensory_kit.yaml` | Planner 瞎编 `sensory_prompts` | **SensoryKitMiner（本 spec 范围）** |
| `hook_recipes.yaml` | Planner 瞎编 `opening_hook / closing_hook` | HookRecipeMiner（下一步） |
| `genre_laws.yaml` | Planner 无事前防御、Evaluator 对死文档事后审无效 | GenreLawMiner（后续） |
| `scene_playbook.yaml` | Generator 缺"本题材的场景长什么样"的样本 | ScenePlaybookMiner（后续） |
| `hook_type_taxonomy.yaml` | HookKeeper 硬编码 7 类伏笔 | HookTaxonomyMiner（后续） |
| `setting.yaml` 新增字段 | Planner 缺题材级 `chapter_type_weights` | SettingSeedMiner（后续） |

**本 spec 只做第一步**。理由：改动面最小（1 miner + 1 agent 1 字段）、端到端最短、A/B 验证 3 天闭环。

## 核心：`era_sensory_kit.yaml`

### Schema

```yaml
# era_sensory_kit.yaml — 按 location 的结构化五感清单
# 消费者：Planner（写 plan.scenes[].sensory_prompts 时按 scene.location 查表）
# 生产者：SensoryKitMiner（素材/已有章节抽取，作者可手工编辑）

schema_version: 1
locations:
  九龙城寨:
    visual:
      - "狭窄巷道上方密密麻麻的冷气机"
      - "铁皮檐上锈水痕"
      - "十二层混凝土楼体挤压出缝隙"
    auditory:
      - "冷气机滴水噼啪声"
      - "粤曲收音机"
      - "麻将碰撞声"
    olfactory:
      - "沟渠腐臭"
      - "大排档镬气"
      - "中药铺当归"
    tactile:
      - "潮湿水泥墙"
      - "铁栏杆铁锈"
      - "旅行袋尼龙带勒肩"
    gustatory:
      - "柱侯牛腩"
      - "碱水云吞面"
      - "普洱茶苦味"

  油麻地:
    visual: [...]
    ...

# 未列入 locations 的地名：Planner 用 LLM 自编（保底行为不变）
```

### 设计约束

1. **location 名称与 plan.scenes[].location 字段保持一致**（Planner 写 plan 时按 scene.location 查表）
2. **五感分类固定 5 类**：visual / auditory / olfactory / tactile / gustatory
3. **每类条目都是 verbatim 片段**，不要抽象描述。"潮湿水泥墙" 优于 "触感压抑"
4. **每 location 每类 3-5 条**。多了 Planner 注入过多、LLM 分心；少了等于没给
5. **允许 location 缺失**。新题材 / 新地点可能没有，Planner 兜底行为是 LLM 自编（保持当前行为）

## SensoryKitMiner 设计

### 输入

- **优先级 1**：已有作品的 `state/chapters/ch*.md`（从自产章节里抽，是**最准的题材样本**）
- **优先级 2**：`projects/<book>/novels/` 下的素材原著（从原著里抽）
- **优先级 3**：`era.md` 里的事实包段落（兜底，信息量有限）

本 spec 先实现 **优先级 1**（从作品自产章节抽），因为：
- 当前作品已有 10 章真实产物（demo snapshot 里）
- 自产章节 = Generator 已经执行了 era.md + writing-style-extra 的产物，抽出来的样本最贴题材
- 其他优先级留给后续 miner 任务迭代

### 算法

```
Step 1. 扫描所有章节 plan.json，收集 scenes[].location 的**完整清单**
        （按词频排序，取 top-N, N ≤ 20）

Step 2. 对每个 location，收集所有引用该 location 的章节正文片段
        （按 location 关键词在正文中定位相关段落，±500 字上下文）

Step 3. LLM 单次调用，严格抽取（temp=0.0, response_format=json）
        system: 你是风格样本抽取员。从给定文本片段里，按五感分类
                **逐字摘录**具体细节词组。不抽象、不概括、不创作。
        user:   <location>: <name>
                <excerpts>: [N 段]
                输出 JSON schema: {visual:[], auditory:[], olfactory:[], tactile:[], gustatory:[]}
                每类 3-5 条，每条 5-20 字，必须能在 excerpts 里找到对应原句

Step 4. 合并所有 location 的产出，写 state/era_sensory_kit.yaml
```

### 产物约定

- 路径：`projects/<book>/state/era_sensory_kit.yaml`
- 和现有 era.md 并存（不替换）
- 由 bootstrap_project 保底复制（若 preset 里有则拷贝，无则跳过；作品首次跑 miner 后自动生成）

## Planner 升级

### 改动点

1. `_build_prompts` 新读 `era_sensory_kit.yaml`（若存在，不强制）
2. system prompt 新增一小段：

```
【感官清单参考】
本作品有一份 era_sensory_kit.yaml，按 location 给出可用的五感样本。
写 scenes[].sensory_prompts 时：
  1. 查看本 scene 的 location 是否在 clipboard 里
  2. 若在：优先从 clipboard[location] 的 5 类里挑 2-3 条作为 sensory_prompts 的起点
  3. 若不在：沿用之前的自编方式
目的：让不同章节对同一 location 的描写共享一致的感官词汇，避免自相矛盾。
```

3. user prompt 里注入**只含本章涉及 locations 的 clipboard**（避免喂 20 个地名 × 5 类 × 5 条的噪声）

### 兼容性

- `era_sensory_kit.yaml` 不存在 → Planner 行为与当前 100% 一致（零回归）
- 存在但 location 缺失 → Planner 对该 scene 走当前路径（LLM 自编）

## Miner 的接入位置

放在 `src/genre_extractor/miners/sensory_kit.py`（新目录）。`miners/` 是新 v2 架构的根目录，与现有 `agents/` / `auditors/` 并列。不改现有 pipeline.py / to_preset.py 等 v1 路径。

CLI 入口（临时，本 spec 不做 web UI）：

```bash
python -m src.genre_extractor.miners.sensory_kit <book_id>
# 读 projects/<book_id>/state/chapters/ch*.md + plan.json
# 写 projects/<book_id>/state/era_sensory_kit.yaml
```

## 验证方式（A/B）

1. 选一个章节（如 ch6，该章尚未生成），记住 Planner 会写的 plan.json
2. A 组（不加 kit）：删掉 era_sensory_kit.yaml（或改名），跑 `python -m src.pipeline --chapter 6 --only-plan`
3. B 组（加 kit）：恢复 era_sensory_kit.yaml，同样跑
4. 人工对比两份 plan.json 的 `sensory_prompts` 字段：
   - B 组是否比 A 组更**具体、更港味、与其他章节语汇更一致**？
5. 不跑 Generator（本次只验 Planner 的变化，Generator 的收益下一步验）

## Non-goals（本 spec 明确不做）

- **不改 iron-laws-extra / writing-style-extra 现状**（保留为墙纸，下一步 GenreLawMiner 再动）
- **不从素材原著抽** sensory_kit（本次只从已有章节抽）
- **不做 web UI**（CLI 足够 A/B）
- **不写**其他 6 个 miner（SensoryKit 跑通+验证再扩展）
- **不拦截 Planner 的 chapter_type/advances 硬编码**（留到 SettingSeedMiner）

## 成功标准

1. **兼容性**：era_sensory_kit.yaml 不存在时 Planner 行为与改动前一致，所有现有测试绿
2. **新功能**：miner CLI 能为 gangster-hk-1983-linjiayao 产出一份合理的 era_sensory_kit.yaml（肉眼验证是实际"港味"词，不是通用词）
3. **真消费**：B 组 plan.json 的 sensory_prompts 出现 era_sensory_kit.yaml 里的词组（至少 1-2 条直接引用）
4. **文档**：AGENTS.md 新增"genre-mining v2"小节，说明 miner 架构方向和当前进度

## 时间估计

- Miner 本体：2-3 小时
- Planner 升级 + 测试：1 小时
- A/B 验证：1 小时

---

详见 [`docs/superpowers/plans/2026-05-14-sensory-kit-miner.md`](../plans/2026-05-14-sensory-kit-miner.md)。


## 实证：demo snapshot 10 章跑出的样本

把 `docs/demo_snapshot_gangster_c5_10ch/` 作为临时 book 跑 miner（已验证，产物清理后未入库）：

```yaml
schema_version: 1
locations:
  九龙城寨:
    visual:
    - 铁皮屋顶染成铁锈色
    - 黄色灯泡套在红色塑料罩里
    - 光晕模糊
    - 高楼把天空切割成不规则的条块
    - 夕阳只能从缝隙里漏进来
    auditory:
    - 麻将声从隔壁楼传过来
    - 收音机里放着许冠杰的《半斤八两》
    - 有人在天台上骂老婆
    - 有狗在巷子里狂吠
    olfactory:
    - 地下水沟的味道和烧腊香混在一起
  中区警署二楼审讯室:
    gustatory:
    - 咖啡
```

要点：
1. **词组 verbatim 来自 demo 章节**（"许冠杰的《半斤八两》" 出自 ch001.md）
2. **五感分类基本正确**（视觉/听觉/嗅觉条目都归位）
3. **噪声少**（没有"冷笔"、"氛围紧张"这种抽象词——严格的短词组约束起效）
4. **缺项可接受**（"中区警署审讯室"场景确实只出现 2 次，可提取的感官词组少）

## A/B 验证步骤（本地复现）

```bash
# 准备：一个已有 ≥3 章生成的作品（比如 gangster-hk-1983-linjiayao 跑过前 3 章）
python -m src.bootstrap --project gangster-hk-1983-linjiayao
python -m src.pipeline --range 1-3

# A 组（无 kit）：删掉 kit（或改名），只跑 Planner
rm -f projects/gangster-hk-1983-linjiayao/state/era_sensory_kit.yaml
python -m src.pipeline --plan-only --chapter 4
cp projects/gangster-hk-1983-linjiayao/state/chapters/ch004.plan.json /tmp/plan_A.json

# B 组（有 kit）：跑 miner 生成 kit，再跑 Planner
python -m src.genre_extractor.miners.sensory_kit gangster-hk-1983-linjiayao
rm projects/gangster-hk-1983-linjiayao/state/chapters/ch004.plan.json
python -m src.pipeline --plan-only --chapter 4
cp projects/gangster-hk-1983-linjiayao/state/chapters/ch004.plan.json /tmp/plan_B.json

# 对比两份 sensory_prompts
diff <(jq '.scenes[].sensory_prompts' /tmp/plan_A.json) \
     <(jq '.scenes[].sensory_prompts' /tmp/plan_B.json)
```

预期：B 组的 `sensory_prompts` 出现 kit 里的词组（如"铁皮屋顶染成铁锈色"），A 组则是 LLM 独立外推的变体。主观判断 B 组是否在跨章节保持更一致的"港味"词汇。
