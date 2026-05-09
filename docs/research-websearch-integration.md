# Websearch 按需搜索集成 · 技术选型与方案

> **状态**：研究报告 | **日期**：2026-05-10 | **范围**：仅架构选型，不写代码
> **依据**：`docs/skill-borrowings-plan.md` §20 + `docs/gap-analysis-post-mvp.md` A-1（降级后）
> **结论先行**：**不用 DeepSeek 原生 tool-call**。采用「Python 层发起搜索 → 结果注入 Evaluator retry prompt」模式。首选搜索引擎：Tavily；备选：Serper.dev + Jina Reader。

---

## 1. 搜索引擎方案对比

### 1.1 总表

| 方案 | 免费额度 | 付费起步价(每千次) | 延迟 | 国内直连(无VPN) | 实现复杂度 | LLM友好度 |
|---|---|---|---|---|---|---|
| **Tavily** | 1000次/月 | $8/k (即用即付) | ~2s | ⚠️ 部分区域需代理 | 低（pip SDK） | ⭐⭐⭐⭐⭐ 专为LLM设计 |
| **Exa** | 1000次/月 | $7/k (search) | 180ms-1s | ⚠️ 未知，可能需代理 | 中（非标准JSON） | ⭐⭐⭐⭐ 语义搜索强 |
| **Serper.dev** | 2500次注册 | $0.30-1.00/k | 1-2s | ⚠️ 不确定 | 低（REST API） | ⭐⭐⭐ Google结果，需自行提取 |
| **SerpAPI** | 100次/月 | ~$5/k | 2-3s | ⚠️ 需代理 | 低 | ⭐⭐⭐ 原始Google SERP |
| **Brave Search API** | 2000次/月($5 credit) | $5/k (search) | 快 | ⚠️ 未知 | 低（REST API） | ⭐⭐⭐⭐ 带LLM优化结果 |
| **Bing Search API** | ⚠️ **已退役(2025.8)** | N/A | N/A | N/A | N/A | N/A |
| **Jina Reader** (s.jina.ai) | 无限（限速100 RPM） | $按token计 | ~2.5s | ⚠️ 不确定 | 极低（HTTP GET） | ⭐⭐⭐⭐⭐ 自动提取内容+搜索 |
| **DuckDuckGo HTML 趴取** | 无限 | 免费 | 不稳定 | 大概率不通 | 高（反爬斗争） | ⭐⭐ 需自行清洗 |
| **SearXNG 自建** | 无限（自有实例） | 服务器费用 | 中等 | ✅ 自己部署可直连 | 高（需Docker部署） | ⭐⭐⭐ 可配置JSON输出 |

### 1.2 逐方案分析

#### Tavily（推荐首选）

- **定价**：免费 1000 credits/月；Pro $30/月(4000 credits)；即用即付 $0.008/credit。一次 basic search = 1 credit
- **API 形状**：Python SDK `tavily-python`，`TavilyClient(api_key="tvly-...").search("query")`，返回 `{results: [{title, url, content, score}]}`
- **LLM 优化**：重排序结果，提取信息丰富片段，减少 token 浪费。结果直接可注入 prompt
- **国内可用性**：Tavily 已支持 proxy（v0.5.2+），可通过环境变量 `TAVILY_HTTP_PROXY` 配置。但 api.tavily.com 本身是否被墙不确定——Firecrawl 用户反馈「在中国用不了 API」，Tavily 同理存在风险
- **可靠性**：已知 Cloudflare 保护网站（如 Crunchbase）可能被拦截

#### Exa（语义搜索）

- **定价**：免费 1000次/月；$7/k requests（含10条结果的content）；额外结果 $1/k
- **API 形状**：`exa_py` SDK，`client.search_and_contents("query")`，返回语义匹配结果（非关键词搜索）
- **优势**：180ms 延迟选项（instant），适合 agent 实时回路；语义搜索找「1983年香港黑色星期六」这种模糊查询可能更好
- **国内可用性**：不确定。Exa 是美国公司，无公开 proxy 配置文档
- **可靠性**：内容提取质量优秀，但搜索结果依赖其自有索引（不如 Google 覆盖面广）

