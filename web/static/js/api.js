/* =========================================================
   api.js — fetch wrappers + toast notifications.
   ========================================================= */

import { $ } from './utils.js';

export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j.reason || j.detail || j.error || detail;
    } catch (_) { /* noop */ }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json();
}

/**
 * Unified mutating-API helper. Backend ships {ok:false, reason} on failure
 * AND may return 4xx/5xx; we collapse both into a thrown Error(reason).
 * On success returns the parsed JSON body.
 */
export async function apiCall(path, opts = {}) {
  const headers = opts.headers || {};
  if (opts.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const resp = await fetch(path, { ...opts, headers });
  let body = {};
  try { body = await resp.json(); } catch (_) { /* allow empty */ }
  if (!resp.ok || body.ok === false || body.started === false) {
    const reason = body.reason || body.detail || body.error || `HTTP ${resp.status}`;
    const err = new Error(reason);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

export function toast(msg, isErr = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('is-error', isErr);
  t.classList.add('is-show');
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove('is-show'), 3200);
}
