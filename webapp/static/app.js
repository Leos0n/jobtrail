"use strict";

const state = { jobs: [], trash: [], statuses: [], filter: "all", selectedId: null };

const $ = (sel, root = document) => root.querySelector(sel);
const api = {
  async get(path) { const r = await fetch(path); if (!r.ok) throw await err(r); return r.json(); },
  async send(method, path, body) {
    const r = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw await err(r);
    return r.status === 204 ? null : r.json();
  },
};
async function err(r) {
  try { const j = await r.json(); return new Error(j.error || r.statusText); }
  catch { return new Error(r.statusText); }
}

/* ---------- toast (with optional action) ---------- */
function toast(msg, isErr = false) { showToast(msg, isErr ? "err" : "", null, null, isErr ? 5000 : 2500); }
function toastAction(msg, label, fn) { showToast(msg, "", label, fn, 7000); }
function showToast(msg, cls, label, fn, ms) {
  const t = $("#toast");
  t.innerHTML = "";
  t.className = "toast" + (cls ? " " + cls : "");
  const span = document.createElement("span"); span.textContent = msg; t.appendChild(span);
  if (label) {
    const b = document.createElement("button");
    b.className = "toast-action"; b.textContent = label;
    b.onclick = () => { t.hidden = true; fn(); };
    t.appendChild(b);
  }
  t.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { t.hidden = true; }, ms);
}

/* ---------- data ---------- */
async function loadAll() {
  const meta = await api.get("/api/meta");
  state.statuses = meta.statuses;
  state.jobs = await api.get("/api/jobs");
  state.trash = await api.get("/api/trash");
  $("#trash-count").textContent = state.trash.length;
  renderFilters();
  renderList();
  loadBackupStatus();
  if (state.selectedId && byId(state.selectedId)) renderDetail(byId(state.selectedId));
}
const byId = (id) => state.jobs.find((j) => j.id === id);

async function loadBackupStatus() {
  try {
    const b = await api.get("/api/backups");
    $("#backup-status").textContent = b.length
      ? `Last backup: ${fmtWhen(b[0].created)} · ${b.length} kept`
      : "No backups yet";
  } catch { /* ignore */ }
}

/* ---------- filters ---------- */
function renderFilters() {
  const counts = { all: state.jobs.length };
  for (const s of state.statuses) counts[s] = 0;
  for (const j of state.jobs) counts[j.status] = (counts[j.status] || 0) + 1;
  const tabs = ["all", ...state.statuses];
  const nav = $("#filters");
  nav.innerHTML = "";
  for (const t of tabs) {
    const b = document.createElement("button");
    b.className = t === state.filter ? "active" : "";
    b.innerHTML = `${cap(t)} <span class="count">${counts[t] || 0}</span>`;
    b.onclick = () => { state.filter = t; renderFilters(); renderList(); syncTrashBtn(); };
    nav.appendChild(b);
  }
  syncTrashBtn();
}
function syncTrashBtn() {
  $("#trash-btn").classList.toggle("active", state.filter === "trash");
}

/* ---------- list ---------- */
function renderList() {
  const ul = $("#job-list");
  ul.innerHTML = "";
  if (state.filter === "trash") return renderTrash(ul);

  const jobs = state.jobs.filter(
    (j) => state.filter === "all" || j.status === state.filter
  );
  $("#empty-list").hidden = state.jobs.length !== 0;
  for (const j of jobs) {
    const li = document.createElement("li");
    li.className = "job-card" + (j.id === state.selectedId ? " selected" : "");
    li.onclick = () => selectJob(j.id);
    li.innerHTML = `
      <h3>${esc(j.title || "Untitled role")}</h3>
      <div class="company">${esc(j.company || "—")}</div>
      <div class="card-foot">
        <span class="pill ${j.status}">${cap(j.status)}</span>
        ${j.location ? `<span class="loc">${esc(j.location)}</span>` : ""}
        <span class="source-tag">${esc(j.source || "")}</span>
      </div>`;
    ul.appendChild(li);
  }
}

function renderTrash(ul) {
  $("#empty-list").hidden = state.trash.length !== 0;
  $("#detail-empty").hidden = false;
  $("#detail").hidden = true;
  for (const j of state.trash) {
    const li = document.createElement("li");
    li.className = "job-card trashed";
    li.innerHTML = `
      <h3>${esc(j.title || "Untitled role")}</h3>
      <div class="company">${esc(j.company || "—")}</div>
      <div class="card-foot">
        <span class="loc">Trashed ${fmtWhen(j.deleted_at)}</span>
      </div>
      <div class="trash-actions"></div>`;
    const actions = $(".trash-actions", li);
    const restore = document.createElement("button");
    restore.className = "btn-ghost"; restore.textContent = "Restore";
    restore.onclick = () => restoreJob(j.id);
    const purge = document.createElement("button");
    purge.className = "btn-danger"; purge.textContent = "Delete forever";
    purge.onclick = () => purgeJob(j.id, j.title);
    actions.append(restore, purge);
    ul.appendChild(li);
  }
}