#### Serper.dev（Google 包装）

- **定价**：注册送 2500次；$50/50k次($1/k)；$375/500k次($0.75/k)；$3750/12.5M次($0.30/k)
- **API 形状**：`POST https://google.serper.dev/search`，`{"q": "query"}`，返回 Google SERP JSON
- **优势**：Google 级覆盖面，价格极低（$0.30-1.00/k），延迟 1-2s
- **劣势**：原始搜索结果需要自行清洗提取正文（只有 title + snippet，无全文 content）。对于事实核查（如「1983年9月港股暴跌具体日期」）足够了
- **国内可用性**：google.serper.dev 本身可能可访问，但结果来源是全球 Google，国内可能有延迟。无公开 proxy 支持

#### Brave Search API

- **定价**：每月 $5 free credit（约 1000 次 search）；$5/k search；AI answers $4/k + token 费
- **API 形状**：`GET /res/v1/web/search?q=query`，Header: `X-Subscription-Token`
- **优势**：独立搜索索引（非 Google 依赖），隐私友好，有 LLM 优化结果。免费额度算慷慨
- **国内可用性**：不确定。Brave 浏览器在国内用的人少，API 是否被墙未知

#### Bing Search API — ⚠️ 已退役

2025年8月11日起 Bing Search API v7 退役，替代品是「Grounding with Bing Search」（Azure AI Agents 专有）。对独立 Python pipeline 不可用。

#### Jina Reader 搜索（s.jina.ai）— 轻量备选

- **定价**：无限免费（100 RPM 限速，无 API Key）；付费 API Key 可提至 1000 RPM。每次请求固定消耗 token（从 10000 起计）
- **API 形状**：`GET https://s.jina.ai/your+search+query`，返回 format=json 时得到 `[{title, content, url}]` × 5 条
- **独特优势**：搜索 + 自动抓取前 5 条结果全文转 Markdown。**一次调用 = 搜索 + 内容提取**，无需「先搜 URL、再爬网页」两步
- **国内可用性**：Jina AI 总部深圳，s.jina.ai 在国内应可访问（但需验证）
- **劣势**：搜索质量不如 Google/Bing；限速严格；没有查询参数定制（无法指定 region、时间范围）

#### DuckDuckGo HTML 趴取 — 不推荐

- **免费**但极其脆弱。反爬措施包括：Rate Limiting（202 Ratelimit）、IP 封禁、CAPTCHA
- 即使加 residential proxy 和 3-5秒延迟，在 2025-2026 年已越来越难稳定使用
- **结论**：不适合作为 pipeline 依赖。成本从「免费」变为「proxy 费用 + 维护时间」

#### SearXNG 自建 — 长期可选

- **成本**：自己部署 Docker 实例（或使用 searx.space 上的公共实例）
- **国内可直连**：部署在腾讯云/阿里云即可。可配置只用 Bing（大陆可用）作为后端
- **API**：JSON 格式（`?format=json`），Python 封装库 `searxng-wrapper` 可用
- **适合谁**：对隐私敏感或长期运行、搜索量大（≥ 每天几百次）的场景。初期 6h 预算不够

---

## 2. DeepSeek Tool-Call 兼容性分析

### 2.1 关键发现：DeepSeek-V4-Pro 支持 tool-call，但有已知 Bug

**官方文档确认**：
- DeepSeek-V4-Pro 支持 OpenAI 兼容的 `tools: [...]` + `tool_choice` 参数
- 支持 thinking mode（reasoning）下的 tool calling
- 支持 strict mode（Beta）
- API 格式与 OpenAI 完全一致（只需换 `base_url`）

**关键 Bug（GitHub Issue #1244，2026-04-24 报告）**：
- **症状**：DeepSeek-V4-Pro **间歇性**将 tool call 序列化为纯文本放在 `content` 字段中，而非用结构化 `tool_calls` 数组
- **表现**：`finish_reason: "stop"`，`tool_calls: null`，但 `content` 里包含 `函数名{"args": ...}`
- **复现率**：19 轮对话中 2 次（11%）出现此 Bug
- **触发条件**：非确定性，前一轮 tool call 成功、下一轮可能就失败。都出现在模型先输出中文文本、然后追加 tool call 的情况
- **影响**：下游 tool 执行 pipeline 会**静默失败**——收到的是文本回复而不知道要执行什么 tool

