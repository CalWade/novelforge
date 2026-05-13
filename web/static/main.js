/* =========================================================
   Novelforge — demo UI
   Vanilla JS. No bundler, no framework. Fetch + DOM.
   ========================================================= */

'use strict';

const AGENT_COLORS = {
  planner:              '#5aa7ff',
  generator:            '#62d97a',
  evaluator:            '#f85149',
  fixer:                '#ffb454',
  summarizer:           '#9aa5b5',
  arc_summarizer:       '#7a85a0',
  book_summarizer:      '#6d7788',
  status_card_updater:  '#c4a0ff',
  hook_keeper:          '#f0a0d0',
  resource_ledger:      '#d0b070',
  ai_slop_guard:        '#b78dff',
  character_guard:      '#3dd5c8',
};
const AGENT_LABEL = {
  planner:              'PLANNER',
  generator:            'GENERATOR',
  evaluator:            'EVALUATOR',
  fixer:                'FIXER',
  summarizer:           'SUMMARIZER',
  arc_summarizer:       'ARC SUMMARIZER',
  book_summarizer:      'BOOK SUMMARIZER',
  status_card_updater:  'STATUS CARD',
  hook_keeper:          'HOOK KEEPER',
  resource_ledger:      'RESOURCE LEDGER',
  ai_slop_guard:        'AI-SLOP GUARD',
  character_guard:      'CHARACTER GUARD',
};

// ---------- LESSONS (pitch crosswalk: principle → code) ----------
const REPO_URL = 'https://github.com/CalWade/novelforge';
const LESSONS = [
  {
    n: 1,
    title: '反复失败时修工具而非提示',
    attribution: 'Anthropic',
    attribution_color: 'anthropic',
    principle: '状态沉到文件里 · 重启胜过修补',
    impl: [
      '所有 Agent 无状态, 每次调用 fresh context',
      '失败写入 state/issues.jsonl + state/debt.jsonl, Fixer 下一轮从文件读',
      '重跑整个章节只需一条命令: python -m src.pipeline --chapter N',
    ],
    code_pointers: [
      { label: 'src/blackboard.py', desc: '文件系统 = 共享记忆的唯一 source of truth', github_path: 'src/blackboard.py', logical_path: null },
      { label: 'src/pipeline.py',   desc: '每个 stage 都是独立 agent.run()',          github_path: 'src/pipeline.py',   logical_path: null },
      { label: 'state/issues.jsonl', desc: 'append-only 失败日志',                    github_path: null,                logical_path: 'state/issues.jsonl' },
    ],
  },
  {
    n: 2,
    title: '自评偏乐观, 必须分工',
    attribution: 'Anthropic',
    attribution_color: 'anthropic',
    principle: '干活的和验收的必须是不同的人',
    impl: [
      'Planner / Generator / Evaluator / Fixer / Summarizer 五个创作 Agent',
      'StatusCardUpdater / HookKeeper / ResourceLedger 三个 bookkeeping Agent (覆盖式)',
      'Evaluator 用对抗人设 (默认拒稿) + 结构化 JSON rubric (18 landmines × severity)',
      'Evaluator 看不到 Generator 的推理过程, 只看最终文件',
      '服务端重算 overall_pass, 不信模型自评 + skeleton detector 防模型复制示例',
    ],
    code_pointers: [
      { label: 'src/agents/evaluator.py', desc: '对抗人设 + JSON rubric + skeleton detector', github_path: 'src/agents/evaluator.py', logical_path: null },
      { label: 'rules/18-landmines.md',   desc: '18 个雷点的结构化判据 (通用)',              github_path: 'rules/18-landmines.md',   logical_path: 'rules/18-landmines.md' },
      { label: 'state/iron-laws-extra.md', desc: '题材特有铁律 (setting 注入)',              github_path: null,                      logical_path: 'state/iron-laws-extra.md' },
      { label: 'rules/00-information-priority.md', desc: '冲突仲裁协议 (9 级优先级 + R1..R5)', github_path: 'rules/00-information-priority.md', logical_path: 'rules/00-information-priority.md' },
    ],
  },
  {
    n: 3,
    title: 'Context Anxiety 需要 Reset',
    attribution: 'Cognition',
    attribution_color: 'cognition',
    principle: '直接丢弃旧窗口, 新窗口从文件读进度',
    impl: [
      '每次 LLM 调用都是 fresh session (见 Inspector: 每行 ≤6 文件, 无累积)',
      'Summarizer 严格只读最终 chapter, 不读 plan/verdict/issues (防 framing 后门泄漏)',
      'Planner 读 ≤2 份前章摘要 + 当前状态卡 + 伏笔池, 不读全文',
      'StatusCardUpdater 每章末覆盖 state/current_status_card.md — 进程重启读它即可恢复',
      'HookKeeper 每章末覆盖 state/pending_hooks.md — 避免 10+ 章漏伏笔',
      'ResourceLedger (可选) 每章末覆盖 state/resource_ledger.md — 仅当 setting 声明 schema',
    ],
    code_pointers: [
      { label: 'src/llm.py',                      desc: '每次调用新建 messages 数组, 无跨调用 memory', github_path: 'src/llm.py',                      logical_path: null },
      { label: 'src/agents/summarizer.py',        desc: 'Summarizer 只读 chapter file (严防泄漏)',    github_path: 'src/agents/summarizer.py',        logical_path: null },
      { label: 'src/agents/status_card_updater.py', desc: 'StatusCardUpdater — 唯一的当前时间点快照', github_path: 'src/agents/status_card_updater.py', logical_path: null },
      { label: 'src/agents/hook_keeper.py',       desc: 'HookKeeper — 待回收伏笔池',                  github_path: 'src/agents/hook_keeper.py',       logical_path: null },
      { label: 'state/current_status_card.md',    desc: 'Context Reset 的单一入口文件',               github_path: null,                              logical_path: 'state/current_status_card.md' },
      { label: 'state/prompts_log.jsonl',         desc: '每次调用的 inputs_read 清单 (见 Inspector)', github_path: null,                              logical_path: 'state/prompts_log.jsonl' },
    ],
  },
  {
    n: 4,
    title: 'AI Slop 每天还一点',
    attribution: 'OpenAI Codex',
    attribution_color: 'openai',
    principle: '黄金原则沉仓库 · 后台 Agent 定期扫 · 带债上线',
    impl: [
      'rules/*.md 是黄金原则 (24 iron laws + 18 landmines, 通用)',
      'genres/<id>/iron-laws-extra.md: 题材特有铁律 (genre 层)',
      '2 个 Auditor 并行独立会话扫每一章 → state/fixes/chNNN.*-patch.md (类 PR)',
      'Evaluator 2 次 retry 仍不过 → shipped_with_debt, 写 debt.jsonl 不死循环',
    ],
    code_pointers: [
      { label: 'rules/24-iron-laws.md', desc: '通用 golden principles (题材无关)',       github_path: 'rules/24-iron-laws.md', logical_path: 'rules/24-iron-laws.md' },
      { label: 'src/auditors/',         desc: 'AISlopGuard + CharacterGuard (Fan-Out 并行)', github_path: 'src/auditors',      logical_path: null },
      { label: 'src/pipeline.py',       desc: '_append_debt: retries 用尽后带债上线',   github_path: 'src/pipeline.py',       logical_path: null },
      { label: 'state/debt.jsonl',      desc: '技术债账本 (每日可还)',                  github_path: null,                    logical_path: 'state/debt.jsonl' },
    ],
  },
  {
    n: 5,
    title: '规则文件宁缺毋滥',
    attribution: 'OpenAI',
    attribution_color: 'openai',
    principle: 'AGENTS.md 目录页 · 详细拆到子文档 · Progressive Disclosure',
    impl: [
      'AGENTS.md 仅 ~70 行, 纯索引 + 规则映射表',
      'rules/ 下 4 份通用规则 + genres/<id>/ 下 3 份题材规则',
      '每个 Agent 只加载它需要的那 1-2 份 (见 AGENTS.md 规则索引)',
    ],
    code_pointers: [
      { label: 'AGENTS.md',  desc: '70 行目录页, 规则按 agent 分派', github_path: 'AGENTS.md', logical_path: 'AGENTS.md' },
      { label: 'rules/',     desc: '3 份通用规则 (题材无关)',        github_path: 'rules',     logical_path: null },
      { label: 'genres/ + projects/', desc: '题材层 + 作品层（2026-05 重构）', github_path: 'genres', logical_path: null },
    ],
  },
];

