/* =========================================================
   features/sourceEditor.js — standalone "edit 4 source files" dialog.
   Opens from the project picker's "edit sources" button.
   ========================================================= */

import { $ } from '../utils.js';
import { apiCall, toast } from '../api.js';
import { state } from '../state.js';
import { pollState } from '../ui/polling.js';

export function openSourceEditor() {
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
