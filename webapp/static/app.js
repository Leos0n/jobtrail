"use strict";

/* ---------------- icons (inline SVG, stroke = currentColor) ---------------- */
const ICONS = {
  cloud: '<path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 9a4.5 4.5 0 0 0 1 8.9Z"/>',
  download: '<path d="M12 4v10m0 0 4-4m-4 4-4-4M5 19h14"/>',
  upload: '<path d="M12 16V6m0 0 4 4m-4-4-4 4M5 19h14"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5L16 9"/>',
  grid: '<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M5 7h14M10 7V5h4v2m-7 0 1 12h8l1-12"/>',
  link: '<path d="M10 13a4 4 0 0 0 5.66 0l2.83-2.83a4 4 0 0 0-5.66-5.66L11 6m3 5a4 4 0 0 0-5.66 0L5.5 13.83a4 4 0 0 0 5.66 5.66L13 18"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  book: '<path d="M5 5a2 2 0 0 1 2-2h11v16H7a2 2 0 0 0-2 2V5Z"/><path d="M18 17H7a2 2 0 0 0-2 2"/>',
  "chev-left": '<path d="m15 6-6 6 6 6"/>',
  "chev-right": '<path d="m9 6 6 6-6 6"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  external: '<path d="M14 5h5v5M19 5l-8 8M12 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6"/>',
};
function svg(name, size = 20) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}
function paintIcons(root = document) {
  root.querySelectorAll("[data-ic]").forEach((el) => { if (!el.dataset.painted) { el.innerHTML = svg(el.dataset.ic); el.dataset.painted = "1"; } });
}

/* ---------------- api ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const api = {
  async get(p) { const r = await fetch(p); if (!r.ok) throw await e(r); return r.json(); },
  async send(m, p, b) { const r = await fetch(p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); if (!r.ok) throw await e(r); return r.status === 204 ? null : r.json(); },
};
async function e(r) { try { return new Error((await r.json()).error || r.statusText); } catch { return new Error(r.statusText); } }

/* ---------------- state ---------------- */
const state = { jobs: [], trash: [], statuses: [], view: "add", calMode: "month", calCursor: startOfMonth(new Date()), selectedId: null };

