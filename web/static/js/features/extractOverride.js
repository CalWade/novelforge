/* =========================================================
   features/extractOverride.js — ⎇ button on project home.
   POSTs /api/projects/<pid>/extract-genre → 202 + pollExtractProgress.
   ========================================================= */

import { $ } from '../utils.js';
import { apiCall, toast } from '../api.js';
import { state } from '../state.js';
import { renderNovelsCheckboxes, pollExtractProgress } from './projectWizard.js';

export function initExtractOverride() {
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
        // For the ⎇ override path there's no post-creation work to do —
        // a successful extract just needs to reload the page so the new
        // genre files surface in the project UI.
        pollExtractProgress(pid).then((ok) => {
          if (ok) setTimeout(() => location.reload(), 400);
        });
      } catch (e2) {
        if (errEl) { errEl.textContent = '失败: ' + e2.message; errEl.hidden = false; }
      }
    };
  }
}

export function getActiveProjectId() {
  // Prefer live state snapshot (freshest); fall back to body data-attr.
  const fromState = state.snapshot
    && state.snapshot.progress
    && state.snapshot.progress.active_project;
  if (fromState) return fromState;
  return document.body.dataset.activeProject || null;
}