function selectJob(id) {
  state.selectedId = id;
  renderList();
  renderDetail(byId(id));
}

/* ---------- detail ---------- */
function renderDetail(job) {
  $("#detail-empty").hidden = !!job;
  const host = $("#detail");
  host.hidden = !job;
  if (!job) { host.innerHTML = ""; return; }

  const tpl = $("#detail-template").content.cloneNode(true);
  $(".d-title", tpl).textContent = job.title || "Untitled role";
  $(".d-company", tpl).textContent = job.company || "";
  const src = $(".d-source", tpl); src.href = job.url || "#";
  $(".d-md", tpl).onclick = () => window.open(`/api/jobs/${job.id}/markdown`, "_blank");
  $(".d-delete", tpl).onclick = () => removeJob(job.id, job.title);

  const chips = $(".d-meta", tpl);
  const meta = [
    ["Location", job.location], ["Remote", job.remote],
    ["Type", job.employment_type], ["Salary", job.salary],
    ["Posted", (job.date_posted || "").slice(0, 10)], ["Source", job.source],
  ];
  for (const [k, v] of meta) if (v) {
    const c = document.createElement("span");
    c.className = "chip"; c.innerHTML = `<b>${esc(k)}:</b> ${esc(v)}`;
    chips.appendChild(c);
  }

  const sel = $(".d-status", tpl);
  for (const s of state.statuses) {
    const o = document.createElement("option");
    o.value = s; o.textContent = cap(s); if (s === job.status) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = () => patch(job.id, { status: sel.value });

  bindInput($(".d-applied", tpl), job.date_applied, (v) => patch(job.id, { date_applied: v }));
  bindInput($(".d-followup", tpl), job.follow_up_date, (v) => patch(job.id, { follow_up_date: v }));
  bindInput($(".d-salexp", tpl), job.salary_expectation, (v) => patch(job.id, { salary_expectation: v }));
  bindInput($(".d-contact", tpl), job.contact, (v) => patch(job.id, { contact: v }));
  bindInput($(".d-notes", tpl), job.notes, (v) => patch(job.id, { notes: v }));

  renderStars($(".d-stars", tpl), job);
  renderFiles(tpl, job);
  $(".desc-body", tpl).innerHTML = mdToHtml(job.description_md || "_No description captured._");

  host.innerHTML = "";
  host.appendChild(tpl);
}

function bindInput(el, value, save) {
  el.value = value || "";
  const handler = () => save(el.value.trim());
  if (el.type === "date") el.onchange = handler; else el.onblur = handler;
}

function renderStars(box, job) {
  box.innerHTML = "";
  const current = job.rating || 0;
  for (let i = 1; i <= 5; i++) {
    const s = document.createElement("span");
    s.className = "star" + (i <= current ? " on" : "");
    s.textContent = "★";
    s.onclick = () => patch(job.id, { rating: i === current ? 0 : i });
    box.appendChild(s);
  }
}

function renderFiles(tpl, job) {
  for (const slot of tpl.querySelectorAll(".file-slot")) {
    const kind = slot.dataset.kind;
    const row = $(".file-row", slot);
    const name = job[`${kind}_name`];
    row.innerHTML = "";
    if (name) {
      const tag = document.createElement("span");
      tag.className = "file-name"; tag.textContent = name; row.appendChild(tag);
      const dl = document.createElement("button");
      dl.className = "link-btn"; dl.textContent = "download";
      dl.onclick = () => window.open(`/api/jobs/${job.id}/file?kind=${kind}`, "_blank");
      row.appendChild(dl);
      const rm = document.createElement("button");
      rm.className = "link-btn"; rm.textContent = "remove";
      rm.onclick = () => removeFile(job.id, kind);
      row.appendChild(rm);
    } else {
      const label = document.createElement("label");
      label.className = "upload-label";
      label.textContent = "Attach file";
      const inp = document.createElement("input");
      inp.type = "file";
      inp.onchange = () => inp.files[0] && uploadFile(job.id, kind, inp.files[0]);
      label.appendChild(inp); row.appendChild(label);
    }
  }
}

/* ---------- mutations ---------- */
async function addJob(url) {
  const btn = $("#add-btn");
  btn.disabled = true; btn.textContent = "Fetching…";
  try {
    const job = await api.send("POST", "/api/jobs", { url });
    $("#add-url").value = "";
    if (state.filter === "trash") state.filter = "all";
    await loadAll();
    selectJob(job.id);
    toast(`Added “${job.title || "job"}”.`);
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = "Add job"; }
}

async function patch(id, fields) {
  try {
    const updated = await api.send("PATCH", `/api/jobs/${id}`, fields);
    Object.assign(byId(id), updated);
    renderFilters(); renderList();
    if ("status" in fields) renderDetail(byId(id));
  } catch (e) { toast(e.message, true); }
}

async function removeJob(id, title) {
  try {
    await api.send("DELETE", `/api/jobs/${id}`); // soft delete -> trash
    if (state.selectedId === id) { state.selectedId = null; renderDetail(null); }
    await loadAll();
    toastAction(`Moved “${title || "job"}” to Trash.`, "Undo", () => restoreJob(id, true));
  } catch (e) { toast(e.message, true); }
}

async function restoreJob(id, quiet) {
  try {
    await api.send("POST", `/api/jobs/${id}/restore`);
    await loadAll();
    if (!quiet) toast("Restored from Trash.");
    else toast("Restored.");
  } catch (e) { toast(e.message, true); }
}

async function purgeJob(id, title) {
  if (!confirm(`Permanently delete “${title || "this job"}” and its files?\nThis cannot be undone (a backup is kept).`)) return;
  try {
    await api.send("DELETE", `/api/jobs/${id}?purge=1`);
    await loadAll();
    toast("Permanently deleted.");
  } catch (e) { toast(e.message, true); }
}

function uploadFile(id, kind, file) {
  const reader = new FileReader();
  reader.onload = async () => {
    const b64 = reader.result.split(",")[1];
    try {
      const updated = await api.send("POST", `/api/jobs/${id}/file`, {
        kind, filename: file.name, content_b64: b64,
      });
      Object.assign(byId(id), updated);
      renderDetail(byId(id));
      toast(`${cap(kind.replace("_", " "))} attached.`);
    } catch (e) { toast(e.message, true); }
  };
  reader.readAsDataURL(file);
}

async function removeFile(id, kind) {
  try {
    const updated = await api.send("DELETE", `/api/jobs/${id}/file?kind=${kind}`);
    Object.assign(byId(id), updated);
    renderDetail(byId(id));
  } catch (e) { toast(e.message, true); }
}

/* ---------- backups & data ---------- */
function exportBackup() { window.open("/api/export", "_blank"); }

async function backupNow() {
  try { await api.send("POST", "/api/backup", {}); await loadBackupStatus(); toast("Backup saved."); }
  catch (e) { toast(e.message, true); }
}

function importBackup(file) {
  const reader = new FileReader();
  reader.onload = async () => {
    let data;
    try { data = JSON.parse(reader.result); }
    catch { return toast("That file is not valid JSON.", true); }
    try {
      const res = await api.send("POST", "/api/import", data);
      await loadAll();
      toast(`Imported ${res.added} job(s); skipped ${res.skipped} already present.`);
    } catch (e) { toast(e.message, true); }
  };
  reader.readAsText(file);
}

/* ---------- tiny markdown -> html ---------- */
function mdToHtml(md) {
  const lines = md.split("\n");
  let html = "", inList = false;
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+?)\*/g, "$1<em>$2</em>")
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  for (let raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    const li = line.match(/^[-*]\s+(.*)$/) || line.match(/^\d+\.\s+(.*)$/);
    if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(li[1])}</li>`; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    if (h) { const n = h[1].length; html += `<h${n}>${inline(h[2])}</h${n}>`; }
    else if (line.trim() === "---") { html += "<hr/>"; }
    else if (line.trim() === "") { /* skip */ }
    else { html += `<p>${inline(line)}</p>`; }
  }
  if (inList) html += "</ul>";
  return html;
}

/* ---------- utils ---------- */
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
const cap = (s) => (s || "").charAt(0).toUpperCase() + (s || "").slice(1);
function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/* ---------- boot ---------- */
$("#add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const url = $("#add-url").value.trim();
  if (url) addJob(url);
});
$("#trash-btn").addEventListener("click", () => {
  state.filter = state.filter === "trash" ? "all" : "trash";
  state.selectedId = null; renderDetail(null);
  renderFilters(); renderList();
});
$("#export-btn").addEventListener("click", exportBackup);
$("#backup-btn").addEventListener("click", backupNow);
$("#import-file").addEventListener("change", (e) => {
  if (e.target.files[0]) { importBackup(e.target.files[0]); e.target.value = ""; }
});
loadAll().catch((e) => toast("Could not load: " + e.message, true));
