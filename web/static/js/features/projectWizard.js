/* =========================================================
   features/projectWizard.js — 新建作品向导（3 步，2026-05-14 重构）

   流程：
     Step 1 · 选 preset（必选）
     Step 2 · 基本信息（书名 / 主角 / 计划章数）
              id 不再由用户填，后端根据 display_name 自动生成
     Step 3 · 起草大纲 & 人物（可选，一次性 drafter）

   POST /api/projects/new 一次调用搞定：synopsis / brief 直接进 payload。
   drafter 失败时作品仍创建成功，后端返回 warnings 数组，前端展示告警
   并保留"去作品页重跑"入口。
   ========================================================= */

import { $, $$ } from '../utils.js';
import { apiCall, toast } from '../api.js';

export async function openNewProjectWizard() {
  const dlg = $('#dlg-new-project');
  if (!dlg) return;
  initProjectWizard();
  await populatePresetSelect();
  dlg.showModal();
  wizardGoToStep(1);
}

function wizardGoToStep(n) {
  $$('.wizard-pane').forEach((el) => {
    const step = Number(el.dataset.wizardStep);
    el.hidden = step !== n;
    el.classList.toggle('is-active', step === n);
  });
}

function initProjectWizard() {
  const dlg = $('#dlg-new-project');
  if (!dlg || dlg.dataset.wired === '1') return;
  dlg.dataset.wired = '1';

  // Step navigation
  dlg.querySelectorAll('[data-wizard-next]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = Number(btn.dataset.wizardNext);
      if (wizardValidateStep(target - 1)) wizardGoToStep(target);
    });
  });
  dlg.querySelectorAll('[data-wizard-prev]').forEach((btn) => {
    btn.addEventListener('click', () => {
      wizardGoToStep(Number(btn.dataset.wizardPrev));
    });
  });

  // Form submit (final step)
  $('#project-wizard-form').addEventListener('submit', (e) => {
    e.preventDefault();
    wizardSubmit();
  });
}


async function populatePresetSelect() {
  const sel = $('#select-from-preset');
  const emptyHint = $('#wizard-preset-empty-hint');
  if (!sel) return;
  try {
    const data = await apiCall('/api/presets');
    const presets = data.presets || [];
    sel.innerHTML = '';
    if (presets.length === 0) {
      sel.innerHTML = '<option value="" disabled selected>暂无 preset</option>';
      if (emptyHint) emptyHint.hidden = false;
      return;
    }
    sel.innerHTML = '<option value="" disabled selected>请选择一个题材 preset</option>';
    // 先列内置，再列自建
    const builtin = presets.filter((p) => p.builtin);
    const custom = presets.filter((p) => !p.builtin);
    for (const p of [...builtin, ...custom]) {
      const opt = document.createElement('option');
      opt.value = p.id;
      const marker = p.builtin ? '◆' : '◇';
      const label = p.display_name && p.display_name !== p.id
        ? `${marker} ${p.display_name} · ${p.id}`
        : `${marker} ${p.id}`;
      opt.textContent = label;
      sel.appendChild(opt);
    }
    if (emptyHint) emptyHint.hidden = true;
  } catch (_) {
    sel.innerHTML = '<option value="" disabled selected>加载失败</option>';
    if (emptyHint) emptyHint.hidden = false;
  }
}


function wizardValidateStep(step) {
  const form = $('#project-wizard-form');
  const fd = new FormData(form);
  const errEl = document.querySelector(`[data-wizard-error="${step}"]`);
  const showErr = (msg) => {
    if (errEl) {
      errEl.textContent = msg;
      errEl.hidden = false;
    }
  };
  if (errEl) { errEl.hidden = true; errEl.textContent = ''; }

  if (step === 1) {
    const preset = (fd.get('from_preset') || '').toString().trim();
    if (!preset) {
      showErr('请选择一个题材 preset');
      return false;
    }
    return true;
  }
  if (step === 2) {
    const display = (fd.get('display_name') || '').toString().trim();
    const chRaw = (fd.get('chapter_count_target') || '').toString().trim();
    if (!display) { showErr('请输入书名'); return false; }
    // 章数留空允许（后端默认 50）；填了就校验 ≥ 1
    if (chRaw) {
      const chNum = Number(chRaw);
      if (!Number.isFinite(chNum) || chNum < 1) {
        showErr('计划章数必须 ≥ 1（或留空让 AI 默认 50 章）');
        return false;
      }
    }
    return true;
  }
  return true;
}


