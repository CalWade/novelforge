/* =========================================================
   features/settings.js — .env editor dialog.
   ========================================================= */

import { $ } from '../utils.js';
import { apiCall, toast } from '../api.js';

export async function openSettingsDialog() {
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