**EasyClaw 代理层**：
- EasyClaw 代理（`work-api-srv.easyclaw.cn`）是 OpenAI 兼容的透传代理
- 理论上它只是转发 `tools` 参数，不会拦截或修改
- 但如果 EasyClaw 在 thinking mode 下丢失 `reasoning_content`，多轮 tool call 可能失败（已知 OpenClaw/Venice 有过此问题）
- **我们不用 thinking mode**（当前 `llm.py` 没发 `reasoning_effort`），所以这个问题不影响我们

### 2.2 如果用 DeepSeek 原生 tool-call，JSON 形状

```python
# 请求 payload
payload = {
    "model": "deepseek-v4-pro",
    "messages": [
        {"role": "system", "content": "你是事实核查助手。"},
        {"role": "user", "content": "1983年9月香港黑色星期六具体是哪一天？"}
    ],
    "tools": [{
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取实时信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索词"}
                },
                "required": ["query"]
            }
        }
    }],
    "tool_choice": "auto"  # 或 {"type": "function", "function": {"name": "web_search"}}
}
```

```python
# 正常响应（79% 概率）
{
    "choices": [{
        "message": {
            "role": "assistant",
            "content": null,
            "tool_calls": [{
                "id": "call_xxx",
                "type": "function",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "1983年 香港 黑色星期六 日期"}'
                }
            }]
        },
        "finish_reason": "tool_calls"
    }]
}

# Buggy响应（11% 概率）— tool call 在 content 里
{
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "需要查一下这个历史事件的具体日期。\nweb_search{\"query\": \"1983年 黑色星期六 港股暴跌\"}",
            "tool_calls": null
        },
        "finish_reason": "stop"
    }]
}
```

### 2.3 DeepSeek tool-call 结论

**对生产 pipeline 不推荐使用**。理由：
1. 11% Bug 率看起来低，但对「确定性 pipeline」来说是致命缺陷——Evaluator 静默失败意味着漏过本该发现的事实错误
2. Bug 修复时间未知（4月24日报告至今未关闭）
3. 多轮 tool call（Evaluator 先触发搜索、结果回来再生成 verdict）在 Bug 存在时复杂度过高

### 2.4 备选：正则解析「伪 tool call」模式

如果坚持让 LLM 在文本里调用，可用以下模式：

```python
# Evaluator prompt 里教 LLM 输出：
# "如果需要搜索，输出：<<SEARCH: 搜索词>>"
# Python 层正则匹配：r'<<SEARCH:\s*(.+?)>>'

import re
match = re.search(r'<<SEARCH:\s*(.+?)>>', evaluator_response)
if match:
    query = match.group(1).strip()
    # 执行搜索...
```

这比用 tool-call API 更可控，但失去了「模型智能决定何时搜索」的灵活性。

---

## 3. 架构集成方案

### 3.1 决策：Python 层搜、不靠 LLM tool-call

理由：
- DeepSeek tool-call 不稳定（§2）
- Evaluator 本身已读 `era.md` + `timeline.yaml`，大多数事实错误可以被已有静态文件捕获
- 仅在「静态事实不足以判定」且「疑似 landmine_13」时触发搜索

### 3.2 推荐流程

```
Evaluator (第1次调用)
  ├─ 读：chNNN.md + 18-landmines + 24-iron-laws + era.md + timeline.yaml
  ├─ 输出：verdict draft（含 landmine_13 判定）
  │
  ├─ 如果 landmine_13.hit == true 且 evidence 不足 → Python 层触发：
  │   1. 从 landmine_13.evidence 提取搜索词（如果 Evaluator 已提供）
  │   2. 或根据 chapter 主题 + era.md 关键词构造搜索词
  │   3. 调用 search() → 得到结果 → 缓存
  │   4. 构造修正 prompt：原始 system prompt + "以下是一份外部搜索验证结果：\n{search_results}\n\n请重新判定 landmine_13，以搜索结果为权威参考（但若搜索无结果，按原有规则判定）。"
  │
  └─ Evaluator (第2次调用，仅当触发搜索时)
       └─ 输出：最终 verdict.json（含 `external_checks` 字段）
```