const state = {
  snapshot: null,          // /api/state last response
  status: { running: false },
  chapters: [],            // outline chapter meta
  prompts: [],             // /api/prompts latest snapshot
  openFile: null,          // currently-viewed file path
  openPromptIds: new Set(),// expanded prompt cards (persist across polls)
  activeCenterTab: 'chapter',
  activeRightTab: 'inspector',
  lessonsRendered: false,
  statusPollTimer: null,
  statePollTimer: null,
  promptsPollTimer: null,
};

// ---------- utilities ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function')
      node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function fmtBytes(b) {
  if (b == null) return '';
  if (b < 1024) return b + ' B';
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
  return (b / (1024 * 1024)).toFixed(2) + ' MB';
}

function fmtRelTime(ts) {
  if (!ts) return '';
  const now = Date.now() / 1000;
  const d = now - ts;
  if (d < 5) return '刚刚';
  if (d < 60) return Math.round(d) + ' 秒前';
  if (d < 3600) return Math.round(d / 60) + ' 分钟前';
  if (d < 86400) return Math.round(d / 3600) + ' 小时前';
  return new Date(ts * 1000).toLocaleString();
}

function fmtClock(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function parseChapterFromInputs(inputs) {
  if (!Array.isArray(inputs)) return null;
  for (const p of inputs) {
    const m = /ch(\d{3})\.(md|plan\.json|verdict\.json)/.exec(p) || /ch(\d{3})\.md/.exec(p);
    if (m) return parseInt(m[1], 10);
  }
  return null;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j.reason || j.detail || j.error || detail;
    } catch (_) { /* noop */ }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json();
}

/**
 * Unified mutating-API helper. Backend ships {ok:false, reason} on failure
 * AND may return 4xx/5xx; we collapse both into a thrown Error(reason).
 * On success returns the parsed JSON body.
 */
async function apiCall(path, opts = {}) {
  const headers = opts.headers || {};
  if (opts.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const resp = await fetch(path, { ...opts, headers });
  let body = {};
  try { body = await resp.json(); } catch (_) { /* allow empty */ }
  if (!resp.ok || body.ok === false || body.started === false) {
    const reason = body.reason || body.detail || body.error || `HTTP ${resp.status}`;
    const err = new Error(reason);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

function toast(msg, isErr = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('is-error', isErr);
  t.classList.add('is-show');
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove('is-show'), 3200);
}

// ---------- top bar pills ----------
function renderPills() {
  const s = state.snapshot;
  const st = state.status;
  if (!s) return;
  const prog = s.progress || {};
  const curr = prog.current_chapter ?? 0;

  $('#pill-chapter').textContent = curr > 0 ? `${curr}/${s.chapters.length}` : `0/${s.chapters.length}`;

  const runPill = $('#pill-running').parentElement;
  let runLabel = '空闲';
  if (st.running) {
    runLabel = (st.kind === 'audit' ? '审计 · 第' : '全流程 · 第') + (st.chapter ?? '?') + '章';
  } else if (prog.in_flight && prog.in_flight.stage) {
    runLabel = prog.in_flight.stage + ' · 第' + prog.in_flight.chapter + '章';
  }
  $('#pill-running').textContent = runLabel;
  runPill.classList.toggle('pill-running', st.running || !!prog.in_flight);

  const debtPill = $('#pill-debt').parentElement;
  $('#pill-debt').textContent = s.debt_count;
  debtPill.classList.toggle('pill-debt-hot', s.debt_count > 0);

  $('#pill-calls').textContent = s.prompt_count;

  // debt tab badge
  const badge = $('#tab-debt-count');
  if (s.debt_count > 0) {
    badge.textContent = s.debt_count;
  } else {
    badge.textContent = '';
  }

  // Run panel + header sync (idempotent; safe to call on every poll)
  syncRunButtons();
  syncProjectButton();
  syncReadonlyBanner();
  autofillRunChapter();
}

// Inject the active setting's title + subtitle into the top-bar brand line,
// so the UI reflects whichever setting was bootstrapped (not a hardcoded genre).
function renderBrandSub() {
  const elBrand = document.getElementById('brand-sub');
  if (!elBrand) return;
  const s = state.snapshot;
  const novel = (s && s.novel) || {};
  const parts = [];
  if (novel.title) parts.push(novel.title);
  if (novel.subtitle) parts.push(novel.subtitle);
  parts.push('小说锻造厂');
  elBrand.textContent = parts.join(' · ');

  if (novel.title) {
    document.title = `Novelforge · ${novel.title}`;
  }
}

// ---------- file tree ----------
function renderTree() {
  const s = state.snapshot;
  if (!s) return;
  const tree = $('#tree');
  tree.innerHTML = '';

  // Section: top-level state files
  tree.appendChild(sectionHeader('state/ · root'));
  [
    ['state/setting.yaml',           'setting.yaml',           '◆'],
    ['state/outline.json',           'outline.json',           '•'],
    ['state/progress.json',          'progress.json',          '•'],
    ['state/timeline.yaml',          'timeline.yaml',          '•'],
    ['state/characters.yaml',        'characters.yaml',        '•'],
    ['state/era.md',                 'era.md',                 '◆'],
    ['state/writing-style-extra.md', 'writing-style-extra.md', '◆'],
    ['state/iron-laws-extra.md',     'iron-laws-extra.md',     '◆'],
    ['state/issues.jsonl',           'issues.jsonl',           '•'],
    ['state/debt.jsonl',             'debt.jsonl',             '•'],
    ['state/prompts_log.jsonl',      'prompts_log.jsonl',      '•'],
  ].forEach(([p, name, icon]) => tree.appendChild(treeItem(p, name, icon || '•')));

  // Section: bookkeeping ledgers (Lesson-3 Context Reset layer)
  // - current_status_card.md (C-23) — overwrite, always present after ch1
  // - pending_hooks.md       (C-25) — overwrite, always present after ch1
  // - resource_schema.yaml   (C-24) — optional; absent for non-numeric settings
  // - resource_ledger.md     (C-24) — only present when schema exists
  tree.appendChild(sectionHeader('bookkeeping/ (Lesson-3 ledgers)'));
  const bk = (s.bookkeeping || {});
  [
    ['state/current_status_card.md', 'current_status_card.md', '❂', !bk.has_status_card],
    ['state/pending_hooks.md',       'pending_hooks.md',       '⚑', !bk.has_pending_hooks],
    ['state/resource_schema.yaml',   'resource_schema.yaml',   '◆', !bk.has_resource_schema],
    ['state/resource_ledger.md',     'resource_ledger.md',     '⚖', !bk.has_resource_ledger],
  ].forEach(([p, name, icon, missing]) => tree.appendChild(treeItem(p, name, icon, missing)));

  // Section: chapters folder, one group per chapter
  tree.appendChild(sectionHeader('chapters/'));
  const chWrap = el('div', { class: 'tree-group-items' });
  s.chapters.forEach((ch) => {
    const produced = [
      ch.has_plan, ch.has_md, ch.has_verdict,
      ch.has_summary, ch.has_slop_patch, ch.has_char_patch,
    ].filter(Boolean).length;
    const total = 6;
    const label = el('div', { class: 'tree-group-label', onclick: (e) => toggleGroup(e.currentTarget) },
      el('span', { class: 'tree-caret' }, '▶'),
      el('span', { class: 'tree-group-name' }, `ch${String(ch.ch).padStart(3, '0')}  ${ch.title.replace(/^第[一二三四五六七八九十]+章\s*·\s*/, '')}`),
      el('span', { class: 'tree-group-count' }, `${produced}/${total}`),
    );
    // auto-open the current / latest chapter
    const openDefault = ch.ch === (s.progress.current_chapter || 1) || ch.has_md;
    if (openDefault) label.classList.add('is-open');

    const items = el('div', { class: 'tree-items', style: openDefault ? '' : 'display:none' },
      treeItem(`state/chapters/ch${String(ch.ch).padStart(3, '0')}.plan.json`,    'plan.json',       '◇', !ch.has_plan),
      treeItem(`state/chapters/ch${String(ch.ch).padStart(3, '0')}.md`,           'chapter.md',      '✎', !ch.has_md),
      treeItem(`state/chapters/ch${String(ch.ch).padStart(3, '0')}.verdict.json`, 'verdict.json',    '⚖', !ch.has_verdict),
      treeItem(`state/summaries/ch${String(ch.ch).padStart(3, '0')}.md`,          'summary.md',      '≡', !ch.has_summary),
      treeItem(`state/fixes/ch${String(ch.ch).padStart(3, '0')}.slop-patch.md`,   'slop-patch.md',   '△', !ch.has_slop_patch),
      treeItem(`state/fixes/ch${String(ch.ch).padStart(3, '0')}.char-patch.md`,   'char-patch.md',   '☗', !ch.has_char_patch),
    );
    const group = el('div', { class: 'tree-group' }, label, items);
    chWrap.appendChild(group);
  });
  tree.appendChild(chWrap);

  // Section: rules (Progressive Disclosure)
  tree.appendChild(sectionHeader('rules/ (universal)'));
  [
    ['rules/00-information-priority.md', '00-information-priority.md'],
    ['rules/24-iron-laws.md',            '24-iron-laws.md'],
    ['rules/18-landmines.md',            '18-landmines.md'],
    ['rules/writing-style-core.md',      'writing-style-core.md'],
  ].forEach(([p, name]) => tree.appendChild(treeItem(p, name, '§')));

  // Section: project root
  tree.appendChild(sectionHeader('project/'));
  tree.appendChild(treeItem('AGENTS.md', 'AGENTS.md', '★'));
}

function sectionHeader(title) {
  return el('div', { class: 'tree-section-header' }, title);
}

function toggleGroup(labelEl) {
  labelEl.classList.toggle('is-open');
  const items = labelEl.nextElementSibling;
  if (items) items.style.display = labelEl.classList.contains('is-open') ? '' : 'none';
}

function treeItem(path, name, icon, missing = false) {
  const node = el('div', {
    class: 'tree-item' + (missing ? ' is-missing' : '') + (state.openFile === path ? ' is-active' : ''),
    dataset: { path },
    title: missing ? `${path} — 尚未生成` : path,
    onclick: missing ? null : () => openFile(path),
  },
    el('span', { class: 'tree-item-icon' }, icon),
    el('span', { class: 'tree-item-name' }, name),
  );
  return node;
}

// ---------- center viewer ----------
async function openFile(path) {
  state.openFile = path;
  // mark active
  $$('.tree-item').forEach((n) => n.classList.toggle('is-active', n.dataset.path === path));

  // decide which tab to focus
  if (path.startsWith('rules/')) {
    setCenterTab('rules');
  } else {
    setCenterTab('chapter');
  }

  const viewerRoot = path.startsWith('rules/') ? $('#rules-viewer') : $('#viewer');
  viewerRoot.innerHTML = '<div class="placeholder"><div class="placeholder-title">加载中…</div></div>';
  $('#viewer-meta').textContent = path;

  try {
    const res = await api('/api/file?path=' + encodeURIComponent(path));
    renderViewer(viewerRoot, res);
    $('#viewer-meta').textContent = `${path}  ·  ${fmtBytes(res.size)}`;
  } catch (e) {
    viewerRoot.innerHTML = '';
    viewerRoot.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-title' }, '无法加载'),
      el('div', { class: 'placeholder-sub' }, String(e.message))));
  }
}

