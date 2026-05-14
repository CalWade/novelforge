/* =========================================================
   utils.js — pure helpers (no state access, no side effects).
   ========================================================= */

export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => Array.from(document.querySelectorAll(sel));

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function')
      node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function fmtBytes(b) {
  if (b == null) return '';
  if (b < 1024) return b + ' B';
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
  return (b / (1024 * 1024)).toFixed(2) + ' MB';
}

export function fmtRelTime(ts) {
  if (!ts) return '';
  const now = Date.now() / 1000;
  const d = now - ts;
  if (d < 5) return '刚刚';
  if (d < 60) return Math.round(d) + ' 秒前';
  if (d < 3600) return Math.round(d / 60) + ' 分钟前';
  if (d < 86400) return Math.round(d / 3600) + ' 小时前';
  return new Date(ts * 1000).toLocaleString();
}

export function fmtClock(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function parseChapterFromInputs(inputs) {
  if (!Array.isArray(inputs)) return null;
  for (const p of inputs) {
    const m = /ch(\d{3})\.(md|plan\.json|verdict\.json)/.exec(p) || /ch(\d{3})\.md/.exec(p);
    if (m) return parseInt(m[1], 10);
  }
  return null;
}

export function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}


/**
 * 渲染 novels/ 下素材库的多选 checkbox 到 DOM。
 * 共享 helper：NovelDNA 新建 preset 页（/presets/new）和原"覆盖题材"
 * 对话框都会用。现在 extract_override 已废弃，只剩 presetNew 消费者。
 *
 * @param {HTMLElement} root      容器
 * @param {Array}      novels    /api/novels 返回的列表
 * @param {string}     fieldName checkbox 的 name 属性
 */
export function renderNovelsCheckboxes(root, novels, fieldName) {
  root.innerHTML = '';
  if (!novels || novels.length === 0) {
    root.innerHTML = '<span class="form-hint">素材库为空，去 /novels 上传 txt 文件</span>';
    return;
  }
  novels.forEach((n) => {
    const name = n.name || n;
    const label = document.createElement('label');
    label.className = 'wizard-novel-row';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.name = fieldName;
    cb.value = name;
    const txt = document.createElement('span');
    txt.textContent = name;
    label.appendChild(cb);
    label.appendChild(txt);
    root.appendChild(label);
  });
}
