/* =========================================================
   ui/lessons.js — right-panel LESSONS tab (pitch crosswalk).
   Code pointers prefer opening the file in the center panel
   (logical_path); fall back to GitHub for directories.
   ========================================================= */

import { $, el } from '../utils.js';
import { LESSONS, REPO_URL } from '../state.js';
import { openFile } from './viewer.js';

export function renderLessons() {
  const root = $('#lessons-panel');
  if (!root) return;
  root.innerHTML = '';
  LESSONS.forEach((lesson) => root.appendChild(lessonCard(lesson)));
}

function lessonCard(lesson) {
  return el('div', { class: 'lesson-card', dataset: { n: lesson.n } },
    el('div', { class: 'lesson-card-head' },
      el('div', { class: 'lesson-n' }, `Lesson ${String(lesson.n).padStart(2, '0')}`),
      el('div', { class: `lesson-attr attr-${lesson.attribution_color}` }, lesson.attribution),
    ),
    el('h3', { class: 'lesson-title' }, lesson.title),
    el('div', { class: 'lesson-principle' }, lesson.principle),
    el('div', { class: 'lesson-section-label' }, '本项目落地'),
    el('ul', { class: 'lesson-impl' },
      ...lesson.impl.map((x) => el('li', null, x))),
    el('div', { class: 'lesson-section-label' }, '代码指针'),
    el('ul', { class: 'lesson-pointers' },
      ...lesson.code_pointers.map((p) => el('li', null, renderPointerFlask(p)))),
  );
}

function renderPointerFlask(p) {
  // Prefer opening the file in the center panel (logical_path), since users are here
  // because they want to *read* the repo. Fall back to GitHub for directories / code.
  if (p.logical_path) {
    return el('a', {
      class: 'ptr-link',
      href: '#',
      title: `打开 ${p.logical_path} (中栏)`,
      onclick: (e) => { e.preventDefault(); openFile(p.logical_path); },
    },
      el('code', null, p.label),
      el('span', { class: 'ptr-desc' }, p.desc),
      el('span', { class: 'ptr-arrow' }, '→'),
    );
  }
  const repoPath = p.github_path;
  const href = repoPath ? `${REPO_URL}/blob/main/${repoPath}` : '#';
  return el('a', {
    class: 'ptr-link',
    href,
    target: '_blank',
    rel: 'noopener',
    title: `GitHub · ${repoPath || p.label}`,
  },
    el('code', null, p.label),
    el('span', { class: 'ptr-desc' }, p.desc),
    el('span', { class: 'ptr-arrow' }, '↗'),
  );
}
