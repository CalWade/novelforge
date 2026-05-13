// /jobs 列表页：fetch /api/jobs?state=... 并渲染。
const listEl = document.getElementById("jobs-list");
let currentFilter = "all";

async function fetchJobs() {
  const qs = currentFilter === "all" ? "" : `?state=${currentFilter}`;
  const r = await fetch(`/api/jobs${qs}`);
  if (!r.ok) return [];
  return (await r.json()).jobs;
}

function kindLabel(kind) {
  return {
    "from-novel": "素材库拆",
    "from-description": "从描述",
    "blank": "空壳",
    "extract-to-project": "覆盖作品",
  }[kind] || kind;
}

function stateBadge(state) {
  const map = {
    running: ["运行中", "badge-running"],
    aborting: ["中止中", "badge-aborting"],
    done: ["完成", "badge-done"],
    failed: ["失败", "badge-failed"],
    aborted: ["已中止", "badge-aborted"],
    interrupted: ["中断", "badge-interrupted"],
  };
  const [text, cls] = map[state] || [state, ""];
  return `<span class="badge ${cls}">${text}</span>`;
}

function renderRow(job) {
  const target = `${job.target.type}:${job.target.id}`;
  const progress = job.progress_text || "";
  const ago = new Date(job.updated_at * 1000).toLocaleString("zh-CN");
  return `
    <a class="job-row" href="/jobs/${job.job_id}">
      <div class="job-row-main">
        <span class="job-kind">${kindLabel(job.kind)}</span>
        <span class="job-target">${target}</span>
        <span class="job-label">${job.label}</span>
      </div>
      <div class="job-row-meta">
        ${stateBadge(job.state)}
        <span class="job-progress">${progress}</span>
        <span class="job-time">${ago}</span>
      </div>
    </a>
  `;
}

async function render() {
  const jobs = await fetchJobs();
  if (jobs.length === 0) {
    listEl.innerHTML = `<div class="jobs-empty">暂无任务</div>`;
    return;
  }
  listEl.innerHTML = jobs.map(renderRow).join("");
}

document.querySelectorAll(".filter-tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.state;
    render();
  });
});

// 初始渲染 + 每 3 秒自动刷新（running 的 job 会更新 progress）
const urlState = new URLSearchParams(location.search).get("state");
if (urlState) {
  currentFilter = urlState;
  document.querySelectorAll(".filter-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.state === urlState);
  });
}
render();
setInterval(render, 3000);
