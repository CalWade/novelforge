/* =========================================================
   ui/tabs.js — center + right tab state machine.
   Tab switching fires lazy renders for heavy panes.
   ========================================================= */

import { $$ } from '../utils.js';
import { state } from '../state.js';
import { renderDebt } from './debt.js';
import { renderBookkeeping } from './bookkeeping.js';
import { renderLessons } from './lessons.js';
import { renderPrompts } from './inspector.js';

export function setCenterTab(name) {
  state.activeCenterTab = name;
  $$('.tab[data-tab]').forEach((b) => {
    const isActive = b.dataset.tab === name;
    b.classList.toggle('tab-active', isActive);
    b.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  $$('.tab-pane[data-pane]').forEach((p) => p.classList.toggle('tab-pane-active', p.dataset.pane === name));
  if (name === 'debt') renderDebt();
  if (name === 'bookkeeping') renderBookkeeping();
}

export function setRightTab(name) {
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

export function wireTabs() {
  $$('.tab[data-tab]').forEach((b) =>
    b.addEventListener('click', () => setCenterTab(b.dataset.tab)));
  $$('.tab[data-rtab]').forEach((b) =>
    b.addEventListener('click', () => setRightTab(b.dataset.rtab)));
}