async function wizardSubmit() {
  const form = $('#project-wizard-form');
  if (!form) return;
  // 依次校验 Step 1 + Step 2
  for (const step of [1, 2]) {
    if (!wizardValidateStep(step)) {
      wizardGoToStep(step);
      return;
    }
  }

  const fd = new FormData(form);
  const synopsis = (fd.get('outline_synopsis') || '').toString().trim();
  const brief = (fd.get('characters_brief') || '').toString().trim();
  const protName = (fd.get('protagonist_name') || '').toString().trim();
  const chRaw = (fd.get('chapter_count_target') || '').toString().trim();

  const payload = {
    // id 不传 → 后端 auto_generate_project_id 从 display_name 生成
    display_name: (fd.get('display_name') || '').toString().trim(),
    from_preset: (fd.get('from_preset') || '').toString().trim(),
  };
  // 留空字段不进 payload：后端用默认值（protagonist_name="" / chapter_count_target=50）
  if (protName) payload.protagonist_name = protName;
  if (chRaw) payload.chapter_count_target = Number(chRaw);
  // outline / characters：有内容就传；空则默认 blank_*=true
  if (synopsis) {
    payload.outline_synopsis = synopsis;
  } else {
    payload.blank_outline = true;
  }
  if (brief) {
    payload.characters_brief = brief;
  } else {
    payload.blank_characters = true;
  }

  // UI 状态
  const err3 = document.querySelector('[data-wizard-error="3"]');
  if (err3) { err3.hidden = true; err3.textContent = ''; }
  const statusEl = $('#np-create-status');
  const textEl = statusEl ? statusEl.querySelector('.wizard-status-text') : null;
  const markEl = statusEl ? statusEl.querySelector('.wizard-status-mark') : null;
  const submitBtn = $('#btn-wizard-submit');
  if (statusEl) {
    statusEl.hidden = false;
    statusEl.classList.remove('is-done', 'is-error');
    if (markEl) markEl.textContent = '◐';
    if (textEl) {
      textEl.textContent = (synopsis || brief)
        ? '正在创建作品并起草…（LLM 调用可能需 30-90 秒）'
        : '正在创建作品…';
    }
  }
  if (submitBtn) submitBtn.disabled = true;

  try {
    const r = await fetch('/api/projects/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok || body.ok === false) {
      const reason = body.reason || body.detail || body.error || ('HTTP ' + r.status);
      throw new Error(reason);
    }

    const pid = body.project_id;
    const warnings = Array.isArray(body.warnings) ? body.warnings : [];

    // UI 成功 + 可能的告警提示
    if (statusEl) {
      statusEl.classList.add('is-done');
      if (markEl) markEl.textContent = '✓';
      if (textEl) {
        textEl.textContent = warnings.length > 0
          ? `已创建 · 但 ${warnings.length} 个字段起草失败，可在作品详情重试`
          : '已创建 · 正在激活…';
      }
    }
    if (warnings.length > 0) {
      const msg = warnings.map((w) =>
        `[${w.field}] ${w.reason || '起草失败'}`,
      ).join(' / ');
      toast('部分字段起草失败：' + msg + '（稍后可在作品详情页重跑）', true);
    }

    // 自动激活新作品
    try {
      await apiCall('/api/projects/activate', {
        method: 'POST',
        body: JSON.stringify({ id: pid }),
      });
    } catch (_) { /* activation best-effort */ }
    toast(warnings.length > 0
      ? '已创建并激活 · ' + pid + '（含起草告警）'
      : '已创建并激活 · ' + pid);
    setTimeout(() => location.reload(), 600);

  } catch (e) {
    if (statusEl) {
      statusEl.classList.add('is-error');
      if (markEl) markEl.textContent = '✕';
      if (textEl) textEl.textContent = '创建失败';
    }
    if (err3) {
      err3.textContent = e.message || '创建失败';
      err3.hidden = false;
    }
    if (submitBtn) submitBtn.disabled = false;
  }
}
