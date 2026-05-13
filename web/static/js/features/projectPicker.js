/* =========================================================
   features/projectPicker.js — the ≡ project dialog.
   Lets the user pick among /api/projects or open the new-project wizard.
   ========================================================= */

import { $, el } from '../utils.js';
import { apiCall, toast } from '../api.js';
import { state } from '../state.js';
import { openNewProjectWizard } from './projectWizard.js';
import { openSourceEditor } from './sourceEditor.js';

export async function openProjectPicker() {
  const dlg = $('#dlg-project');
  const grid = $('#pp-grid');
  grid.innerHTML = '<div class="project-grid-loading">加载中…</div>';
  dlg.showModal();
  try {
    const { active, projects } = await apiCall('/api/projects');
    renderProjectGrid(grid, projects, active, {
      onActivate: async (pid) => {
        if (pid === active) return;
        const target = projects.find((p) => p.id === pid);
        const name = (target && target.display_name) || pid;
        if (!confirm(`切换到 "${name}" ？当前进度保留在 state/ 里，可随时切回。`)) return;
        try {
          await apiCall('/api/projects/activate', {
            method: 'POST',
            body: JSON.stringify({ id: pid }),
          });
          toast('已切换 · 正在刷新…');
          setTimeout(() => location.reload(), 400);
        } catch (e) {
          toast('切换失败: ' + e.message, true);
        }
      },
      onNew: openNewProjectWizard,
    });
  } catch (e) {
    grid.innerHTML = '';
    grid.appendChild(el('div', { class: 'form-error' }, '加载作品列表失败: ' + e.message));
  }

  // Wire the "edit sources" button to open the standalone source editor
  // scoped to the currently active project.
  const editBtn = $('#pp-edit-sources');
  if (editBtn) {
    editBtn.onclick = () => {
      dlg.close();
      openSourceEditor();
    };
  }
}

export function renderProjectGrid(root, projects, activeId, { onActivate, onNew }) {
  root.innerHTML = '';
  const ro = !!(state.snapshot && state.snapshot.readonly_mode);
  projects.forEach((p) => {
    const isActive = p.id === activeId;
    const card = el('button', {
      class: 'project-card' + (isActive ? ' is-active' : ''),
      type: 'button',
      title: isActive ? '当前作品' : `切换到 ${p.display_name}`,
      onclick: () => { if (!isActive && onActivate && !ro) onActivate(p.id); },
    },
      el('div', { class: 'project-card-name' }, p.display_name || p.id),
      el('div', { class: 'project-card-meta' },
        p.genre ? el('span', { class: 'project-card-tag' }, p.genre) : null,
        isActive
          ? el('span', { class: 'project-card-tag is-active' }, '当前')
          : (p.has_state
              ? el('span', { class: 'project-card-tag is-stateful' }, '已初始化')
              : el('span', { class: 'project-card-tag is-uninit' }, '未初始化')),
      ),
      el('div', { class: 'project-card-id' }, p.id),
    );
    root.appendChild(card);
  });

  // Add a "+ 新建作品" tile (hidden in readonly mode)
  if (onNew && !ro) {
    const newCard = el('button', {
      class: 'project-card project-card-new',
      type: 'button',
      onclick: onNew,
    },
      el('div', null,
        el('span', { class: 'project-card-new-glyph' }, '+'),
        el('span', null, '新建作品'),
      ),
    );
    root.appendChild(newCard);
  }
}
