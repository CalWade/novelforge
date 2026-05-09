# Blackboard Novel Pipeline Implementation Plan

> ⚠️ **历史记录 (v1.0)**：本文件是 2026-05-09 首次实施时的计划，完工后经过一次重大重构——
> `rules/writing-style.md / era-1983-hk.md / characters-canon.md` 已下沉到 `settings/<name>/`，
> Agent prompt 题材无关化。当前实际结构见 `docs/superpowers/specs/2026-05-09-blackboard-novel-pipeline-design.md` §5。
> 下文保留原貌仅作历史参考。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end multi-agent novel-writing pipeline MVP that produces 3 chapters of a 港综 novel with a Flask demo UI, deployed to a public URL, before 2026-05-10 23:59 Beijing.

**Architecture:** Outer Pipeline (chapter-by-chapter) × Inner Blackboard (state/ files as shared memory) × Auditor Fan-Out × Evaluator half-Debate. 5 primary agents + 2 background auditors. Pure Python + DeepSeek-V4-Pro via EasyClaw OpenAI-compatible proxy. No Agent framework.

**Tech Stack:** Python 3.11, httpx, Flask, PyYAML, python-dotenv. No database, no ORM, no Celery/Redis. Everything in files.

**Time Budget (approx.):** Total ≤ 12h of focused work.
- Scaffolding + rules + bootstrap: 2h
- 5 Agents + 2 Auditors: 3h
- Pipeline main loop: 1h
- Web UI: 2h
- Run + tune 3 chapters: 2h
- Deploy + README + submit: 2h

**Pragmatic trade-offs (budget-driven):**
- No unit tests except for `blackboard.py` (state I/O is the one place a bug silently corrupts the whole run)
- `llm.py` gets one smoke test (hit real API, return shape is right)
- All Agents are validated by running the pipeline end-to-end
- Git commits after each Task (not after each step)

---

## File Structure Overview

```
blackboard-novel-pipeline/  (= ~/Desktop/opencode/)
├── AGENTS.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore                    (already exists)
├── rules/
│   ├── 24-iron-laws.md
│   ├── 18-landmines.md
│   ├── writing-style.md
│   ├── era-1983-hk.md
│   └── characters-canon.md
├── src/
│   ├── __init__.py
│   ├── config.py                 (env vars, paths)
│   ├── llm.py                    (DeepSeek client wrapper + prompt_log writer)
│   ├── blackboard.py             (state/ read/write API)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── _base.py              (common BaseAgent class)
│   │   ├── planner.py
│   │   ├── generator.py
│   │   ├── evaluator.py
│   │   ├── fixer.py
│   │   └── summarizer.py
│   ├── auditors/
│   │   ├── __init__.py
│   │   ├── ai_slop_guard.py
│   │   └── character_guard.py
│   ├── pipeline.py
│   └── bootstrap.py
├── web/
│   ├── app.py                    (Flask)
│   ├── templates/index.html
│   └── static/main.css           (minimal)
├── tests/
│   └── test_blackboard.py
└── state/                        (runtime, .gitignored except .gitkeep)
    └── .gitkeep
```

---

## Task 1: Scaffolding + Blackboard + LLM Client

**Goal:** Project skeleton, state I/O, DeepSeek client with automatic prompt logging.

**Files:**
- Create: `requirements.txt`, `.env.example`, `src/__init__.py`, `src/config.py`, `src/llm.py`, `src/blackboard.py`, `tests/test_blackboard.py`, `state/.gitkeep`, `web/__init__.py`, `src/agents/__init__.py`, `src/auditors/__init__.py`

- [ ] **1.1** `requirements.txt`:
  ```
  httpx>=0.27
  flask>=3.0
  pyyaml>=6.0
  python-dotenv>=1.0
  pytest>=8.0
  ```

- [ ] **1.2** `.env.example`:
  ```
  DEEPSEEK_API_KEY=dc-sk-...
  DEEPSEEK_BASE_URL=https://work-api-srv.easyclaw.cn/v1
  DEEPSEEK_MODEL=deepseek-v4-pro
  ```

