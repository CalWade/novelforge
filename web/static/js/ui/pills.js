/* =========================================================
   ui/pills.js — top bar pills (chapter / running / debt / calls)
   + brand subtitle sync.
   ========================================================= */

import { $ } from '../utils.js';
import { state } from '../state.js';
import {
  syncRunButtons,
  syncProjectButton,
  syncReadonlyBanner,
  autofillRunChapter,
} from './runControls.js';

export function renderPills() {
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

  // Bookkeeping tab badge — show "n/3" only when the ledger isn't fully populated.
  // When a book opts out of resource_ledger (no resource_schema.yaml),
  // "full" means 2/2; we surface the partial state so users notice the gap
  // but stay quiet once everything has been produced.
  const bk = s.bookkeeping || {};
  const bkBadge = $('#tab-bookkeeping-badge');
  if (bkBadge) {
    const ledgerEnabled = !!bk.has_resource_schema;
    const required = ledgerEnabled ? 3 : 2;
    let have = 0;
    if (bk.has_status_card) have += 1;
    if (bk.has_pending_hooks) have += 1;
    if (ledgerEnabled && bk.has_resource_ledger) have += 1;
    if (have < required) {
      bkBadge.textContent = `${have}/${required}`;
    } else {
      bkBadge.textContent = '';
    }
  }

  // Run panel + header sync (idempotent; safe to call on every poll)
  syncRunButtons();
  syncProjectButton();
  syncReadonlyBanner();
  autofillRunChapter();

  // Running genre-extract jobs pill (Task 16).
  // Fire-and-forget: the pill hides itself on error, so a missing /api/jobs
  // endpoint (e.g. during local dev) never breaks the rest of the top bar.
  renderJobsPill();
}

// Top-bar pill showing count of running genre-extract jobs.
// Hidden when there are no running jobs; links to /jobs?state=running.
export async function renderJobsPill() {
  const el = document.getElementById('pill-jobs');
  if (!el) return;
  try {
    const r = await fetch('/api/jobs?state=running');
    if (!r.ok) return;
    const { jobs } = await r.json();
    if (!jobs || jobs.length === 0) {
      el.style.display = 'none';
    } else {
      el.style.display = '';
      el.innerHTML = `<a href="/jobs?state=running">⚙ ${jobs.length} 个题材任务运行中</a>`;
    }
  } catch {
    // 网络错误静默隐藏，不破坏首页
    el.style.display = 'none';
  }
}

// Inject the active setting's title + subtitle into the top-bar brand line,
// so the UI reflects whichever setting was bootstrapped (not a hardcoded genre).
export function renderBrandSub() {
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