### 3.3 为什么这是更简单的路径

| 方案 | LLM调用次数 | Python代码复杂度 | 可控性 | 失败模式 |
|---|---|---|---|---|
| Evaluator 用 tool-call | 1-3次（取决于是否需要多轮） | 高（处理 tool_calls + 重入 + Bug兼容） | 低（依赖模型行为稳定性） | 静默失败 |
| Python 层搜 + Evaluator retry | 1-2次 | 低（简单 HTTP call + prompt拼接） | 高（完全由代码控制） | 搜索失败 → fallback到原始判定 |

### 3.4 预算与限流

**搜索缓存**：
- 缓存 key = 搜索 query 的 SHA256 前 16 位
- 缓存存储 = `state/websearch_cache.json`（JSON dict，跨章持久化）
- 有效期：24 小时（事实类查询不频繁变化）
- 清理策略：文件超过 100 条时，删除最早 20 条

**限流**：
- 每章最多 3 次搜索（Evaluator retry 算 1 次，如果搜索失败不重试）
- 全局每分钟最多 10 次（防 API 账单爆炸）
- 搜索超时 10s，超时 = fallback，不阻塞 pipeline

### 3.5 分离关注点：Python 侧 vs LLM Prompt 侧

| 层 | 职责 |
|---|---|
| **Python 代码** (`src/tools/websearch.py`) | 1. 接收搜索 query → 调用搜索 API → 返回文本结果<br>2. 缓存管理（读写 state/websearch_cache.json）<br>3. 限流控制<br>4. 失败回退（搜索超时/不可用 → 返回 None） |
| **Evaluator LLM Prompt** | 1. 判定 landmine_13 时，如果怀疑但不确定，在 verdict 中标记 `needs_external_check: true` + 提供 `suggested_query`<br>2. 在 retry prompt 中收到搜索结果后，以搜索结果为最高优先级参考，更新 verdict |

**关键**：LLM 不知道搜索是 Python 层执行的——它只输出「我需要搜索什么词」，和接收「搜索结果」。这让搜索 API 更换不影响 prompt 结构。

---

## 4. 安全与隐私

### 4.1 API Key 管理

**现状**：`.env` 存 `DEEPSEEK_API_KEY`（明文），Git 已 `.gitignore`。加 `SEARCH_API_KEY` 同理。

**风险**：`.env` 泄露 = 两个 API key 同时泄露 = DeepSeek 账单 + 搜索 API 账单双爆。

**在当前阶段可接受**：
- 这是 hackathon/open-source 项目，还没有商业账单风险
- 实施成本最低的方案是**新增 `.env` 字段 + 在 `config.py` 读取**
- 如果未来商业化，推荐方案：
  - **macOS**：用 `keyring` 库存系统钥匙串（`keyring.set_password("opencode", "SEARCH_API_KEY", "xxx")`）
  - **服务器部署**：用环境变量注入（systemd EnvironmentFile / Docker secrets）
  - **或**：`python-dotenv-vault`（`.env.vault` 加密文件 + `DOTENV_KEY` 解密）

**不建议**在 6h 预算中引入 keyring / vault——专注功能实现，`.env` 够用。

### 4.2 搜索查询泄露风险

- 搜索词如「1983年香港黑色星期六 港股暴跌 恒生指数」会暴露小说题材和具体情节
- 对于公开 benchmark / hackathon：**无风险**。这些是公开历史事实
- 对于商业小说：搜索词可能泄露尚未公开的剧情（如反派计划、关键反转）。未来需考虑：
  - 用模糊搜索词（去掉具体角色名）
  - 搜索结果仅缓存本地，不上传

**当前阶段**: 不过度设计。

---

## 5. 具体推荐

