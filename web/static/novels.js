/* Novels library — Task A stub. Task B will implement the real UI. */
(function () {
  'use strict';
  // minimal hydrate so the page isn't blank; Task B replaces this entirely
  document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('novels-root');
    if (!root) return;
    root.innerHTML = '<p style="text-align:center;color:var(--text-soft);padding:40px;">素材库 UI 建设中…</p>';
  });
})();
