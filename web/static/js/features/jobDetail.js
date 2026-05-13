const root = document.querySelector(".job-detail-page");
const jobId = root.dataset.jobId;

const $ = (sel) => document.querySelector(sel);
const logPane = $("#log-pane");
const btnAbort = $("#btn-abort");
const btnDelete = $("#btn-delete");

let logOffset = 0;
let polling = true;

const PHASE_ORDER = ["extract", "merge", "draft", "validate"];

function setNodeState(phase, state) {
  const node = document.querySelector(`.phase-node[data-phase="${phase}"]`);
  if (!node) return;
  node.classList.remove("pending", "active", "done", "failed");
  node.classList.add(state);
  const icon = node.querySelector(".phase-icon");
  icon.textContent = state === "done" ? "✓" : state === "active" ? "●" : state === "failed" ? "✕" : "○";
}

function renderPipeline(job) {
  const curIdx = job.phase ? PHASE_ORDER.indexOf(job.phase) : -1;
  PHASE_ORDER.forEach((p, i) => {
    if (i < curIdx) setNodeState(p, "done");
    else if (i === curIdx && job.state === "running") setNodeState(p, "active");
    else if (i === curIdx && job.state === "failed") setNodeState(p, "failed");
    else if (i === curIdx && (job.state === "done" || job.state === "aborted")) setNodeState(p, "done");
    else setNodeState(p, "pending");
  });
  // 子步骤
  const sub = job.sub_steps || {};
  document.querySelector('[data-sub="extract"]').textContent =
    sub.batch_total ? `batch ${sub.batch_cur || 0}/${sub.batch_total}` : "";
  document.querySelector('[data-sub="merge"]').textContent =
    sub.arc_total ? `arc ${sub.arc_cur || 0}/${sub.arc_total}` : "";
  document.querySelector('[data-sub="draft"]').textContent =
    sub.draft_pass ? `pass ${sub.draft_pass}/3` : "";
  document.querySelector('[data-sub="validate"]').textContent =
    sub.validate_round ? `round ${sub.validate_round}/2` : "";
}

function renderMeta(job) {
  $("#job-label").textContent = job.label;
  $("#job-kind").textContent = job.kind;
  $("#job-target").textContent = `${job.target.type}:${job.target.id}`;
  $("#job-started").textContent = new Date(job.started_at * 1000).toLocaleString("zh-CN");
  $("#job-updated").textContent = new Date(job.updated_at * 1000).toLocaleString("zh-CN");
  $("#job-finished").textContent = job.finished_at
    ? new Date(job.finished_at * 1000).toLocaleString("zh-CN")
    : "—";
  const badge = $("#job-state-badge");
  badge.textContent = job.state;
  badge.className = `badge badge-${job.state}`;
  const err = $("#job-error");
  if (job.error) {
    err.textContent = `错误：${job.error}`;
    err.style.display = "";
  } else {
    err.style.display = "none";
  }
  // 按钮显示
  btnAbort.style.display = job.state === "running" ? "" : "none";
  btnDelete.style.display =
    ["done", "failed", "aborted", "interrupted"].includes(job.state) ? "" : "none";
}

async function fetchJob() {
  const r = await fetch(`/api/jobs/${jobId}`);
  if (!r.ok) return null;
  return r.json();
}

async function fetchLog() {
  const r = await fetch(`/api/jobs/${jobId}/log?offset=${logOffset}`);
  if (!r.ok) return;
  const { content, next_offset } = await r.json();
  if (content) {
    logPane.textContent += content;
    logPane.scrollTop = logPane.scrollHeight;
  }
  logOffset = next_offset;
}

async function tick() {
  if (!polling) return;
  const job = await fetchJob();
  if (!job) return;
  renderMeta(job);
  renderPipeline(job);
  await fetchLog();
  if (["done", "failed", "aborted", "interrupted"].includes(job.state)) {
    polling = false;
    // 再拉一次尾巴以防最后几行没收
    await fetchLog();
  } else {
    setTimeout(tick, 1500);
  }
}

btnAbort.addEventListener("click", async () => {
  if (!confirm("确认中止该任务？")) return;
  btnAbort.disabled = true;
  const r = await fetch(`/api/jobs/${jobId}/abort`, { method: "POST" });
  if (!r.ok) {
    alert(`中止失败：${(await r.json()).error}`);
    btnAbort.disabled = false;
  }
});

btnDelete.addEventListener("click", async () => {
  if (!confirm("确认删除该任务的记录？日志也会一并删除。")) return;
  const r = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (r.ok) location.href = "/jobs";
  else alert(`删除失败：${(await r.json()).error}`);
});

tick();