function renderViewer(root, file) {
  const ext = (file.path.split('.').pop() || '').toLowerCase();
  const isMd = ext === 'md' || file.mimetype === 'text/markdown';
  const isJsonish = ext === 'json' || ext === 'jsonl';
  const isYaml = ext === 'yaml' || ext === 'yml';

  root.innerHTML = '';

  if (isMd && window.marked) {
    const html = window.marked.parse(file.content, { breaks: false, gfm: true });
    const article = el('div', { class: 'viewer' });
    article.innerHTML = html;
    root.appendChild(article);
  } else if (isJsonish) {
    const pre = el('pre', { class: 'viewer-source' });
    pre.innerHTML = highlightJson(file.content, ext === 'jsonl');
    root.appendChild(pre);
  } else if (isYaml) {
    const pre = el('pre', { class: 'viewer-source' });
    pre.textContent = file.content;
    root.appendChild(pre);
  } else {
    const pre = el('pre', { class: 'viewer-source' });
    pre.textContent = file.content;
    root.appendChild(pre);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function highlightJson(text, jsonl) {
  // small, line-safe highlighter; pretty-prints .json but leaves .jsonl as-is
  let source = text;
  if (!jsonl) {
    try { source = JSON.stringify(JSON.parse(text), null, 2); } catch (_) { /* leave raw */ }
  }
  const escaped = escapeHtml(source);
  return escaped
    .replace(/(&quot;[^&]*?&quot;)\s*:/g, '<span class="src-key">$1</span>:')
    .replace(/: (&quot;.*?&quot;)/g, ': <span class="src-string">$1</span>')
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="src-num">$1</span>')
    .replace(/\b(true|false)\b/g, '<span class="src-bool">$1</span>')
    .replace(/\bnull\b/g, '<span class="src-null">null</span>');
}

// ---------- center tabs ----------
function setCenterTab(name) {
  state.activeCenterTab = name;
  $$('.tab[data-tab]').forEach((b) => b.classList.toggle('tab-active', b.dataset.tab === name));
  $$('.tab-pane[data-pane]').forEach((p) => p.classList.toggle('tab-pane-active', p.dataset.pane === name));
  if (name === 'debt') renderDebt();
}

function setRightTab(name) {
  state.activeRightTab = name;
  $$('.tab[data-rtab]').forEach((b) => b.classList.toggle('tab-active', b.dataset.rtab === name));
  $$('.tab-pane[data-rpane]').forEach((p) => p.classList.toggle('tab-pane-active', p.dataset.rpane === name));
  if (name === 'lessons') {
    if (!state.lessonsRendered) {
      renderLessons();
      state.lessonsRendered = true;
    }
    return;
  }
  renderPrompts(); // re-render current view
}

// ---------- LESSONS (Flask build: logical_path → openFile, else GitHub) ----------
function renderLessons() {
  const root = $('#lessons-panel');
  if (!root) return;
  root.innerHTML = '';
  LESSONS.forEach((lesson) => root.appendChild(lessonCard(lesson)));
}

function lessonCard(lesson) {
  return el('div', { class: 'lesson-card', dataset: { n: lesson.n } },
    el('div', { class: 'lesson-card-head' },
      el('div', { class: 'lesson-n' }, `Lesson ${String(lesson.n).padStart(2, '0')}`),
      el('div', { class: `lesson-attr attr-${lesson.attribution_color}` }, lesson.attribution),
    ),
    el('h3', { class: 'lesson-title' }, lesson.title),
    el('div', { class: 'lesson-principle' }, lesson.principle),
    el('div', { class: 'lesson-section-label' }, '本项目落地'),
    el('ul', { class: 'lesson-impl' },
      ...lesson.impl.map((x) => el('li', null, x))),
    el('div', { class: 'lesson-section-label' }, '代码指针'),
    el('ul', { class: 'lesson-pointers' },
      ...lesson.code_pointers.map((p) => el('li', null, renderPointerFlask(p)))),
  );
}

function renderPointerFlask(p) {
  // Prefer opening the file in the center panel (logical_path), since users are here
  // because they want to *read* the repo. Fall back to GitHub for directories / code.
  if (p.logical_path) {
    return el('a', {
      class: 'ptr-link',
      href: '#',
      title: `打开 ${p.logical_path} (中栏)`,
      onclick: (e) => { e.preventDefault(); openFile(p.logical_path); },
    },
      el('code', null, p.label),
      el('span', { class: 'ptr-desc' }, p.desc),
      el('span', { class: 'ptr-arrow' }, '→'),
    );
  }
  const repoPath = p.github_path;
  const href = repoPath ? `${REPO_URL}/blob/main/${repoPath}` : '#';
  return el('a', {
    class: 'ptr-link',
    href,
    target: '_blank',
    rel: 'noopener',
    title: `GitHub · ${repoPath || p.label}`,
  },
    el('code', null, p.label),
    el('span', { class: 'ptr-desc' }, p.desc),
    el('span', { class: 'ptr-arrow' }, '↗'),
  );
}

// ---------- debt ----------
async function renderDebt() {
  const root = $('#debt-view');
  try {
    const debt = await api('/api/debt');
    root.innerHTML = '';
    if (!debt.length) {
      root.appendChild(el('div', { class: 'debt-empty' },
        el('div', { class: 'debt-empty-mark' }, '✓'),
        el('div', null, '暂无技术债'),
        el('div', { style: 'color: var(--text-soft); font-size: 12px; margin-top: 8px;' },
          '每章都在 2 次 Fixer 重试内通过评审。'),
      ));
      return;
    }
    const table = el('table', { class: 'debt-table' },
      el('thead', null, el('tr', null,
        el('th', null, '章节'),
        el('th', null, '重试次数'),
        el('th', null, '未决'),
        el('th', null, 'Top 未决雷点'),
        el('th', null, '时间'),
      )),
      el('tbody', null,
        ...debt.map((d) => el('tr', null,
          el('td', null, '第 ' + d.chapter + ' 章'),
          el('td', null, String(d.retries_used)),
          el('td', null, String((d.unresolved || []).length)),
          el('td', { class: 'debt-landmines' },
            ...(d.unresolved || []).slice(0, 5).map((u) =>
              el('span', { class: 'debt-landmine-pill', title: u.evidence || '' }, u.landmine_id || '?')),
          ),
          el('td', { style: 'color: var(--text-soft); font-family: var(--font-mono); font-size: 11px;' },
            fmtRelTime(d.ts)),
        )),
      ),
    );
    root.appendChild(table);
  } catch (e) {
    root.innerHTML = '';
    root.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-title' }, 'Debt 加载失败'),
      el('div', { class: 'placeholder-sub' }, e.message)));
  }
}