/* ---------------- utils ---------------- */
function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
const cap = (s) => (s || "").charAt(0).toUpperCase() + (s || "").slice(1);
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function isoToDate(s) { if (!s) return null; const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
function sameDay(a, b) { return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function fmtShort(d) { return d ? `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}` : ""; }
function fmtWhenIso(iso) { const d = iso && new Date(iso); return d && !isNaN(d) ? d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"; }
const byId = (id) => state.jobs.find((j) => j.id === id) || state.trash.find((j) => j.id === id);

function favClass(source) { const s = (source || "").toLowerCase(); return s.includes("linkedin") ? "linkedin" : s.includes("indeed") ? "indeed" : "other"; }
function favGlyph(job) { return (job.company || job.title || "J").trim().charAt(0).toUpperCase(); }
function brandSVG(source) {
  const c = favClass(source);
  if (c === "linkedin") return '<svg viewBox="0 0 40 40" width="100%" height="100%" aria-hidden="true"><rect width="40" height="40" fill="#0a66c2"/><text x="20" y="28" text-anchor="middle" font-family="Plus Jakarta Sans, Arial, sans-serif" font-size="20" font-weight="700" fill="#fff">in</text></svg>';
  return '<svg viewBox="0 0 40 40" width="100%" height="100%" aria-hidden="true"><rect width="40" height="40" fill="#2557a7"/><circle cx="20" cy="12.5" r="3.6" fill="#fff"/><rect x="16.4" y="17.5" width="7.2" height="13.5" rx="3.6" fill="#fff"/></svg>';
}
function favBadge(job) { const c = favClass(job.source); if (c === "other") return `<span class="fav other">${esc(favGlyph(job))}</span>`; return `<span class="fav brand">${brandSVG(job.source)}</span>`; }
function srcLabel(source) { const c = favClass(source); return c === "linkedin" ? "LinkedIn" : c === "indeed" ? "Indeed" : (source ? cap(source.replace("-", " ")) : "Saved link"); }

/* ---------------- toast ---------------- */
function toast(msg, isErr) { showToast(msg, isErr ? "err" : "", null, null, isErr ? 5000 : 2600); }
function toastUndo(msg, fn) { showToast(msg, "", "Undo", fn, 7000); }
function showToast(msg, cls, label, fn, ms) {
  const t = $("#toast"); t.className = "toast" + (cls ? " " + cls : ""); t.innerHTML = `<span>${esc(msg)}</span>`;
  if (label) { const b = document.createElement("button"); b.className = "toast-action"; b.textContent = label; b.onclick = () => { t.hidden = true; fn(); }; t.appendChild(b); }
  t.hidden = false; clearTimeout(showToast._t); showToast._t = setTimeout(() => { t.hidden = true; }, ms);
}

/* ---------------- load ---------------- */
async function loadAll() {
  state.statuses = (await api.get("/api/meta")).statuses;
  state.jobs = await api.get("/api/jobs");
  state.trash = await api.get("/api/trash");
  loadBackupStatus();
  render();
}
async function loadBackupStatus() {
  try { const b = await api.get("/api/backups"); $("#backup-status").textContent = b.length ? `Last backup: ${fmtWhenIso(b[0].created)}` : "No backups yet"; } catch {}
}

/* ---------------- render router ---------------- */
function render() {
  $("#view-add").hidden = state.view !== "add";
  $("#view-calendar").hidden = state.view !== "calendar";
  document.querySelectorAll(".navlink").forEach((n) => n.classList.toggle("active", n.dataset.view === state.view));
  if (state.view === "add") renderRecent(); else renderCalendar();
}

/* ---------------- Add view: recently added ---------------- */
function renderRecent() {
  const list = $("#recent-list");
  const jobs = [...state.jobs].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")).slice(0, 8);
  $("#recent-empty").hidden = jobs.length !== 0;
  list.hidden = jobs.length === 0;
  list.innerHTML = "";
  for (const j of jobs) {
    const date = isoToDate(j.created_at);
    const b = document.createElement("button");
    b.className = "job-row";
    b.onclick = () => openDrawer(j.id);
    b.innerHTML = `${favBadge(j)}
      <span class="job-main">
        <span class="job-title">${esc(j.title || "Untitled role")}</span>
        <span class="job-meta">${esc(srcLabel(j.source))}<span class="sep">·</span><span class="st st-${j.status}">${cap(j.status)}</span>${j.company ? `<span class="sep">·</span>${esc(j.company)}` : ""}</span>
      </span>
      <span class="job-right"><span>${date ? fmtShort(date) : ""}</span><span class="chev">${svg("chev", 18)}</span></span>`;
    list.appendChild(b);
  }
}

/* ---------------- Calendar view ---------------- */
function renderCalendar() {
  renderUpcoming();
  $("#cal-title").textContent = `${MONTHS[state.calCursor.getMonth()]} ${state.calCursor.getFullYear()}`;
  document.querySelectorAll(".seg-btn").forEach((s) => s.classList.toggle("active", s.dataset.mode === state.calMode));
  const body = $("#cal-body");
  if (state.calMode === "month") body.innerHTML = monthGrid();
  else if (state.calMode === "week") body.innerHTML = weekGrid();
  else body.innerHTML = listView();
  body.querySelectorAll("[data-job]").forEach((el) => { el.onclick = () => openDrawer(+el.dataset.job); });
}

function jobEvents(j) {
  const out = [];
  const a = isoToDate(j.date_applied); if (a) out.push({ job: j, date: a, kind: "applied", label: "Applied" });
  const f = isoToDate(j.follow_up_date); if (f) out.push({ job: j, date: f, kind: "follow", label: "Follow up" });
  return out;
}
function eventsOn(d) {
  const out = [];
  for (const j of state.jobs) for (const e of jobEvents(j)) if (sameDay(e.date, d)) out.push(e);
  return out;
}
function calEventChip(e) {
  return `<span class="cal-event ${e.kind}" data-job="${e.job.id}"><span class="ce-title">${esc(e.job.company || e.job.title || "Job")}</span><span class="ce-tag">${e.label}</span></span>`;
}

function monthGrid() {
  const cur = state.calCursor, today = new Date();
  const first = new Date(cur.getFullYear(), cur.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - first.getDay());
  let html = '<div class="cal-grid">' + DOW.map((d) => `<div class="cal-dow">${d}</div>`).join("");
  for (let i = 0; i < 42; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const out = d.getMonth() !== cur.getMonth();
    const events = eventsOn(d);
    const evs = events.slice(0, 3).map(calEventChip).join("");
    const more = events.length > 3 ? `<span class="cal-more">+${events.length - 3} more</span>` : "";
    html += `<div class="cal-cell${out ? " out" : ""}${sameDay(d, today) ? " today" : ""}"><span class="cal-daynum">${d.getDate()}</span>${evs}${more}</div>`;
  }
  return html + "</div>";
}

function weekGrid() {
  const cur = state.calCursor, today = new Date();
  const base = state.calMode === "week" ? today : cur;
  const start = new Date(base); start.setDate(base.getDate() - base.getDay());
  let html = '<div class="cal-week">';
  for (let i = 0; i < 7; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const evs = eventsOn(d).map(calEventChip).join("");
    html += `<div class="wk-col"><div class="wk-head${sameDay(d, today) ? " today" : ""}">${DOW[d.getDay()]} <span class="wk-num">${d.getDate()}</span></div>${evs}</div>`;
  }
  return html + "</div>";
}

function listView() {
  const evs = [];
  for (const j of state.jobs) for (const e of jobEvents(j)) evs.push(e);
  evs.sort((a, b) => b.date - a.date);
  if (!evs.length) return '<div class="empty"><p class="empty-title">No dated activity</p><p class="muted">Apply dates from your sheet will appear here.</p></div>';
  return '<div class="cal-listview">' + evs.map((e) => {
    const j = e.job;
    return `<div class="li-row" data-job="${j.id}"><span class="li-date">${e.date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })}</span>${favBadge(j)}<span class="job-main"><span class="job-title">${esc(j.title || j.company || "Job")}</span><span class="job-meta">${esc(j.company || srcLabel(j.source))}<span class="sep">·</span>${e.label}</span></span></div>`;
  }).join("") + "</div>";
}

function renderUpcoming() {
  const host = $("#upcoming"); host.innerHTML = "";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const cur = state.calCursor;
  const addLabel = (txt, count) => {
    const l = document.createElement("div"); l.className = "up-group-label";
    l.innerHTML = count != null ? `${esc(txt)} <span class="up-count">${count}</span>` : esc(txt);
    host.appendChild(l);
  };

  const followUps = state.jobs.filter((j) => { const d = isoToDate(j.follow_up_date); return d && d >= today; })
    .sort((a, b) => a.follow_up_date.localeCompare(b.follow_up_date));
  if (followUps.length) {
    addLabel("Upcoming follow-ups");
    followUps.forEach((j) => host.appendChild(upRow(j, "Follow up")));
  }

  const monthApps = state.jobs
    .filter((j) => { const d = isoToDate(j.date_applied); return d && d.getFullYear() === cur.getFullYear() && d.getMonth() === cur.getMonth(); })
    .sort((a, b) => b.date_applied.localeCompare(a.date_applied));
  if (monthApps.length) {
    addLabel(`Applied in ${MONTHS[cur.getMonth()]}`, monthApps.length);
    let lastDay = "";
    for (const j of monthApps.slice(0, 60)) {
      const d = isoToDate(j.date_applied);
      const dl = d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
      if (dl !== lastDay) { const dh = document.createElement("div"); dh.className = "up-day"; dh.textContent = dl; host.appendChild(dh); lastDay = dl; }
      host.appendChild(upRow(j, "Applied"));
    }
    if (monthApps.length > 60) addLabel(`+${monthApps.length - 60} more this month`);
  } else if (!followUps.length) {
    host.innerHTML = `<p class="muted" style="margin-bottom:18px">No applications in ${MONTHS[cur.getMonth()]} ${cur.getFullYear()}. Use the ‹ › arrows to browse other months.</p>`;
  }
}
function relLabel(d, today) {
  const diff = Math.round((d - today) / 86400000);
  if (diff <= 0) return "Today";
  if (diff === 1) return `Tomorrow · ${d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}`;
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}
function upRow(j, tag) {
  const b = document.createElement("button"); b.className = "up-row"; b.onclick = () => openDrawer(j.id);
  b.innerHTML = `${favBadge(j)}<span class="job-main"><span class="job-title">${esc(j.title || "Job")}</span><span class="job-meta">${esc(j.company || srcLabel(j.source))}<span class="sep">·</span>${esc(tag)}</span></span>`;
  return b;
}

/* ---------------- Detail drawer ---------------- */
function openDrawer(id) {
  const j = byId(id); if (!j) return;
  state.selectedId = id;
  const opts = state.statuses.map((s) => `<option value="${s}"${s === j.status ? " selected" : ""}>${cap(s)}</option>`).join("");
  const chips = [["Location", j.location], ["Salary", j.salary], ["Type", j.employment_type], ["Posted", (j.date_posted || "").slice(0, 10)]]
    .filter(([, v]) => v).map(([k, v]) => `<span class="chip"><b>${k}:</b> ${esc(v)}</span>`).join("");
  const d = $("#drawer");
  d.innerHTML = `
    <div class="drawer-head">
      <div><h2>${esc(j.title || "Untitled role")}</h2><p class="d-company">${esc(srcLabel(j.source))}${j.company ? " · " + esc(j.company) : ""}</p></div>
      <button class="icon-btn" id="drawer-close" aria-label="Close">${svg("x")}</button>
    </div>
    <div class="drawer-actions">
      ${j.url && j.url.startsWith("http") ? `<a class="btn-ghost" href="${esc(j.url)}" target="_blank" rel="noopener">Open original</a>` : ""}
      <button class="btn-ghost" id="d-md">Markdown</button>
      <button class="btn-danger" id="d-del">Delete</button>
    </div>
    ${chips ? `<div class="chips">${chips}</div>` : ""}
    <div class="d-label">Application</div>
    <div class="grid2">
      <div class="field"><label>Status</label><select id="f-status">${opts}</select></div>
      <div class="field"><label>Date applied</label><input type="date" id="f-applied" value="${esc((j.date_applied || "").slice(0,10))}"></div>
      <div class="field"><label>Follow-up</label><input type="date" id="f-follow" value="${esc((j.follow_up_date || "").slice(0,10))}"></div>
      <div class="field"><label>Salary expectation</label><input type="text" id="f-salexp" value="${esc(j.salary_expectation || "")}" placeholder="$85,000"></div>
      <div class="field"><label>Contact</label><input type="text" id="f-contact" value="${esc(j.contact || "")}" placeholder="Recruiter / email"></div>
      <div class="field"><label>Interest</label><div class="stars" id="f-stars"></div></div>
    </div>
    <div class="d-label">Documents</div>
    <div class="files">
      <div class="file-slot" data-kind="resume"><label style="font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.04em;font-weight:600">Resume</label><div class="file-row" data-row="resume"></div></div>
      <div class="file-slot" data-kind="cover_letter"><label style="font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.04em;font-weight:600">Cover letter</label><div class="file-row" data-row="cover_letter"></div></div>
    </div>
    <div class="field" style="margin-top:18px"><label>Notes</label><textarea id="f-notes" rows="4" placeholder="Interview prep, links, reminders…">${esc(j.notes || "")}</textarea></div>
    <details class="desc"><summary>Job description</summary><div class="markdown" id="d-desc"></div></details>
  `;
  d.hidden = false; $("#scrim").hidden = false; paintIcons(d);

  $("#drawer-close").onclick = closeDrawer;
  $("#d-md").onclick = () => window.open(`/api/jobs/${id}/markdown`, "_blank");
  $("#d-del").onclick = () => removeJob(id, j.title);
  $("#f-status").onchange = (ev) => patch(id, { status: ev.target.value });
  $("#f-applied").onchange = (ev) => patch(id, { date_applied: ev.target.value });
  $("#f-follow").onchange = (ev) => patch(id, { follow_up_date: ev.target.value });
  $("#f-salexp").onblur = (ev) => patch(id, { salary_expectation: ev.target.value.trim() });
  $("#f-contact").onblur = (ev) => patch(id, { contact: ev.target.value.trim() });
  $("#f-notes").onblur = (ev) => patch(id, { notes: ev.target.value.trim() });
  renderStars(id, j.rating || 0);
  renderFiles(id, j);
  $("#d-desc").innerHTML = mdToHtml(j.description_md || "_No description captured._");
}
function closeDrawer() { $("#drawer").hidden = true; $("#scrim").hidden = true; state.selectedId = null; }
function renderStars(id, cur) {
  const box = $("#f-stars"); box.innerHTML = "";
  for (let i = 1; i <= 5; i++) { const s = document.createElement("span"); s.className = "star" + (i <= cur ? " on" : ""); s.textContent = "★"; s.onclick = () => patch(id, { rating: i === cur ? 0 : i }); box.appendChild(s); }
}
function renderFiles(id, j) {
  for (const kind of ["resume", "cover_letter"]) {
    const row = $(`[data-row="${kind}"]`); const name = j[`${kind}_name`]; row.innerHTML = "";
    if (name) {
      row.innerHTML = `<span class="file-name">${esc(name)}</span>`;
      const dl = mkBtn("download", () => window.open(`/api/jobs/${id}/file?kind=${kind}`, "_blank"));
      const rm = mkBtn("remove", () => removeFile(id, kind)); row.append(dl, rm);
    } else {
      const lbl = document.createElement("label"); lbl.className = "upload-label"; lbl.textContent = "Attach file";
      const inp = document.createElement("input"); inp.type = "file"; inp.onchange = () => inp.files[0] && uploadFile(id, kind, inp.files[0]);
      lbl.appendChild(inp); row.appendChild(lbl);
    }
  }
}
function mkBtn(t, fn) { const b = document.createElement("button"); b.className = "link-btn"; b.textContent = t; b.onclick = fn; return b; }

/* ---------------- mutations ---------------- */
async function addJob(url) {
  const btn = $("#add-btn"); btn.disabled = true; btn.textContent = "Fetching…";
  try { const j = await api.send("POST", "/api/jobs", { url }); $("#add-url").value = ""; await loadAll(); toast(`Saved “${j.title || "job"}”.`); openDrawer(j.id); }
  catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; btn.textContent = "Save job"; }
}
async function patch(id, fields) {
  try { const u = await api.send("PATCH", `/api/jobs/${id}`, fields); Object.assign(byId(id), u); render(); if (!$("#drawer").hidden && state.selectedId === id) { /* keep drawer values */ } }
  catch (err) { toast(err.message, true); }
}
async function removeJob(id, title) {
  try { await api.send("DELETE", `/api/jobs/${id}`); closeDrawer(); await loadAll(); toastUndo(`Moved “${title || "job"}” to Trash.`, () => restoreJob(id)); }
  catch (err) { toast(err.message, true); }
}
async function restoreJob(id) { try { await api.send("POST", `/api/jobs/${id}/restore`); await loadAll(); toast("Restored."); } catch (err) { toast(err.message, true); } }
async function purgeJob(id, title) {
  if (!confirm(`Permanently delete “${title || "this job"}” and its files? A backup is kept, but this can't be undone.`)) return;
  try { await api.send("DELETE", `/api/jobs/${id}?purge=1`); await loadAll(); renderTrash(); toast("Permanently deleted."); } catch (err) { toast(err.message, true); }
}
function uploadFile(id, kind, file) {
  const r = new FileReader();
  r.onload = async () => { try { const u = await api.send("POST", `/api/jobs/${id}/file`, { kind, filename: file.name, content_b64: r.result.split(",")[1] }); Object.assign(byId(id), u); openDrawer(id); toast("Attached."); } catch (err) { toast(err.message, true); } };
  r.readAsDataURL(file);
}
async function removeFile(id, kind) { try { const u = await api.send("DELETE", `/api/jobs/${id}/file?kind=${kind}`); Object.assign(byId(id), u); openDrawer(id); } catch (err) { toast(err.message, true); } }

/* ---------------- Data menu ---------------- */
function toggleMenu(open) { const m = $("#data-menu"); const show = open ?? m.hidden; m.hidden = !show; $("#data-btn").setAttribute("aria-expanded", String(show)); }
function exportBackup() {
  const a = document.createElement("a");
  a.href = "/api/export"; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  toast("Notebook exported.");
}
async function backupNow() { try { await api.send("POST", "/api/backup", {}); loadBackupStatus(); toast("Backup saved."); } catch (err) { toast(err.message, true); } }
function importBackup(file) {
  const r = new FileReader();
  r.onload = async () => { let data; try { data = JSON.parse(r.result); } catch { return toast("Not valid JSON.", true); } try { const res = await api.send("POST", "/api/import", data); await loadAll(); toast(`Imported ${res.added}; skipped ${res.skipped}.`); } catch (err) { toast(err.message, true); } };
  r.readAsText(file);
}
function setAppearance(mode) {
  document.body.className = "ui-" + mode;
  try { localStorage.setItem("jobtrail-appearance", mode); } catch {}
  document.querySelectorAll(".appearance").forEach((a) => a.classList.toggle("sel", a.dataset.appearance === mode));
}

/* ---------------- Trash modal ---------------- */
function openTrash() { renderTrash(); $("#trash-modal").hidden = false; }
function renderTrash() {
  const list = $("#trash-list"); list.innerHTML = ""; $("#trash-empty").hidden = state.trash.length !== 0; list.hidden = state.trash.length === 0;
  for (const j of state.trash) {
    const row = document.createElement("div"); row.className = "job-row"; row.style.cursor = "default";
    row.innerHTML = `${favBadge(j)}<span class="job-main"><span class="job-title">${esc(j.title || "Job")}</span><span class="job-meta">${esc(j.company || srcLabel(j.source))}<span class="sep">·</span>Trashed ${esc(fmtWhenIso(j.deleted_at))}</span></span>`;
    const acts = document.createElement("span"); acts.className = "trash-actions";
    const rest = document.createElement("button"); rest.className = "btn-ghost"; rest.textContent = "Restore"; rest.onclick = async () => { await restoreJob(j.id); renderTrash(); };
    const pur = document.createElement("button"); pur.className = "btn-danger"; pur.textContent = "Delete forever"; pur.onclick = () => purgeJob(j.id, j.title);
    acts.append(rest, pur); row.appendChild(acts); list.appendChild(row);
  }
}

/* ---------------- tiny markdown ---------------- */
function mdToHtml(md) {
  const lines = md.split("\n"); let html = "", inList = false;
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*]+?)\*/g, "$1<em>$2</em>").replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, ""); const h = line.match(/^(#{1,6})\s+(.*)$/); const li = line.match(/^[-*]\s+(.*)$/) || line.match(/^\d+\.\s+(.*)$/);
    if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(li[1])}</li>`; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    if (h) html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; else if (line.trim() === "---") html += "<hr/>"; else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>"; return html;
}

/* ---------------- boot ---------------- */
function boot() {
  paintIcons();
  try { setAppearance(localStorage.getItem("jobtrail-appearance") || "calm"); } catch { setAppearance("calm"); }
  if (location.hash.replace("#", "") === "calendar") state.view = "calendar";

  document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
    state.view = b.dataset.view; location.hash = state.view === "calendar" ? "calendar" : "";
    render();
  }));
  $("#add-form").addEventListener("submit", (ev) => { ev.preventDefault(); const u = $("#add-url").value.trim(); if (u) addJob(u); });

  $("#data-btn").addEventListener("click", (ev) => { ev.stopPropagation(); toggleMenu(); });
  document.addEventListener("click", (ev) => { if (!ev.target.closest(".data-wrap")) toggleMenu(false); });
  $("#data-menu").addEventListener("click", (ev) => {
    const item = ev.target.closest("[data-act], .appearance"); if (!item) return;
    if (item.dataset.appearance) { setAppearance(item.dataset.appearance); return; }
    toggleMenu(false);
    const act = item.dataset.act;
    if (act === "backup") backupNow(); else if (act === "export") exportBackup(); else if (act === "trash") openTrash();
  });
  $("#import-file").addEventListener("change", (ev) => { if (ev.target.files[0]) { importBackup(ev.target.files[0]); ev.target.value = ""; toggleMenu(false); } });

  $("#cal-prev").addEventListener("click", () => { state.calCursor = new Date(state.calCursor.getFullYear(), state.calCursor.getMonth() - 1, 1); renderCalendar(); });
  $("#cal-next").addEventListener("click", () => { state.calCursor = new Date(state.calCursor.getFullYear(), state.calCursor.getMonth() + 1, 1); renderCalendar(); });
  $("#cal-today").addEventListener("click", () => { state.calCursor = startOfMonth(new Date()); renderCalendar(); });
  document.querySelectorAll(".seg-btn").forEach((s) => s.addEventListener("click", () => { state.calMode = s.dataset.mode; renderCalendar(); }));

  $("#scrim").addEventListener("click", closeDrawer);
  $("#trash-close").addEventListener("click", () => { $("#trash-modal").hidden = true; });
  $("#trash-modal").addEventListener("click", (ev) => { if (ev.target.id === "trash-modal") $("#trash-modal").hidden = true; });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { closeDrawer(); $("#trash-modal").hidden = true; toggleMenu(false); } });

  loadAll().catch((err) => toast("Could not load: " + err.message, true));
}
boot();