### 5.1 推荐首选：Tavily Search API

**理由**：
1. LLM 优化最好——返回结果已提取正文、自动重排序、token 友好
2. 免费 1000次/月足够 Evaluator 使用（每章触发 1-3 次，30 章 = 90 次）
3. Python SDK 一行调用
4. 支持 proxy 配置（如果国内访问需要）

**配置**：
```bash
# .env 新增
SEARCH_API_KEY=tvly-xxxxxxxxxxxxxxxx
```

### 5.2 备选：Serper.dev + Jina Reader

如果 Tavily 从大陆不通：
1. 用 **Serper.dev** 做关键词搜索（获取 URL + snippet）
2. 对感兴趣的结果 URL，用 **Jina Reader** (`r.jina.ai`) 提取全文

这是两步方案，但 Serper 便宜（$0.30/k）且 Jina Reader 国内友好。

### 5.3 6 小时实施计划

| 步骤 | 内容 | 预估 |
|---|---|---|
| **0.5h** | **注册 Tavily 账号，获取 API Key**。验证 `curl` 可达性。在 `.env.example` 加 `SEARCH_API_KEY` 字段 | 调研+配置 |
| **0.5h** | **新建 `src/tools/__init__.py` + `src/tools/websearch.py`**（~80行）。封装 `search(query: str) -> str | None`：调 Tavily SDK，超时 10s，返回拼接的文本结果，失败返回 None | 工具层 |
| **0.5h** | **缓存层**：`websearch.py` 内加 `_cache` dict + `_load_cache()` / `_save_cache()`，用 query SHA256 做 key。缓存文件 `state/websearch_cache.json` | 基础设施 |
| **1.0h** | **Evaluator prompt 修改**：在 `landmine_13` 判据中加指令：「如果判定为 hit 但证据不足，设置 `needs_external_check: true` + `suggested_query: "..."`」。在 verdict JSON schema 增加这两个字段 | Prompt 工程 |
| **1.0h** | **Evaluator Python 代码修改** (`src/agents/evaluator.py`)：`evaluate()` 改为两步——第1次调用 → 解析 verdict → 如果 `needs_external_check` 且 `suggested_query` 存在 → 调 `search()` → 构造 enriched prompt → 第2次调用（retry），输出含 `external_checks` 的最终 verdict | 核心逻辑 |
| **0.5h** | **限流**：`search()` 函数内加 `_rate_limit` 装饰器（每分 ≤10次，用 `time.monotonic()` 滑窗）。在超限时返回 None 而非抛异常 | 保护 |
| **0.5h** | **测试**：用 `pytest` 加 `test_websearch.py`（mock Tavily 响应，测缓存、限流、超时 fallback）。测试 evaluator 在 `needs_external_check=true` 时是否正确重走 | 验证 |
| **0.5h** | **集成测试 + 日志**：跑一遍 pipeline chapter N → 检查 `state/prompts_log.jsonl` 确认 search 调用被记录。在 `state/websearch_cache.json` 确认缓存写入 | 收尾 |
| **0.5h** | **缓冲**：处理意料之外的问题（Tavily 不可达→切换到 Serper、Bug 修复、文档） | 裕量 |

### 5.4 如果 6h 不够（砍范围顺序）

1. 先砍**缓存**（1.0h → 0.5h）：不做文件持久化，只做内存 dict
2. 再砍**限流**（0.5h → 0h）：依赖 Tavily 自己的 rate limit
3. 再砍**测试**（0.5h → 0h）：手动验证
4. 最后砍**enriched prompt 重走**（1.0h → 0h）：搜索失败时 Evaluator 按原始规则判定，不影响主流程

---

## 6. 风险预警

### 6.1 风险一：DeepSeek Tool-Call 不可靠（⚠️ 高危，已规避）

**风险**：DeepSeek-V4-Pro tool-call 有 11% 静默失败率（issue #1244）。
**应对**：不用 tool-call API。Python 侧正则匹配 `<<SEARCH:>>` 或 Evaluator JSON 驱动。**本文方案已完全规避此风险**。

