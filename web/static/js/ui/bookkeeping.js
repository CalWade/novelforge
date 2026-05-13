/* =========================================================
   ui/bookkeeping.js — Lesson-3 三件套专属视图
     current_status_card.md · pending_hooks.md · resource_ledger.md

   These three files are the *authoritative snapshot* of the world
   at the end of each chapter. The tab renders them side by side
   so a reader doing a "Context Reset" can rebuild reality in one
   glance instead of hunting through the file tree.
   ========================================================= */

import { el, fmtBytes } from '../utils.js';
import { api } from '../api.js';
import { state } from '../state.js';

const BOOKKEEPING_CARDS = [
  {
    key: 'status',
    path: 'state/current_status_card.md',
    missingMsg: '首章产出后生成',
    missingSub: 'StatusCardUpdater 会在每章 Summarizer 之后覆盖式重写这份文件。',
  },
  {
    key: 'hooks',
    path: 'state/pending_hooks.md',
    missingMsg: '首章产出后生成',
    missingSub: 'HookKeeper 维护活跃伏笔池；三操作：回收 / 新增 / 推进。',
  },
  {
    key: 'ledger',
    path: 'state/resource_ledger.md',
    missingMsg: '首章产出后生成',
    missingSub: 'ResourceLedger 按 resource_schema.yaml 记录资源变动。',
  },
];

// Per-card cache so repeat polls don't blow away DOM when nothing changed.
const _bkCache = { status: null, hooks: null, ledger: null };

// Bind refresh buttons once (delegation-style). Called lazily on first render.
let _bkRefreshWired = false;
function _wireBookkeepingRefresh() {
  if (_bkRefreshWired) return;
  const root = document.getElementById('bookkeeping-view');
  if (!root) return;
  root.addEventListener('click', (e) => {
    const btn = e.target.closest('.bk-card-refresh');
    if (!btn) return;
    const card = btn.closest('.bk-card');
    if (!card) return;
    const key = card.dataset.bk;
    const def = BOOKKEEPING_CARDS.find((c) => c.key === key);
    if (!def) return;
    e.preventDefault();
    btn.classList.add('is-spinning');
    setTimeout(() => btn.classList.remove('is-spinning'), 320);
    _bkCache[key] = null; // force re-render
    _renderBookkeepingCard(def, { forceFresh: true });
  });
  _bkRefreshWired = true;
}

/**
 * Refresh all three bookkeeping cards.
 * @param {{silent?: boolean, forceFresh?: boolean}} opts
 *   silent: don't show "loading" placeholders on refresh (used by poll).
 *   forceFresh: trigger amber flash on newly-loaded cards.
 */
export function renderBookkeeping(opts = {}) {
  _wireBookkeepingRefresh();
  BOOKKEEPING_CARDS.forEach((def) => _renderBookkeepingCard(def, opts));
}

async function _renderBookkeepingCard(def, opts = {}) {
  const card = document.querySelector(`.bk-card[data-bk="${def.key}"]`);
  if (!card) return;
  const body = card.querySelector('.bk-card-body');
  const flag = card.querySelector('.bk-card-flag');
  if (!body) return;

  // Ledger has a conditional "disabled" state: if the active book has no
  // resource_schema.yaml, the ledger is intentionally off and we say so.
  if (def.key === 'ledger') {
    const snap = state.snapshot || {};
    const bk = snap.bookkeeping || {};
    if (!bk.has_resource_schema) {
      card.classList.add('is-disabled');
      card.classList.remove('is-missing');
      if (flag) {
        flag.className = 'bk-card-flag flag-missing';
        flag.textContent = '未启用';
      }
      body.innerHTML = '';
      body.appendChild(el('div', { class: 'bk-disabled-note' },
        el('div', { class: 'bk-disabled-mark' }, '◌'),
        el('div', null, el('strong', null, '本作品未启用资源账本')),
        el('div', null,
          '作品目录下没有 ',
          el('code', null, 'resource_schema.yaml'),
          '；这通常是有意为之（如都市言情不数值化）。'),
      ));
      _bkCache.ledger = 'disabled';
      return;
    }
    card.classList.remove('is-disabled');
  }

  if (!opts.silent && _bkCache[def.key] === null) {
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-title' }, '加载中…')));
  }

  let res;
  try {
    res = await api('/api/file?path=' + encodeURIComponent(def.path));
  } catch (err) {
    // 404 is the common "not produced yet" case.
    card.classList.add('is-missing');
    card.classList.remove('is-disabled');
    if (flag) {
      flag.className = 'bk-card-flag flag-missing';
      flag.textContent = '尚未产出';
    }
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'placeholder' },
      el('div', { class: 'placeholder-mark' }, '◐'),
      el('div', { class: 'placeholder-title' }, def.missingMsg || '尚未产出'),
      el('div', { class: 'placeholder-sub' }, def.missingSub || '')));
    _bkCache[def.key] = 'missing';
    return;
  }

  card.classList.remove('is-missing', 'is-disabled');

  // Skip DOM work if content is unchanged (polling fires every few seconds).
  const signature = `${res.size}:${(res.content || '').length}:${(res.content || '').slice(-60)}`;
  const changed = _bkCache[def.key] !== signature;
  _bkCache[def.key] = signature;

  if (changed) {
    body.innerHTML = '';
    if (window.marked && (res.content || '').trim()) {
      const html = window.marked.parse(res.content, { breaks: false, gfm: true });
      const wrap = el('div', { class: 'bk-md' });
      wrap.innerHTML = html;
      body.appendChild(wrap);
    } else if (!(res.content || '').trim()) {
      body.appendChild(el('div', { class: 'placeholder' },
        el('div', { class: 'placeholder-title' }, '文件为空')));
    } else {
      const pre = el('pre');
      pre.textContent = res.content;
      body.appendChild(pre);
    }
  }

  if (flag) {
    flag.className = 'bk-card-flag flag-fresh';
    flag.textContent = `${fmtBytes(res.size)}`;
  }

  // Flash amber border if this is a manual refresh OR if content just changed
  // during a background poll. 400ms envelope — visible but not noisy.
  if (opts.forceFresh || (changed && opts.silent !== true && _bkCache[def.key] !== null)) {
    card.classList.remove('is-fresh');
    // force reflow so the animation restarts
    void card.offsetWidth;
    card.classList.add('is-fresh');
    setTimeout(() => card.classList.remove('is-fresh'), 900);
  }
}
