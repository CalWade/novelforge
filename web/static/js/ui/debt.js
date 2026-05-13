/* =========================================================
   ui/debt.js — center "Debt" tab.
   ========================================================= */

import { $, el, fmtRelTime } from '../utils.js';
import { api } from '../api.js';

export async function renderDebt() {
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