### 6.2 风险二：搜索 API 从大陆不可达（⚠️ 中危）

**风险**：Tavily/Serper 的 API 域名可能被 GFW 阻断。
**应对**：
- 优先验证 `curl https://api.tavily.com` 在本机是否可达
- 如果不可达，Tavily SDK 支持 proxy（设置 `TAVILY_HTTP_PROXY` 环境变量）
- 备选方案：Jina Reader (`s.jina.ai`) 总部深圳，大概率可直连
- 终极兜底：搜索失败 → Evaluator 按 `era.md` 静态事实判定 → **主流程不被阻塞**

### 6.3 风险三：搜索帮倒忙（⚠️ 低危，需观察）

**风险**：搜索结果是错的/不相关/过时 → Evaluator 把错误当真理 → 误判过/不过。
**可观测性设计**：
- 每次搜索调用记录到 `state/prompts_log.jsonl`（搜索词 + 返回结果 + 用在了哪个 verdict）
- 在 `verdict.json` 的 `external_checks` 字段记录：
  ```json
  {
    "search_query": "1983年香港黑色星期六日期",
    "search_had_results": true,
    "changed_verdict": false,
    "original_landmine_13_hit": true,
    "final_landmine_13_hit": true
  }
  ```
- 如果出现 `changed_verdict: true` 但最终校对时发现改错了，就说明搜索有反作用

### 6.4 风险四：API 账单失控（⚠️ 低危）

- Tavily 免费 1000次/月。按每章 2 次搜索、30 章 = 60 次，**远低于免费额度**
- 限流（每分 ≤10次）是额外防线
- 如果未来跑 100+ 章且每章 3 次搜索 = 300 次，仍在免费额度内

### 6.5 风险五：Evaluator 第二次 LLM 调用的 token 成本

- 每次触发搜索会多一次 Evaluator LLM 调用（≈ 重新跑一次 Evaluator）
- 但如果 landmine_13 本身 hit 率低（现实中大部分章节不会触发世界观错误），额外成本可控
- 每章最多 +1 次 LLM 调用（$0.001-0.01 级别）

---

## 附录 A：DeepSeek Tool-Call 的 JSON 形状参考

### A.1 请求（带 tools 参数）

```json
{
  "model": "deepseek-v4-pro",
  "messages": [{"role": "user", "content": "查一下港股1983年9月的暴跌事件"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "web_search",
      "description": "搜索互联网获取真实信息",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"]
      }
    }
  }],
  "tool_choice": "auto"
}
```

### A.2 成功响应（正常情况）

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "web_search",
          "arguments": "{\"query\": \"1983年9月 香港 黑色星期六 恒生指数 暴跌\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

### A.3 Bug响应（11% 概率）

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "需要确认一下这个事件的具体日期。\nweb_search{\"query\": \"1983年 香港 黑色星期六\"}",
      "tool_calls": null
    },
    "finish_reason": "stop"
  }]
}
```

---

## 附录 B：源码修改点速查（供实施时参考，不展开）

| 文件 | 操作 | 说明 |
|---|---|---|
| `.env.example` | 新增 `SEARCH_API_KEY` | 搜索 API key |
| `src/config.py` | 新增 `SEARCH_API_KEY` 读取 | 从环境变量加载 |
| `src/tools/__init__.py` | 新建 | 工具包入口 |
| `src/tools/websearch.py` | 新建（~80行） | search() + 缓存 + 限流 |
| `src/agents/evaluator.py` | 修改 evaluate() | 加 needs_external_check 判定 + search retry |
| `state/websearch_cache.json` | 自动生成 | 搜索缓存 |

---

## 附录 C：结论摘要

1. **推荐方案**：Tavily Search API（Python 层调用，不依赖 DeepSeek tool-call）
2. **备选方案**：Serper.dev + Jina Reader
3. **最大风险**：搜索 API 从大陆不可达（需验证 + proxy 备选）
4. **DeepSeek tool-call 结论**：**不推荐使用**（V4-Pro 有已知 tool call 序列化 Bug，11% 失败率）
5. **预计工时**：6h（含裕量），砍范围可缩至 3h
