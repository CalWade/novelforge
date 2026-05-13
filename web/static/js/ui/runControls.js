/* =========================================================
   ui/runControls.js — run panel (mode selector / chapter / range)
   + header sync helpers (project button, readonly banner).

   The run panel covers all 9 pipeline entry points. Each mode
   maps to the POST /api/run body shape the backend expects
   (see _MODE_DISPATCH in app.py). Range mode has its own input
   format ("N-M"); packaging takes no chapter.
   ========================================================= */

import { $ } from '../utils.js';
import { apiCall, toast } from '../api.js';
import { state } from '../state.js';
import { pollStatus } from './polling.js';

const MODES_NO_CHAPTER = new Set(['range', 'packaging']);

export function syncRunFields() {
  const mode = $('#run-mode').value;
  $('#run-chapter-field').hidden = MODES_NO_CHAPTER.has(mode);
  $('#run-range-field').hidden = mode !== 'range';
}

export function autofillRunChapter() {
  const s = state.snapshot;
  if (!s) return;
  const input = $('#run-chapter');
  if (!input || document.activeElement === input) return;
  // Default to next chapter (or 1 if starting from scratch)
  const next = (s.progress.current_chapter || 0) + 1;
  input.value = Math.max(1, Math.min(next, s.chapters.length || next));
  input.max = String(s.chapters.length || 999);
}

export function syncRunButtons() {
  const running = !!(state.status && state.status.running);
  const readonly = !!(state.snapshot && state.snapshot.readonly_mode);
  const runBtn = $('#btn-run');
  const abortBtn = $('#btn-abort');
  if (runBtn) runBtn.disabled = running || readonly;
  if (abortBtn) abortBtn.disabled = !running || readonly;
}

export async function doRun() {
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

export async function doAbort() {
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
export function syncProjectButton() {
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

export function syncReadonlyBanner() {
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
