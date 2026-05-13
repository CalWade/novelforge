/* =========================================================
   features/extractProgress.js — poll + render the 4-phase
   "extract → merge → draft → validate" progress indicator.

   Shared between projectWizard (new-project async path) and
   extractOverride (⎇ button on project home).
   ========================================================= */

import { $ } from '../utils.js';
import { toast } from '../api.js';

// Update phase-timeline UI in place. Accepts the progress element (the
// <ol data-phase-timeline>) and the current phase name.
function renderPhaseTimeline(timelineEl, phase) {
  if (!timelineEl) return;
  const phases = ['extract', 'merge', 'draft', 'validate'];
  const curIdx = phases.indexOf(phase);
  phases.forEach((ph, i) => {
    const li = timelineEl.querySelector(`li[data-phase="${ph}"]`);
    if (!li) return;
    li.classList.toggle('is-done', curIdx === -1 ? false : i < curIdx);
    li.classList.toggle('is-active', i === curIdx);
  });
}

// Returns true when the extract completed cleanly, false on fail/abort.
// No hard iteration cap — large books can legitimately take >10 minutes.
// Polling stops on: state in {done, failed, aborted, unknown} OR user
// clicks the abort button (which the button handler sets via _aborted).
export async function pollExtractProgress(pid) {
  if (!pid) return false;
  // Prefer the wizard's status element; fall back to the override progress
  // box when the wizard isn't mounted (e.g. ⎇ dialog on project home).
  const containerEl = $('#np-create-status') || $('#extract-override-progress');
  const textEl = containerEl ? containerEl.querySelector('.wizard-status-text') : null;
  const timelineEl = containerEl ? containerEl.querySelector('[data-phase-timeline]') : null;
  const abortBtn = containerEl ? containerEl.querySelector('#btn-extract-abort, #np-btn-abort') : null;

  // Wire the abort button (idempotent — we overwrite onclick each poll session)
  let userAborted = false;
  if (abortBtn) {
    abortBtn.hidden = false;
    abortBtn.onclick = async () => {
      userAborted = true;
      abortBtn.disabled = true;
      try {
        await fetch(`/api/projects/${encodeURIComponent(pid)}/extract-genre/abort`, { method: 'POST' });
      } catch (_) { /* best-effort */ }
      toast('已请求中断');
    };
  }

  const POLL_MS = 1000;
  // Intentionally no iteration cap — the design doc promises up to 60min
  // tasks work. We rely on {done|failed|aborted} terminal states or the
  // user pressing abort to stop the loop.
  while (true) {
    if (userAborted) {
      if (textEl) textEl.textContent = '已中断';
      if (abortBtn) abortBtn.hidden = true;
      return false;
    }
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(pid)}/extract-genre/progress`);
      const s = await r.json();
      if (s.phase) renderPhaseTimeline(timelineEl, s.phase);
      if (textEl) {
        const detail = s.progress ? ' · ' + s.progress : '';
        if (s.phase) {
          textEl.textContent = `拆解中 · ${s.phase}${detail}`;
        } else if (s.state === 'running') {
          textEl.textContent = '准备中…';
        }
      }
      if (s.state === 'done') {
        if (timelineEl) {
          // Paint all four bars green.
          timelineEl.querySelectorAll('li').forEach((li) => {
            li.classList.remove('is-active');
            li.classList.add('is-done');
          });
        }
        if (abortBtn) abortBtn.hidden = true;
        toast('题材拆解完成');
        return true;
      }
      if (s.state === 'failed' || s.state === 'aborted' || s.state === 'unknown') {
        const msg = `拆解${s.state === 'aborted' ? '已中止' : (s.state === 'unknown' ? '任务丢失' : '失败')}：${s.error || s.state}`;
        if (textEl) textEl.textContent = msg;
        if (abortBtn) abortBtn.hidden = true;
        toast(msg, true);
        return false;
      }
    } catch (_) { /* tolerate polling hiccups */ }
    await new Promise((res) => setTimeout(res, POLL_MS));
  }
}