- [ ] **1.3** `src/config.py`: load dotenv, expose `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `STATE_DIR = "state"`, `RULES_DIR = "rules"`.

- [ ] **1.4** `src/llm.py`: single function `chat(system: str, user: str, *, agent_name: str, temperature: float = 0.7, response_format: str = None) -> str`. Uses `httpx.Client` with 60s timeout. After every call, appends a JSON line to `state/prompts_log.jsonl` with: `{ts, agent_name, system, user, output, temperature, latency_ms, usage}`. If `response_format == "json"`, passes `{"response_format": {"type": "json_object"}}` in request.

- [ ] **1.5** `src/blackboard.py`: `Blackboard` class with methods:
  - `read_text(path) / write_text(path, content)` (atomic: write to `.tmp` then rename)
  - `read_json(path) / write_json(path, obj)`
  - `read_yaml(path) / write_yaml(path, obj)`
  - `append_jsonl(path, obj)`
  - `read_jsonl(path) -> list`
  - `list_files(dir_glob) -> list[str]`
  - All paths are relative to `state/` unless marked absolute.

- [ ] **1.6** `tests/test_blackboard.py`: 3 tests — atomic write (verify no partial file on crash simulation), jsonl append preserves order, yaml round-trip.

- [ ] **1.7** Commit: `feat: scaffolding + blackboard + llm client`

---

## Task 2: Rules Files (Golden Principles, Lesson 4+5)

**Goal:** Five focused `rules/*.md` files. Content distilled from `docs/ai 小说流水线教程贴.txt`. AGENTS.md in Task 3 references these.

**Files to create under `rules/`:**

- [ ] **2.1** `rules/24-iron-laws.md` — 24 iron laws of the novel (extracted from tutorial §第 1-15 major rules and §二 "小说设定 7-14"). Use numbered list format.

- [ ] **2.2** `rules/18-landmines.md` — 18 common writing pitfalls with ❌/✅ examples (extracted from tutorial §16 "写作过程中容易出现的雷电" points 1-18). Each landmine has: trigger, why it's bad, fix.

- [ ] **2.3** `rules/writing-style.md` — condensed to ≤300 lines:
  - 六步人物心理分析 (6-step character construction)
  - 代入感六大支柱 (6 pillars of immersion)
  - Show-don't-tell examples (positive + negative)
  - 句式 / 词汇 / 修辞 / 分段 rules

- [ ] **2.4** `rules/era-1983-hk.md` — 1983 Hong Kong fact sheet:
  - 1983 key events (黑色星期六 港元危机, 七三股灾余波, 中英谈判)
  - 1983 Hong Kong geography (中环/湾仔/九龙城寨/旺角/尖沙咀)
  - Typical prices (茶餐厅一碗面约 HK$5, 月租 $500-1500)
  - Typical slang / 俚语
  - Law enforcement (PTU, ICAC, 四大探长余波)
  - Triad landscape (14K, 和胜和, 新义安)
  - Celebrities alive in 1983 (霍英东, 李嘉诚, 邵逸夫)
  - Movies in theaters: 《最佳拍档》, 《鬼马智多星》
  - Currency rates, transit, phone culture

- [ ] **2.5** `rules/characters-canon.md` — protagonist bio + 5 supporting characters. Contents:
  - 主角：林家耀（男，22 岁，福建移民，父亲曾是国民党特务，家道中落。性格：极致利己 + 有底线，冷，算计。金手指：系统「港务档案」——可查询 1983-2000 年任何公开事件和股价，但需要支付"情报值"，情报值通过完成"拨乱反正"任务获取。限制：不能直接预知人物私密信息或武力输出。）
  - 配角 5 位，每个 3-4 行的 bio，都有自己的动机

- [ ] **2.6** Commit: `feat: rules files — golden principles`

---

## Task 3: AGENTS.md (80-line ToC)

**Files:** `AGENTS.md`

- [ ] **3.1** Write `AGENTS.md` with these sections (each section ≤ 6 lines):
  - Project purpose (2 lines)
  - How to run (3 lines: `pip install -r requirements.txt` / `python -m src.bootstrap` / `python -m src.pipeline --chapter 1`)
  - Architecture 1-liner + link to `docs/superpowers/specs/2026-05-09-blackboard-novel-pipeline-design.md`
  - State directory map (each state/ file with 1-line description)
  - Agent roster (one line per agent: name, what it reads, what it writes, model temperature)
  - **Rule index** (5 entries pointing to `rules/*.md`)
  - Progressive disclosure rule (agents load only needed rules)
  - Troubleshooting: "If Agent loops / fails, read `state/debt.jsonl` and `state/prompts_log.jsonl`, don't patch — restart"

- [ ] **3.2** Verify total ≤ 100 lines with `wc -l AGENTS.md`.

- [ ] **3.3** Commit: `feat: AGENTS.md — 80-line ToC (Lesson 5)`

---

## Task 4: Bootstrap — Seed the Blackboard

**Goal:** `python -m src.bootstrap` populates `state/` with outline, characters, timeline, empty progress.

**Files:** `src/bootstrap.py`

- [ ] **4.1** Write `src/bootstrap.py` that creates/overwrites:
  - `state/outline.json`: novel meta + 10-chapter beat-sheet array. Each entry: `{ch, title, beats: [str], key_characters: [str], key_location: str, key_year_month: str, tension: str, hook_for_next: str}`. Content: 林家耀 in 1983 Hong Kong, chapters 1-10 cover his arrival + first hustle + first enemy + first ally + first win.
  - `state/timeline.yaml`: chronological events 1983-1984 with pointers to chapters
  - `state/characters.yaml`: load from `rules/characters-canon.md` (parse or duplicate — duplicate is fine for 24h MVP)
  - `state/progress.json`: `{current_chapter: 0, completed: [], in_flight: null}`
  - Ensure `state/chapters/`, `state/summaries/`, `state/fixes/` directories exist
  - Creates empty `state/issues.jsonl` and `state/debt.jsonl`

- [ ] **4.2** Run bootstrap. Verify all files exist with sanity checks (outline has 10 entries, characters.yaml parses).

- [ ] **4.3** Commit: `feat: bootstrap — seed blackboard with outline + canon`

---

## Task 5: Planner + Generator Agents

**Files:** `src/agents/_base.py`, `src/agents/planner.py`, `src/agents/generator.py`

- [ ] **5.1** `src/agents/_base.py`: `BaseAgent` with attributes `name`, `temperature`, `response_format`. Method `_build_messages(context: dict) -> (system, user)` is abstract. Method `run(bb: Blackboard, **kwargs)` orchestrates: build messages → call `llm.chat(...)` → post-process → write result to blackboard.

- [ ] **5.2** `src/agents/planner.py`: reads `outline.json`, `progress.json`, last 2 `summaries/chNNN.md`. Emits a beat-sheet JSON to `chapters/chNNN.plan.json` with: `{ch, title, opening_hook, beats: [{scene, purpose, cast, conflict, ~words}], closing_hook, landmines_to_avoid: [str]}`. Uses `response_format="json"`. Temperature 0.4. System prompt enforces: "你是有 20 年经验的责编，只输出严格 JSON，每章必须包含 3-5 个 beats，每个 beat 必须给出目的（推进主线/塑造人物/埋伏笔）"。

- [ ] **5.3** `src/agents/generator.py`: reads `chNNN.plan.json`, `characters.yaml`, `rules/writing-style.md`, `rules/18-landmines.md`, latest 1 summary. Writes `chapters/chNNN.md` (plain Chinese text, target 3000 chars). Temperature 0.85. System prompt loads writing-style + characters canon, emphasizes Show-don't-tell with explicit ❌/✅ examples, says "严禁 AI 味，严禁流水账，严禁形容词堆砌，每段 1 个核心信息".

- [ ] **5.4** Smoke test: hand-craft a minimal outline, run `Planner().run(bb, chapter=1)` → inspect `chNNN.plan.json`. Then `Generator().run(bb, chapter=1)` → inspect `chNNN.md`.

- [ ] **5.5** Commit: `feat: planner + generator agents`

---

## Task 6: Evaluator + Fixer (with Adversarial Persona)

**Files:** `src/agents/evaluator.py`, `src/agents/fixer.py`

- [ ] **6.1** `src/agents/evaluator.py`:
  - System prompt opens with adversarial persona: "你是以刁钻著称的资深网文主编，默认拒稿。下面这份 3000 字的章节稿件，你必须找出至少 3 处硬伤——如果你找不出 3 处就是失职。只看稿件事实，不要相信作者本意。"
  - User prompt includes: chapter text, `rules/18-landmines.md`, relevant character excerpt, relevant timeline excerpt.
  - `response_format="json"`. Schema:
    ```
    {
      "overall_pass": bool,
      "landmines": {"<mine_id>": {"hit": bool, "evidence": str|null, "severity": "low"|"medium"|"high"}, ...},
      "top_3_fixes": [{"where": str, "what": str}]
    }
    ```
  - Writes verdict to `chapters/chNNN.verdict.json`
  - Appends each hit issue to `state/issues.jsonl` with `{chapter, landmine_id, evidence, severity, ts}`.
  - Temperature 0.0.

- [ ] **6.2** `src/agents/fixer.py`: reads `chapters/chNNN.md`, `chapters/chNNN.verdict.json` (top_3_fixes + hit landmines). System prompt: "你是改稿高手，只修，不重写。只解决传入的具体问题，其他地方一字不动，输出完整的修改后章节。" Writes back to `chapters/chNNN.md`. Temperature 0.5.

- [ ] **6.3** Commit: `feat: evaluator (adversarial + JSON rubric) + fixer`

---

## Task 7: Summarizer + Auditor Fan-Out

**Files:** `src/agents/summarizer.py`, `src/auditors/ai_slop_guard.py`, `src/auditors/character_guard.py`

- [ ] **7.1** `src/agents/summarizer.py`: reads **only** `chapters/chNNN.md` (explicitly NOT plan.json or issues — this prevents Generator framing leakage per Oracle's §3). Writes `summaries/chNNN.md` (≤ 300 Chinese chars, factual, who-did-what-where-when-why, no opinion). Temp 0.2.

- [ ] **7.2** `src/auditors/ai_slop_guard.py`: reads `chapters/chNNN.md` + a tight extract of `rules/18-landmines.md` (only slop-related: AI flavor, 了字堆砌, repetitive sentence structures, adjective stacking, 流水账). Output JSON: `{slop_score: 0-10, hits: [{type, example_snippet, suggested_rewrite}]}`. Writes to `state/fixes/chNNN.slop-patch.md` in a human-readable format.

- [ ] **7.3** `src/auditors/character_guard.py`: reads `chapters/chNNN.md` + `characters.yaml` + prior `summaries/*.md`. Output JSON: `{ooc_score: 0-10, hits: [{character, prior_behavior, current_deviation, severity}]}`. Writes `state/fixes/chNNN.char-patch.md`.

- [ ] **7.4** Commit: `feat: summarizer + 2 auditors (fan-out)`

---

## Task 8: Pipeline Main Loop

**Files:** `src/pipeline.py`

- [ ] **8.1** `src/pipeline.py` with CLI via `argparse`:
  ```
  python -m src.pipeline --chapter N       # run a single chapter end-to-end
  python -m src.pipeline --range 1-3       # run multiple
  python -m src.pipeline --audit-only N    # just auditors on existing chapter
  ```

- [ ] **8.2** `run_chapter(N)` implements:
  ```
  1. Planner.run(ch=N)
  2. Generator.run(ch=N)
  3. for attempt in range(1, 3):
        verdict = Evaluator.run(ch=N)
        if verdict["overall_pass"]: break
        Fixer.run(ch=N, issues=verdict)
     else:
        progress["chapters"][N] = "shipped_with_debt"
        append unresolved issues to state/debt.jsonl
  4. Summarizer.run(ch=N)
  5. In parallel (threading): AISlopGuard.run(N), CharacterGuard.run(N)
  6. Update progress.json
  ```

- [ ] **8.3** Use `concurrent.futures.ThreadPoolExecutor(max_workers=2)` for the Auditor fan-out.

- [ ] **8.4** Commit: `feat: pipeline main loop + debt tracking`

---

## Task 9: Flask Web UI

**Files:** `web/app.py`, `web/templates/index.html`, `web/static/main.css`, `web/static/main.js`

- [ ] **9.1** `web/app.py` routes:
  - `GET /` → `index.html`
  - `GET /api/state` → JSON: `{progress, chapters: [{n, title, status}], debt_count}`
  - `GET /api/file?path=...` → return file content (text) if under `state/`, else 403
  - `GET /api/prompts` → last 200 entries of `prompts_log.jsonl`
  - `GET /api/debt` → content of `debt.jsonl`
  - `POST /api/run?chapter=N` → spawns `run_chapter(N)` in background thread (threading, not subprocess — keep simple), returns 202. Writes runtime status to `state/pipeline_status.json`.
  - `GET /api/status` → `pipeline_status.json` contents
  - `POST /api/reset` → demonstration: kill any in-flight thread (set flag), re-read `progress.json`, return. (For true "Context Reset" demo, pressing reset in UI simply restarts polling from state — the essence is that all state lives in files.)

- [ ] **9.2** `index.html`: 3-column CSS grid layout.
  - **Left column**: file tree of `state/` (generated from `/api/state` + `/api/file` — use a simple expandable UL).
  - **Center column (tab 1)**: current chapter markdown rendered (use marked.js via CDN); (tab 2) `debt.jsonl` as a table.
  - **Right column (tab 1)**: Prompt Inspector — list of last prompts with collapsed entries showing: timestamp, agent, latency, token count. Click to expand full `system`, `user`, `output`. (tab 2) Agent log scrolling (same data, denser view).
  - **Top bar**: status pills (current chapter, running agent) + 3 buttons: 生成下一章 / 全量审计 / 重置并续写.

- [ ] **9.3** `main.css`: minimal. No framework — hand-rolled flex/grid, ~150 lines. Dark-ish theme for seriousness.

- [ ] **9.4** `main.js`: vanilla JS. Polls `/api/state` and `/api/status` every 2 seconds. Updates columns. Handles button clicks.

- [ ] **9.5** Run `flask --app web.app run --debug` locally. Verify all three panels populate from a pre-run state.

- [ ] **9.6** Commit: `feat: Flask web demo (3 panels + prompt inspector)`

---

## Task 10: Generate Chapters 1-3 for Demo

- [ ] **10.1** `python -m src.bootstrap`
- [ ] **10.2** `python -m src.pipeline --range 1-3`
- [ ] **10.3** Read each chapter. If any chapter is obviously trash (AI slop visible, logic broken), rerun `--chapter N` once. If still bad, accept and let it demonstrate the `debt.jsonl` feature.
- [ ] **10.4** Commit: `feat: produce chapters 1-3 for demo (with state/)` — note: state/ is .gitignored; instead commit a `state_snapshot/` copy as demo artifact.

---

## Task 11: README + Deploy

- [ ] **11.1** Write `README.md` with:
  - Badges (if any), hero screenshot
  - 1-minute pitch (same as design doc §8)
  - Architecture diagram (ASCII from design doc §1)
  - How to run locally (3 commands)
  - Deployment notes
  - Credits + license (MIT)

- [ ] **11.2** Deploy decision tree:
  - **Option A (easiest for Flask):** Railway.app — push GitHub, Railway auto-deploys. Free tier enough for demo.
  - **Option B:** Cloudflare Tunnel from local machine (cloudflared). Works during demo window, dies when laptop sleeps.
  - **Option C:** Render.com
  - **Pick A.** If Railway fails, fallback to Cloudflare Tunnel.

- [ ] **11.3** Verify public URL loads and agent log populates.

- [ ] **11.4** Commit: `docs: README + deploy config`

---

## Task 12: GitHub Repo

- [ ] **12.1** Create public GitHub repo `blackboard-novel-pipeline` under user's account. (gh CLI if available, else user creates it and provides URL.)
- [ ] **12.2** `git remote add origin ...`, `git branch -M main`, `git push -u origin main`.
- [ ] **12.3** Verify repo is public and README renders.

---

## Task 13: Submit Hackathon Entry

- [ ] **13.1** Create demo ZIP: `git archive --format=zip --prefix=blackboard-novel-pipeline/ HEAD -o /tmp/submission.zip`. Verify `du -h /tmp/submission.zip` < 10MB.
- [ ] **13.2** Log into EasyClaw with stored credentials (`~/Desktop/opencode/.easyclaw/account.json`).
- [ ] **13.3** Fill `/zh/hackathon/submit` with user-provided personal info + project fields (ask user for age/phone/wechat/city/school, they give name = 魏何文 based on email).
- [ ] **13.4** Upload ZIP, demo URL, GitHub URL (as link 1), design doc URL (as link 2).
- [ ] **13.5** Submit. Verify `GET /api/hackathon/my-entry` now returns `entry: {...}`.

---

## Self-Review

- [x] Spec coverage: every design doc section has a task.
- [x] No "TBD" / "implement later" placeholders.
- [x] File paths and imports are consistent (`src.pipeline`, `src.agents.planner`, etc.).
- [x] Function signatures stable across tasks.
- [ ] One caveat: Task 10 commits a snapshot of state/. Since `.gitignore` excludes `state/`, we will create `demo_snapshot/` with the 3 chapter outputs + verdict/summary/patches/prompt_log excerpt, to evidence the system worked.

---

**Plan complete.**
