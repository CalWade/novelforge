/* =========================================================
   Novelforge — demo UI entrypoint
   Vanilla JS ES modules. No bundler, no framework. Fetch + DOM.

   This file is intentionally small. It wires the DOMContentLoaded
   boot sequence and the handful of buttons that don't belong to a
   feature module. Everything else lives in ./ui/ and ./features/.
   ========================================================= */

import { $ } from './utils.js';
import { state } from './state.js';
import { wireTabs, setCenterTab } from './ui/tabs.js';
import { pollState, pollStatus, pollPrompts } from './ui/polling.js';
import { refreshPrompts } from './ui/inspector.js';
import { openFile } from './ui/viewer.js';
import { syncRunFields, doRun, doAbort } from './ui/runControls.js';
import { openProjectPicker } from './features/projectPicker.js';
import { openSettingsDialog } from './features/settings.js';
import { initExtractOverride } from './features/extractOverride.js';
import { checkOnboarding, showOnboarding } from './features/onboarding.js';

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

  // Lane B Task #3: when the project is past ch1 AND a status card
  // exists, the "current time-point" ledgers are usually more useful
  // than the chapter-viewer default. We only do this on first paint;
  // thereafter the user's tab choice is respected (setCenterTab keeps
  // state, and the polling loop does not re-invoke this).
  //
  // Guards:
  //   1) snapshot must be loaded (otherwise we can't read progress)
  //   2) current_chapter > 1 — on a brand new project we want the
  //      chapter viewer so the author sees what they just wrote
  //   3) has_status_card — without the card the tab would just be
  //      a sea of placeholders, worse than the chapter view
  const snap = state.snapshot;
  if (snap
      && (snap.progress?.current_chapter || 0) > 1
      && snap.bookkeeping?.has_status_card) {
    setCenterTab('bookkeeping');
  }

  requestAnimationFrame(hideLoadingOverlay);
}

window.addEventListener('DOMContentLoaded', init);