// ---------- prompt inspector (the money shot) ----------
async function refreshPrompts() {
  try {
    const arr = await api('/api/prompts?limit=80');
    state.prompts = arr;
    renderPrompts();
  } catch (_) { /* tolerate */ }
}

function renderPrompts() {
  if (state.activeRightTab === 'inspector') renderInspector();
  else renderLog();
}

function renderInspector() {
  const root = $('#inspector');
  if (!state.prompts.length) {
    root.innerHTML = '';
    root.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-title' }, '等待 LLM 调用…'),
      el('div', { class: 'placeholder-sub' }, '点击顶栏「生成下一章」开始。')));
    return;
  }
  root.innerHTML = '';
  state.prompts.forEach((p) => root.appendChild(inspectorCard(p)));
}

function inspectorCard(p) {
  const agent = p.agent_name || 'unknown';
  const open = state.openPromptIds.has(p.id);
  const chapter = parseChapterFromInputs(p.inputs_read);
  const tokens = (p.usage && (p.usage.completion_tokens ?? p.usage.total_tokens)) || null;
  const promptTokens = p.usage && p.usage.prompt_tokens;

  const head = el('div', {
    class: 'insp-head',
    onclick: () => {
      if (state.openPromptIds.has(p.id)) state.openPromptIds.delete(p.id);
      else state.openPromptIds.add(p.id);
      renderInspector();
    },
  },
    el('div', { class: 'insp-row-1' },
      el('span', { class: `insp-agent insp-agent-${agent}` }, AGENT_LABEL[agent] || agent.toUpperCase()),
      chapter ? el('span', { class: 'insp-chapter' }, '第 ' + chapter + ' 章') : null,
      p.error ? el('span', { class: 'insp-err' }, 'ERROR') : null,
    ),
    el('div', { class: 'insp-time' }, fmtRelTime(p.ts)),
    el('div', { class: 'insp-row-2' },
      p.latency_ms != null ? metric('latency', (p.latency_ms / 1000).toFixed(1) + 's') : null,
      tokens ? metric('tokens', tokens + (promptTokens ? `  (+${promptTokens} in)` : '')) : null,
      p.model ? metric('model', p.model) : null,
      p.temperature != null ? metric('temp', p.temperature) : null,
    ),
  );

  const body = el('div', { class: 'insp-body' },
    el('div', { class: 'insp-callout' },
      el('strong', null, '📋 全新上下文 · '),
      promptTokens ? `${promptTokens} 个 prompt tokens, ` : '',
      '无对话历史, 无残留记忆。本次调用从零开始。',
    ),
    inspSection('inputs_read',
      el('div', { class: 'insp-inputs' },
        ...(p.inputs_read || ['—']).map((inp) => inp === '—'
          ? el('span', { class: 'insp-input-chip' }, '—')
          : el('span', {
              class: 'insp-input-chip',
              onclick: () => openFile(inp.replace(/^\.\//, '').startsWith('state/') || inp.startsWith('rules/') || inp === 'AGENTS.md' ? inp : 'state/' + inp),
            }, inp))),
    ),
    inspSection('system prompt', el('pre', { class: 'insp-pre insp-pre-sys' }, p.system || '')),
    inspSection('user prompt',   el('pre', { class: 'insp-pre insp-pre-user' }, p.user || '')),
    inspSection(p.error ? '错误' : '输出',
      el('pre', { class: 'insp-pre insp-pre-output' }, p.error ? JSON.stringify(p.error, null, 2) : (p.output || ''))),
    inspMeta(p),
  );

  const card = el('div', { class: 'insp-card' + (open ? ' is-open' : '') },
    el('div', { class: `insp-dot ag-${agent}` }),
    head,
    body,
  );
  return card;
}

function metric(label, value) {
  return el('span', { class: 'insp-metric' },
    el('span', { class: 'insp-metric-label' }, label + ':'),
    el('span', { class: 'insp-metric-value' }, String(value)),
  );
}

function inspSection(label, body) {
  return el('div', { class: 'insp-section' },
    el('div', { class: 'insp-section-label' }, label),
    body,
  );
}

function inspMeta(p) {
  return el('div', { class: 'insp-section' },
    el('div', { class: 'insp-section-label' }, '原始元数据'),
    el('div', { class: 'insp-meta-grid' },
      el('span', null, 'id'),            el('span', null, p.id || '—'),
      el('span', null, 'ts'),            el('span', null, fmtClock(p.ts)),
      el('span', null, 'model'),         el('span', null, p.model || '—'),
      el('span', null, 'temperature'),   el('span', null, p.temperature ?? '—'),
      el('span', null, 'response_fmt'),  el('span', null, p.response_format || 'text'),
      el('span', null, 'latency_ms'),    el('span', null, p.latency_ms ?? '—'),
    ),
  );
}

function renderLog() {
  const root = $('#log-view');
  root.innerHTML = '';
  if (!state.prompts.length) {
    root.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-title' }, '尚无日志')));
    return;
  }
  state.prompts.forEach((p) => {
    const chapter = parseChapterFromInputs(p.inputs_read);
    const tokens = (p.usage && p.usage.completion_tokens) || '—';
    root.appendChild(el('div', {
      class: 'log-row',
      title: p.id,
      onclick: () => {
        setRightTab('inspector');
        state.openPromptIds.add(p.id);
        renderInspector();
        // scroll to card
        setTimeout(() => {
          const cards = $$('.insp-card');
          // newest first — find matching index
          const idx = state.prompts.findIndex((x) => x.id === p.id);
          if (cards[idx]) cards[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 50);
      },
    },
      el('span', { class: `log-bar ag-${p.agent_name}` }),
      el('span', { class: 'log-time' }, fmtClock(p.ts)),
      el('span', { class: `log-agent insp-agent-${p.agent_name}` }, (p.agent_name || '?').toUpperCase()),
      el('span', { class: 'log-ch' }, chapter ? '第' + chapter + '章' : '—'),
      el('span', { class: 'log-lat' }, p.latency_ms != null ? (p.latency_ms / 1000).toFixed(1) + 's' : '—'),
      el('span', { class: 'log-tok' }, String(tokens)),
      el('span', { class: p.error ? 'log-err' : '' }, p.error ? 'ERROR' : (p.inputs_read || []).join(', ')),
    ));
  });
}

// ---------- polling ----------
async function pollState() {
  try {
    state.snapshot = await api('/api/state');
    renderPills();
    renderTree();
    renderBrandSub();
  } catch (e) {
    // don't spam toasts on polling failures
    console.warn('state poll:', e.message);
  }
}

async function pollStatus() {
  try {
    const prev = state.status.running;
    state.status = await api('/api/status');
    renderPills();
    if (prev && !state.status.running) {
      if (state.status.ok === false) {
        toast('流水线失败: ' + (state.status.error || '未知'), true);
      } else {
        toast('流水线完成 · 第 ' + state.status.chapter + ' 章');
        pollState();
        refreshPrompts();
      }
    }
  } catch (_) { /* tolerate */ }

  // adaptive cadence: faster when running
  const interval = state.status.running ? 1500 : 4000;
  state.statusPollTimer = setTimeout(pollStatus, interval);
}

async function pollPrompts() {
  if (state.activeRightTab === 'inspector' || state.activeRightTab === 'log') {
    await refreshPrompts();
  }
  state.promptsPollTimer = setTimeout(pollPrompts, state.status.running ? 2500 : 5000);
}

// ---------- actions: run panel ----------
// The run panel covers all 9 pipeline entry points. Each mode maps to the
// POST /api/run body shape the backend expects (see _MODE_DISPATCH in app.py).
// Range mode has its own input format ("N-M"); packaging takes no chapter.
const MODES_NO_CHAPTER = new Set(['range', 'packaging']);

function syncRunFields() {
  const mode = $('#run-mode').value;
  $('#run-chapter-field').hidden = MODES_NO_CHAPTER.has(mode);
  $('#run-range-field').hidden = mode !== 'range';
}

function autofillRunChapter() {
  const s = state.snapshot;
  if (!s) return;
  const input = $('#run-chapter');
  if (!input || document.activeElement === input) return;
  // Default to next chapter (or 1 if starting from scratch)
  const next = (s.progress.current_chapter || 0) + 1;
  input.value = Math.max(1, Math.min(next, s.chapters.length || next));
  input.max = String(s.chapters.length || 999);
}

function syncRunButtons() {
  const running = !!(state.status && state.status.running);
  const readonly = !!(state.snapshot && state.snapshot.readonly_mode);
  const runBtn = $('#btn-run');
  const abortBtn = $('#btn-abort');
  if (runBtn) runBtn.disabled = running || readonly;
  if (abortBtn) abortBtn.disabled = !running || readonly;
}

async function doRun() {
  const mode = $('#run-mode').value;
  const body = { mode };
  if (mode === 'range') {
    const range = $('#run-range').value.trim();
    if (!/^\d+-\d+$/.test(range)) {
      toast('范围格式必须为 N-M（如 1-3）', true);
      return;
    }
    body.range = range;
  } else if (!MODES_NO_CHAPTER.has(mode)) {
    const ch = parseInt($('#run-chapter').value, 10);
    if (!ch || ch < 1) {
      toast('请填写有效章号', true);
      return;
    }
    body.chapter = ch;
  }
  try {
    await apiCall('/api/run', { method: 'POST', body: JSON.stringify(body) });
    toast('已启动 · ' + modeLabel(mode));
    pollStatus();
  } catch (e) {
    toast('无法启动: ' + e.message, true);
  }
}

async function doAbort() {
  try {
    const r = await apiCall('/api/abort', { method: 'POST' });
    toast(r.was_running ? '已发送中断信号 · 等下一阶段边界停下' : '流水线并未运行');
  } catch (e) {
    toast('中断失败: ' + e.message, true);
  }
}

function modeLabel(mode) {
  const sel = $('#run-mode');
  if (!sel) return mode;
  const opt = sel.querySelector(`option[value="${mode}"]`);
  return opt ? opt.textContent.trim() : mode;
}

// ---------- header sync helpers ----------
function syncProjectButton() {
  const s = state.snapshot;
  const nameEl = $('#btn-project-name');
  if (!nameEl) return;
  const novel = (s && s.novel) || {};
  const pid = (s && s.progress && s.progress.active_project) || null;
  if (novel.title) {
    nameEl.textContent = novel.title;
  } else if (pid) {
    nameEl.textContent = pid;
  } else {
    nameEl.textContent = '未激活';
  }
  nameEl.title = pid ? `当前作品: ${pid}` : '未激活作品';
}

function syncReadonlyBanner() {
  const s = state.snapshot;
  const banner = $('#readonly-banner');
  if (!banner) return;
  const ro = !!(s && s.readonly_mode);
  banner.hidden = !ro;
  // Hide mutating header controls in readonly mode
  const runPanel = $('#run-panel');
  const gear = $('#btn-settings');
  if (runPanel) runPanel.style.display = ro ? 'none' : '';
  // The project button still opens the picker (read-only view) but activation
  // will be refused by the backend. We keep it visible so users can see what
  // project the demo is frozen on.
  if (gear) gear.style.display = ro ? 'none' : '';
}

// =========================================================
//  PROJECT PICKER & NEW PROJECT WIZARD
// =========================================================

async function openProjectPicker() {
  const dlg = $('#dlg-project');
  const grid = $('#pp-grid');
  grid.innerHTML = '<div class="project-grid-loading">加载中…</div>';
  dlg.showModal();
  try {
    const { active, projects } = await apiCall('/api/projects');
    renderProjectGrid(grid, projects, active, {
      onActivate: async (pid) => {
        if (pid === active) return;
        const target = projects.find((p) => p.id === pid);
        const name = (target && target.display_name) || pid;
        if (!confirm(`切换到 "${name}" ？当前进度保留在 state/ 里，可随时切回。`)) return;
        try {
          await apiCall('/api/projects/activate', {
            method: 'POST',
            body: JSON.stringify({ id: pid }),
          });
          toast('已切换 · 正在刷新…');
          setTimeout(() => location.reload(), 400);
        } catch (e) {
          toast('切换失败: ' + e.message, true);
        }
      },
      onNew: openNewProjectWizard,
    });
  } catch (e) {
    grid.innerHTML = '';
    grid.appendChild(el('div', { class: 'form-error' }, '加载作品列表失败: ' + e.message));
  }

  // Wire the "edit sources" button to open the standalone source editor
  // scoped to the currently active project.
  const editBtn = $('#pp-edit-sources');
  if (editBtn) {
    editBtn.onclick = () => {
      dlg.close();
      openSourceEditor();
    };
  }
}

function renderProjectGrid(root, projects, activeId, { onActivate, onNew }) {
  root.innerHTML = '';
  const ro = !!(state.snapshot && state.snapshot.readonly_mode);
  projects.forEach((p) => {
    const isActive = p.id === activeId;
    const card = el('button', {
      class: 'project-card' + (isActive ? ' is-active' : ''),
      type: 'button',
      title: isActive ? '当前作品' : `切换到 ${p.display_name}`,
      onclick: () => { if (!isActive && onActivate && !ro) onActivate(p.id); },
    },
      el('div', { class: 'project-card-name' }, p.display_name || p.id),
      el('div', { class: 'project-card-meta' },
        p.genre ? el('span', { class: 'project-card-tag' }, p.genre) : null,
        isActive
          ? el('span', { class: 'project-card-tag is-active' }, '当前')
          : (p.has_state
              ? el('span', { class: 'project-card-tag is-stateful' }, '已初始化')
              : el('span', { class: 'project-card-tag is-uninit' }, '未初始化')),
      ),
      el('div', { class: 'project-card-id' }, p.id),
    );
    root.appendChild(card);
  });

  // Add a "+ 新建作品" tile (hidden in readonly mode)
  if (onNew && !ro) {
    const newCard = el('button', {
      class: 'project-card project-card-new',
      type: 'button',
      onclick: onNew,
    },
      el('div', null,
        el('span', { class: 'project-card-new-glyph' }, '+'),
        el('span', null, '新建作品'),
      ),
    );
    root.appendChild(newCard);
  }
}

// =========================================================
//  NEW PROJECT WIZARD (4 steps, Phase 4 Task 4.7)
//    1) basics (id / display_name / protagonist_name / chapter_count_target)
//    2) genre starter (preset / extract / blank)
//    3) outline starter (synopsis / blank)
//    4) characters starter (brief / blank)
//
//  Submits to POST /api/projects/new.
//  If from_extract path → backend responds 202 with project_id; we poll
//  /api/projects/<pid>/extract-genre/progress until done, then reload.
// =========================================================

async function openNewProjectWizard() {
  // Close the picker if open
  const picker = $('#dlg-project');
  if (picker && picker.open) picker.close();

  const dlg = $('#dlg-new-project');
  if (!dlg) return;

  // Reset form + step state
  const form = $('#project-wizard-form');
  if (form) form.reset();
  wizardGoToStep(1);
  $$('[data-wizard-error]').forEach((n) => { n.hidden = true; n.textContent = ''; });
  const statusEl = $('#np-create-status');
  if (statusEl) statusEl.hidden = true;

  // (Re-)wire step navigation, starter radios, and submit (idempotent).
  initProjectWizard();

  dlg.showModal();
}

function wizardGoToStep(n) {
  const dlg = $('#dlg-new-project');
  if (!dlg) return;
  dlg.querySelectorAll('[data-wizard-step]').forEach((s) => {
    s.hidden = Number(s.dataset.wizardStep) !== Number(n);
  });
}

function initProjectWizard() {
  const dlg = $('#dlg-new-project');
  if (!dlg) return;
  const form = $('#project-wizard-form');
  if (!form) return;

  // Step navigation buttons (prev / next)
  dlg.querySelectorAll('[data-wizard-next]').forEach((btn) => {
    btn.onclick = () => {
      const from = Number(btn.closest('[data-wizard-step]')?.dataset.wizardStep || '1');
      if (!wizardValidateStep(from)) return;
      wizardGoToStep(btn.dataset.wizardNext);
    };
  });
  dlg.querySelectorAll('[data-wizard-prev]').forEach((btn) => {
    btn.onclick = () => wizardGoToStep(btn.dataset.wizardPrev);
  });

  // Genre starter radios → show/hide panels
  dlg.querySelectorAll('input[name="genre_starter"]').forEach((r) => {
    r.onchange = wizardUpdateGenrePanels;
  });
  wizardUpdateGenrePanels();

  // Load preset dropdown
  const presetSel = $('#select-from-preset');
  if (presetSel) {
    presetSel.innerHTML = '<option value="" disabled selected>加载中…</option>';
    fetch('/api/presets')
      .then((r) => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then((data) => {
        const list = data.presets || [];
        if (!list.length) {
          presetSel.innerHTML = '<option value="" disabled selected>（尚无 preset）</option>';
          return;
        }
        presetSel.innerHTML = '';
        list.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = p.display_name || p.id;
          presetSel.appendChild(opt);
        });
      })
      .catch((e) => {
        presetSel.innerHTML = `<option value="" disabled selected>加载失败: ${e.message}</option>`;
      });
  }

  // Load novels pool for "extract" starter
  const pool = $('#novels-pool-checkboxes');
  if (pool) {
    pool.innerHTML = '<span class="form-hint">加载中…</span>';
    fetch('/api/novels')
      .then((r) => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then((data) => {
        renderNovelsCheckboxes(pool, data.novels || [], 'extract_source');
      })
      .catch((e) => {
        pool.innerHTML = `<span class="form-error">加载失败: ${e.message}</span>`;
      });
  }

  // Submit handler
  form.onsubmit = (e) => {
    e.preventDefault();
    wizardSubmit();
  };
}

function wizardUpdateGenrePanels() {
  const dlg = $('#dlg-new-project');
  if (!dlg) return;
  const val = dlg.querySelector('input[name="genre_starter"]:checked')?.value;
  dlg.querySelectorAll('[data-genre-panel]').forEach((p) => {
    p.hidden = p.dataset.genrePanel !== val;
  });
}

function wizardValidateStep(step) {
  const dlg = $('#dlg-new-project');
  if (!dlg) return true;
  const fd = new FormData($('#project-wizard-form'));
  const errEl = dlg.querySelector(`[data-wizard-error="${step}"]`);
  const showErr = (msg) => { if (errEl) { errEl.textContent = msg; errEl.hidden = false; } };
  if (errEl) { errEl.hidden = true; errEl.textContent = ''; }

  if (step === 1) {
    const id = (fd.get('id') || '').toString().trim();
    if (!/^[a-z0-9_][a-z0-9_-]{0,63}$/.test(id)) {
      showErr('ID 必须是小写字母/数字/_/-，长度 ≤ 64');
      return false;
    }
    if (!(fd.get('display_name') || '').toString().trim()) {
      showErr('显示名必填');
      return false;
    }
    if (!(fd.get('protagonist_name') || '').toString().trim()) {
      showErr('主角姓名必填');
      return false;
    }
    const n = Number(fd.get('chapter_count_target'));
    if (!Number.isInteger(n) || n < 1) {
      showErr('目标章数必须是 ≥1 的整数');
      return false;
    }
  }
  if (step === 2) {
    const starter = fd.get('genre_starter');
    if (starter === 'preset' && !fd.get('from_preset')) {
      showErr('请选一个 preset');
      return false;
    }
    if (starter === 'extract' && fd.getAll('extract_source').length === 0) {
      showErr('请至少勾选一份原著素材');
      return false;
    }
  }
  return true;
}

function renderNovelsCheckboxes(root, novels, fieldName) {
  root.innerHTML = '';
  if (!novels.length) {
    root.innerHTML = '<span class="form-hint">（素材库为空，去 /novels 上传）</span>';
    return;
  }
  novels.forEach((n) => {
    const name = n.name || n;
    const lbl = document.createElement('label');
    lbl.className = 'wizard-radio';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.name = fieldName;
    input.value = name;
    const txt = document.createElement('span');
    txt.textContent = ' ' + name;
    lbl.appendChild(input);
    lbl.appendChild(txt);
    root.appendChild(lbl);
  });
}

async function wizardSubmit() {
  const form = $('#project-wizard-form');
  if (!form) return;
  // Final validation on all steps
  for (const step of [1, 2]) {
    if (!wizardValidateStep(step)) {
      wizardGoToStep(step);
      return;
    }
  }

  const fd = new FormData(form);
  const starter = fd.get('genre_starter');
  const payload = {
    id: (fd.get('id') || '').toString().trim(),
    display_name: (fd.get('display_name') || '').toString().trim(),
    protagonist_name: (fd.get('protagonist_name') || '').toString().trim(),
    chapter_count_target: Number(fd.get('chapter_count_target')),
  };

  if (starter === 'preset') {
    payload.from_preset = fd.get('from_preset');
  } else if (starter === 'extract') {
    payload.from_extract = {
      sources: fd.getAll('extract_source'),
      with_trial: fd.get('extract_with_trial') === 'on',
    };
  } else {
    payload.blank_genre = true;
  }

  // Outline starter
  const synopsis = (fd.get('outline_synopsis') || '').toString().trim();
  if (fd.get('blank_outline') === 'on' || !synopsis) {
    payload.blank_outline = true;
  } else {
    payload.outline_synopsis = synopsis;
  }

  // Characters starter
  const brief = (fd.get('characters_brief') || '').toString().trim();
  if (fd.get('blank_characters') === 'on' || !brief) {
    payload.blank_characters = true;
  } else {
    payload.characters_brief = brief;
  }

  const err4 = document.querySelector('[data-wizard-error="4"]');
  if (err4) { err4.hidden = true; err4.textContent = ''; }
  const statusEl = $('#np-create-status');
  const textEl = statusEl ? statusEl.querySelector('.wizard-status-text') : null;
  const markEl = statusEl ? statusEl.querySelector('.wizard-status-mark') : null;
  const submitBtn = $('#btn-wizard-submit');
  if (statusEl) {
    statusEl.hidden = false;
    statusEl.classList.remove('is-done', 'is-error');
    if (markEl) markEl.textContent = '◐';
    if (textEl) textEl.textContent = starter === 'extract'
      ? '已提交 · 正在拆解题材（慢，后台运行）…'
      : '正在创建作品…';
  }
  if (submitBtn) submitBtn.disabled = true;

  try {
    const r = await fetch('/api/projects/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (r.status === 202) {
      // Async extract path — poll progress
      const data = await r.json();
      if (textEl) textEl.textContent = '后台拆解中…（可关闭对话框，状态栏会继续轮询）';
      await pollExtractProgress(data.project_id || payload.id);
      return;
    }
    const body = await r.json().catch(() => ({}));
    if (!r.ok || body.ok === false) {
      const reason = body.reason || body.detail || body.error || ('HTTP ' + r.status);
      throw new Error(reason);
    }
    if (statusEl) {
      statusEl.classList.add('is-done');
      if (markEl) markEl.textContent = '✓';
      if (textEl) textEl.textContent = '已创建 · 正在激活…';
    }
    // Activate the new project automatically
    try {
      await apiCall('/api/projects/activate', {
        method: 'POST',
        body: JSON.stringify({ id: payload.id }),
      });
    } catch (_) { /* activation best-effort */ }
    toast('已创建并激活 · ' + payload.id);
    setTimeout(() => location.reload(), 400);
  } catch (e) {
    if (statusEl) {
      statusEl.classList.add('is-error');
      if (markEl) markEl.textContent = '✕';
      if (textEl) textEl.textContent = '创建失败';
    }
    if (err4) {
      err4.textContent = e.message || '创建失败';
      err4.hidden = false;
    }
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function pollExtractProgress(pid) {
  if (!pid) return;
  const statusEl = $('#np-create-status') || $('#extract-override-progress');
  const textEl = statusEl ? statusEl.querySelector('.wizard-status-text') : null;

  for (let i = 0; i < 600; i += 1) {  // ~10 min max
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(pid)}/extract-genre/progress`);
      const s = await r.json();
      if (textEl && s.phase) {
        textEl.textContent = `拆解中 · ${s.phase}${s.progress ? ' · ' + s.progress : ''}`;
      }
      if (s.state === 'done') {
        toast('题材拆解完成 · 正在刷新…');
        setTimeout(() => location.reload(), 400);
        return;
      }
      if (s.state === 'failed' || s.state === 'aborted') {
        const msg = `拆解${s.state === 'aborted' ? '已中止' : '失败'}：${s.error || s.state}`;
        if (textEl) textEl.textContent = msg;
        toast(msg, true);
        return;
      }
    } catch (_) { /* tolerate polling hiccups */ }
    await new Promise((res) => setTimeout(res, 1000));
  }
  toast('拆解超时 · 请刷新页面查看状态', true);
}

// =========================================================
//  OVERRIDE GENRE (⎇ button on project home, Phase 4 Task 4.7)
//    POSTs /api/projects/<pid>/extract-genre → 202 + pollExtractProgress.
// =========================================================

function initExtractOverride() {
  const btn = $('#btn-extract-genre-override');
  const dlg = $('#extract-override-dialog');
  if (!btn || !dlg) return;

  btn.onclick = async () => {
    // Need active project id
    const pid = getActiveProjectId();
    if (!pid) {
      toast('先激活一个作品', true);
      return;
    }
    // Load novels pool fresh
    const box = $('#override-novels-checkboxes');
    if (box) {
      box.innerHTML = '<span class="form-hint">加载中…</span>';
      try {
        const data = await apiCall('/api/novels');
        renderNovelsCheckboxes(box, data.novels || [], 'override_source');
      } catch (e) {
        box.innerHTML = `<span class="form-error">加载失败: ${e.message}</span>`;
      }
    }
    // Reset progress state
    $('#extract-override-progress').hidden = true;
    const errEl = $('#extract-override-error');
    if (errEl) { errEl.hidden = true; errEl.textContent = ''; }
    dlg.showModal();
  };

  const form = $('#extract-override-form');
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const sources = fd.getAll('override_source');
      const errEl = $('#extract-override-error');
      if (errEl) { errEl.hidden = true; errEl.textContent = ''; }
      if (sources.length === 0) {
        if (errEl) { errEl.textContent = '请至少勾选一份素材'; errEl.hidden = false; }
        return;
      }
      const pid = getActiveProjectId();
      if (!pid) {
        if (errEl) { errEl.textContent = '找不到当前作品'; errEl.hidden = false; }
        return;
      }
      try {
        const r = await fetch(`/api/projects/${encodeURIComponent(pid)}/extract-genre`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sources,
            with_trial: fd.get('override_with_trial') === 'on',
          }),
        });
        const body = await r.json().catch(() => ({}));
        if (r.status !== 202 && !r.ok) {
          const reason = body.reason || body.detail || body.error || ('HTTP ' + r.status);
          throw new Error(reason);
        }
        // Show progress area, hide form
        $('#extract-override-progress').hidden = false;
        form.querySelectorAll('button, input').forEach((n) => { n.disabled = true; });
        pollExtractProgress(pid);
      } catch (e2) {
        if (errEl) { errEl.textContent = '失败: ' + e2.message; errEl.hidden = false; }
      }
    };
  }
}

function getActiveProjectId() {
  // Prefer live state snapshot (freshest); fall back to body data-attr.
  const fromState = state.snapshot
    && state.snapshot.progress
    && state.snapshot.progress.active_project;
  if (fromState) return fromState;
  return document.body.dataset.activeProject || null;
}

function wireTabs() {
  $$('.tab[data-tab]').forEach((b) =>
    b.addEventListener('click', () => setCenterTab(b.dataset.tab)));
  $$('.tab[data-rtab]').forEach((b) =>
    b.addEventListener('click', () => setRightTab(b.dataset.rtab)));
}

function openSourceEditor() {
  const dlg = $('#dlg-sources');
  const pid = (state.snapshot && state.snapshot.progress && state.snapshot.progress.active_project) || '—';
  $('#src-active-project').textContent = pid;
  initSourceEditor('[data-scope="standalone"]');
  dlg.showModal();
}

function initSourceEditor(scopeSel) {
  const scope = document.querySelector(`.src-editor${scopeSel}`);
  if (!scope) return;
  const tabs = scope.querySelectorAll('.src-tab');
  const area = scope.querySelector('[data-src-area]');
  const err = scope.querySelector('[data-src-error]');
  const saveBtn = scope.querySelector('[data-src-save]');

  // Initial state: activate first tab + load
  tabs.forEach((t) => t.classList.remove('is-active'));
  tabs[0].classList.add('is-active');
  loadSourceFile(scope, tabs[0].dataset.src);

  tabs.forEach((t) => {
    t.onclick = () => {
      tabs.forEach((x) => x.classList.toggle('is-active', x === t));
      loadSourceFile(scope, t.dataset.src);
    };
  });

  saveBtn.onclick = async () => {
    const active = scope.querySelector('.src-tab.is-active');
    if (!active) return;
    const name = active.dataset.src;
    err.hidden = true;
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中…';
    try {
      await apiCall('/api/project-files', {
        method: 'PUT',
        body: JSON.stringify({ name, content: area.value }),
      });
      toast(`已保存 · ${name} · state 已重新同步`);
      pollState();
    } catch (e) {
      err.textContent = '保存失败: ' + e.message;
      err.hidden = false;
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = scope.dataset.scope === 'wizard' ? '保存当前页' : '保存';
    }
  };
}

async function loadSourceFile(scope, name) {
  const area = scope.querySelector('[data-src-area]');
  const err = scope.querySelector('[data-src-error]');
  err.hidden = true;
  area.value = '加载中…';
  area.disabled = true;
  try {
    const body = await apiCall('/api/project-files?name=' + encodeURIComponent(name));
    area.value = body.content || '';
  } catch (e) {
    area.value = '';
    err.textContent = `无法加载 ${name}: ${e.message}`;
    err.hidden = false;
  } finally {
    area.disabled = false;
  }
}

// =========================================================
//  SETTINGS (.env editor)
// =========================================================

async function openSettingsDialog() {
  const dlg = $('#dlg-settings');
  const errEl = $('#st-error');
  errEl.hidden = true;
  // Reset password fields every open (blank = keep current)
  $('#st-deepseek-key').value = '';
  $('#st-perplexity-key').value = '';

  // Load current env into the form
  try {
    const env = await apiCall('/api/env');
    setHint('st-deepseek-key',  env.DEEPSEEK_API_KEY);
    setHint('st-perplexity-key', env.PERPLEXITY_API_KEY);
    $('#st-deepseek-base').value  = (env.DEEPSEEK_BASE_URL  && env.DEEPSEEK_BASE_URL.value)  || '';
    $('#st-deepseek-model').value = (env.DEEPSEEK_MODEL     && env.DEEPSEEK_MODEL.value)     || '';
    $('#st-perplexity-base').value  = (env.PERPLEXITY_BASE_URL  && env.PERPLEXITY_BASE_URL.value)  || '';
    $('#st-perplexity-model').value = (env.PERPLEXITY_MODEL     && env.PERPLEXITY_MODEL.value)     || '';
  } catch (e) {
    errEl.textContent = '加载 .env 失败: ' + e.message;
    errEl.hidden = false;
  }

  // Wire the submit handler (reset each open to avoid stacking)
  $('#settings-form').onsubmit = (e) => {
    e.preventDefault();
    saveSettings();
  };

  dlg.showModal();
}

function setHint(fieldId, meta) {
  const hint = document.querySelector(`[data-hint-for="${fieldId}"]`);
  if (!hint) return;
  if (!meta) { hint.textContent = ''; return; }
  if (meta.set) {
    hint.textContent = `当前已设置 · ${meta.preview || ''} （留空则保留）`;
  } else {
    hint.textContent = '尚未设置';
  }
}

async function saveSettings() {
  const errEl = $('#st-error');
  errEl.hidden = true;
  const payload = {};
  // Sensitive: only send if user actually typed something (blank = keep).
  const dsKey = $('#st-deepseek-key').value;
  if (dsKey) payload.DEEPSEEK_API_KEY = dsKey;
  const pxKey = $('#st-perplexity-key').value;
  if (pxKey) payload.PERPLEXITY_API_KEY = pxKey;
  // Non-sensitive: always send current form value (blank means "delete this key")
  payload.DEEPSEEK_BASE_URL  = $('#st-deepseek-base').value;
  payload.DEEPSEEK_MODEL     = $('#st-deepseek-model').value;
  payload.PERPLEXITY_BASE_URL  = $('#st-perplexity-base').value;
  payload.PERPLEXITY_MODEL     = $('#st-perplexity-model').value;

  if (Object.keys(payload).length === 0) {
    errEl.textContent = '没有要保存的字段';
    errEl.hidden = false;
    return;
  }

  try {
    const r = await apiCall('/api/env', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    toast(`已保存 · 更新了 ${r.updated.length} 个字段`);
    $('#dlg-settings').close();
  } catch (e) {
    errEl.textContent = '保存失败: ' + e.message;
    errEl.hidden = false;
  }
}

// =========================================================
//  ONBOARDING (gating check on first paint)
// =========================================================

async function checkOnboarding() {
  // Returns { needed: bool, step: 'key' | 'project' | null }
  let envOk = false;
  try {
    const env = await apiCall('/api/env');
    envOk = !!(env.DEEPSEEK_API_KEY && env.DEEPSEEK_API_KEY.set);
  } catch (_) { /* treat as not ok */ }

  if (!envOk) return { needed: true, step: 'key' };

  const pid = state.snapshot && state.snapshot.progress && state.snapshot.progress.active_project;
  if (!pid) {
    // Fallback: also check /api/projects in case progress.json wasn't primed
    try {
      const { active } = await apiCall('/api/projects');
      if (!active) return { needed: true, step: 'project' };
    } catch (_) {
      return { needed: true, step: 'project' };
    }
  }
  return { needed: false };
}

async function showOnboarding(step) {
  const overlay = $('#onboarding');
  overlay.hidden = false;
  showOnboardingStep(step);
  if (step === 'key') wireOnboardingKey();
  if (step === 'project') await wireOnboardingProjects();
}

function showOnboardingStep(step) {
  $$('.onb-step').forEach((n) => { n.hidden = n.dataset.step !== step; });
}

function wireOnboardingKey() {
  const form = $('#onb-key-form');
  const errEl = $('#onb-key-error');
  form.onsubmit = async (e) => {
    e.preventDefault();
    errEl.hidden = true;
    const ds = $('#onb-deepseek').value.trim();
    const px = $('#onb-perplexity').value.trim();
    if (!ds) {
      errEl.textContent = 'DEEPSEEK_API_KEY 必填';
      errEl.hidden = false;
      return;
    }
    const payload = { DEEPSEEK_API_KEY: ds };
    if (px) payload.PERPLEXITY_API_KEY = px;
    try {
      await apiCall('/api/env', { method: 'POST', body: JSON.stringify(payload) });
      toast('已保存 · 正在检查作品…');
      // Advance to project step (re-check in case already activated)
      showOnboardingStep('project');
      await wireOnboardingProjects();
    } catch (e2) {
      errEl.textContent = e2.message;
      errEl.hidden = false;
    }
  };
}

async function wireOnboardingProjects() {
  const grid = $('#onb-project-grid');
  grid.innerHTML = '<div class="project-grid-loading">加载作品列表…</div>';
  try {
    const { active, projects } = await apiCall('/api/projects');
    // If somehow an active project already exists, skip onboarding.
    if (active) {
      $('#onboarding').hidden = true;
      location.reload();
      return;
    }
    renderProjectGrid(grid, projects, active, {
      onActivate: async (pid) => {
        try {
          await apiCall('/api/projects/activate', {
            method: 'POST',
            body: JSON.stringify({ id: pid }),
          });
          toast('已激活 · 正在加载…');
          setTimeout(() => location.reload(), 400);
        } catch (e) {
          toast('激活失败: ' + e.message, true);
        }
      },
      onNew: openNewProjectWizard,
    });
  } catch (e) {
    grid.innerHTML = '';
    grid.appendChild(el('div', { class: 'form-error' }, '加载作品列表失败: ' + e.message));
  }
}

function wireButtons() {
  // Run panel
  $('#run-mode').addEventListener('change', () => { syncRunFields(); });
  $('#btn-run').addEventListener('click', doRun);
  $('#btn-abort').addEventListener('click', doAbort);
  $('#btn-reload').addEventListener('click', () => location.reload());

  // Project switcher + settings
  $('#btn-project').addEventListener('click', openProjectPicker);
  $('#btn-settings').addEventListener('click', openSettingsDialog);

  // Override-genre button + dialog (Phase 4 Task 4.7)
  initExtractOverride();

  // Generic dialog close (data-close-dialog)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-close-dialog]');
    if (btn) {
      const dlg = btn.closest('dialog');
      if (dlg && dlg.open) dlg.close();
    }
  });

  // Close dialogs with backdrop click (native dialogs leave this to us)
  document.querySelectorAll('dialog.dlg').forEach((dlg) => {
    dlg.addEventListener('click', (e) => {
      // Click on the dialog element itself (not children) = backdrop
      const rect = dlg.getBoundingClientRect();
      const inside = e.clientX >= rect.left && e.clientX <= rect.right
                  && e.clientY >= rect.top  && e.clientY <= rect.bottom;
      if (!inside) dlg.close();
    });
  });

  syncRunFields();
}

// ---------- loading overlay helpers ----------

function setLoadingPhase(text) {
  const el = document.getElementById('loading-phase');
  if (el) el.textContent = text;
}

function hideLoadingOverlay() {
  const el = document.getElementById('loading-overlay');
  if (!el) return;
  el.classList.add('is-hiding');
  el.setAttribute('aria-busy', 'false');
}


async function init() {
  wireTabs();
  wireButtons();
  setLoadingPhase('读取 state/ 快照…');
  await pollState();

  // Onboarding gate — if env or active project is missing, show the wizard
  // and keep the loading overlay dim behind it. Main UI init continues in
  // the background so once the user finishes onboarding (triggering a reload)
  // state is already warm.
  setLoadingPhase('检查配置…');
  const gate = await checkOnboarding();
  if (gate.needed) {
    hideLoadingOverlay();
    await showOnboarding(gate.step);
    return;
  }

  setLoadingPhase('加载 prompt log…');
  await refreshPrompts();
  setLoadingPhase('读取运行状态…');
  await pollStatus();
  pollPrompts();
  // fast state refresh
  (function loopState() {
    state.statePollTimer = setTimeout(async () => {
      await pollState();
      loopState();
    }, state.status.running ? 2000 : 4000);
  })();

  // Auto-open the first produced chapter on first load
  setLoadingPhase('渲染界面…');
  if (state.snapshot && state.snapshot.chapters.length) {
    const produced = state.snapshot.chapters.find((c) => c.has_md);
    if (produced) openFile(`state/chapters/ch${String(produced.ch).padStart(3, '0')}.md`);
  }

  requestAnimationFrame(hideLoadingOverlay);
}

window.addEventListener('DOMContentLoaded', init);
