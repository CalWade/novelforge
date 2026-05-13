/* =========================================================
   features/onboarding.js — first-run onboarding gate.
   Two steps: (1) set DEEPSEEK_API_KEY, (2) pick or create a project.
   ========================================================= */

import { $, $$, el } from '../utils.js';
import { apiCall, toast } from '../api.js';
import { state } from '../state.js';
import { renderProjectGrid } from './projectPicker.js';
import { openNewProjectWizard } from './projectWizard.js';

export async function checkOnboarding() {
  // Returns { needed: bool, step: 'key' | 'project' | null }
  let envOk = false;
  try {
    const env = await apiCall('/api/env');
    envOk = !!(env.DEEPSEEK_API_KEY && env.DEEPSEEK_API_KEY.set);
  } catch (_) { /* treat as not ok */ }

  if (!envOk) return { needed: true, step: 'key' };

  const pid = state.snapshot && state.snapshot.progress && state.snapshot.progress.active_project;
  if (!pid) {
    // Fallback: also check /api/projects in case progress.json wasn't primed
    try {
      const { active } = await apiCall('/api/projects');
      if (!active) return { needed: true, step: 'project' };
    } catch (_) {
      return { needed: true, step: 'project' };
    }
  }
  return { needed: false };
}

export async function showOnboarding(step) {
  const overlay = $('#onboarding');
  overlay.hidden = false;
  showOnboardingStep(step);
  if (step === 'key') wireOnboardingKey();
  if (step === 'project') await wireOnboardingProjects();
}

function showOnboardingStep(step) {
  $$('.onb-step').forEach((n) => { n.hidden = n.dataset.step !== step; });
}

function wireOnboardingKey() {
  const form = $('#onb-key-form');
  const errEl = $('#onb-key-error');
  form.onsubmit = async (e) => {
    e.preventDefault();
    errEl.hidden = true;
    const ds = $('#onb-deepseek').value.trim();
    const px = $('#onb-perplexity').value.trim();
    if (!ds) {
      errEl.textContent = 'DEEPSEEK_API_KEY 必填';
      errEl.hidden = false;
      return;
    }
    const payload = { DEEPSEEK_API_KEY: ds };
    if (px) payload.PERPLEXITY_API_KEY = px;
    try {
      await apiCall('/api/env', { method: 'POST', body: JSON.stringify(payload) });
      toast('已保存 · 正在检查作品…');
      // Advance to project step (re-check in case already activated)
      showOnboardingStep('project');
      await wireOnboardingProjects();
    } catch (e2) {
      errEl.textContent = e2.message;
      errEl.hidden = false;
    }
  };
}

async function wireOnboardingProjects() {
  const grid = $('#onb-project-grid');
  grid.innerHTML = '<div class="project-grid-loading">加载作品列表…</div>';
  try {
    const { active, projects } = await apiCall('/api/projects');
    // If somehow an active project already exists, skip onboarding.
    if (active) {
      $('#onboarding').hidden = true;
      location.reload();
      return;
    }
    renderProjectGrid(grid, projects, active, {
      onActivate: async (pid) => {
        try {
          await apiCall('/api/projects/activate', {
            method: 'POST',
            body: JSON.stringify({ id: pid }),
          });
          toast('已激活 · 正在加载…');
          setTimeout(() => location.reload(), 400);
        } catch (e) {
          toast('激活失败: ' + e.message, true);
        }
      },
      onNew: openNewProjectWizard,
    });
  } catch (e) {
    grid.innerHTML = '';
    grid.appendChild(el('div', { class: 'form-error' }, '加载作品列表失败: ' + e.message));
  }
}
