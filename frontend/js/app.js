/* Paperless AOT — SPA */
const API = "/api/v1";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => v == null ? "" :
  String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STATUS_META = {
  MATCHED: ["ok", "✓ Matched"],
  MATCHED_WITH_TOLERANCE: ["ok", "✓ Matched (tol.)"],
  PARTIAL_MATCH: ["warn", "△ Partial"],
  WAITING_FOR_FWB: ["pending", "◷ Waiting FWB"],
  WAITING_FOR_FHL: ["pending", "◷ Waiting FHL"],
  MULTIPLE_HOUSES: ["info", "▤ Multi-house"],
  DUPLICATE: ["warn", "⧉ Duplicate"],
  INVALID_FORMAT: ["err", "✕ Invalid"],
  PARSE_ERROR: ["err", "✕ Parse error"],
  NEEDS_REVIEW: ["warn", "👁 Needs review"],
  RESOLVED: ["ok", "✓ Resolved"],
  REJECTED: ["err", "✕ Rejected"],
  PARSED: ["ok", "✓ Parsed"],
};
const badge = (st) => {
  const [cls, label] = STATUS_META[st] || ["muted", st || "—"];
  return `<span class="badge ${cls}">${esc(label)}</span>`;
};
const fmtW = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
const fmtD = (v) => v ? v.replace("T", " ").slice(0, 16) : "—";

let CURRENT_USER = null;
const isAdmin = () => CURRENT_USER?.role === "ADMINISTRATOR";
const canImport = () => ["ADMINISTRATOR", "OPERATOR"].includes(CURRENT_USER?.role);

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (res.status === 401 && CURRENT_USER) { showLogin("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.code || res.statusText);
  return data;
}
const jsonPost = (body) => ({
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- router ---------------- */
const routes = {
  dashboard: renderDashboard, import: renderImport, matches: renderMatches,
  rawdata: renderRawData, errors: renderErrors, history: renderHistory,
  audit: renderAudit, settings: renderSettings, do: renderDeliveryOrders,
  users: renderUsers,
};
const titles = {
  dashboard: "Dashboard", import: "Import Messages", matches: "Match Results",
  rawdata: "Raw Data / Analysis", errors: "Errors", history: "Match History",
  audit: "Audit Log", settings: "Settings", do: "Delivery Orders",
  users: "Users",
};

function navigate() {
  if (!CURRENT_USER) return;
  closeModal();   // a detail modal must not survive a route change
  const hash = location.hash.replace(/^#\//, "") || "dashboard";
  const [route, qs] = hash.split("?");
  const link = $(`.nav a[data-route="${route}"]`);
  if (link && link.hidden) {
    $("#view").innerHTML =
      `<div class="empty"><div class="big">🔒</div>บทบาท ${esc(CURRENT_USER.role)} ไม่มีสิทธิ์เข้าหน้านี้</div>`;
    $("#page-title").textContent = "ไม่มีสิทธิ์";
    return;
  }
  const fn = routes[route] || renderDashboard;
  $$(".nav a").forEach(a => a.classList.toggle("active", a.dataset.route === route));
  $("#page-title").textContent = titles[route] || "Dashboard";
  fn(new URLSearchParams(qs || ""));
}
window.addEventListener("hashchange", navigate);

$("#global-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.value.trim()) {
    location.hash = `#/matches?search=${encodeURIComponent(e.target.value.trim())}`;
  }
});

/* ---------------- dashboard ---------------- */
const DONUT_COLORS = {
  MATCHED: "#1e8e5a", MATCHED_WITH_TOLERANCE: "#63b98a", PARTIAL_MATCH: "#e0a52e",
  NEEDS_REVIEW: "#b76e00", WAITING_FOR_FWB: "#6554c0", WAITING_FOR_FHL: "#8d80d8",
  DUPLICATE: "#d98b2b", INVALID_FORMAT: "#c0392b", PARSE_ERROR: "#e26a5a",
};

async function renderDashboard() {
  const v = $("#view");
  v.innerHTML = `<div class="empty">Loading…</div>`;
  let s;
  try { s = await api("/dashboard/summary"); }
  catch (e) { v.innerHTML = `<div class="empty">โหลดข้อมูลไม่สำเร็จ: ${esc(e.message)}</div>`; return; }

  const cards = [
    ["Imported Today", s.importedToday, "accent-navy", "⇪", "#/rawdata?table=cargo_messages"],
    ["Matched", s.matched, "accent-ok", "✓", "#/matches?status=MATCHED,MATCHED_WITH_TOLERANCE"],
    ["Waiting", s.waiting, "accent-pending", "◷", "#/matches?status=WAITING_FOR_FWB,WAITING_FOR_FHL"],
    ["Partial / Review", s.partial, "accent-warn", "△", "#/matches?status=PARTIAL_MATCH,NEEDS_REVIEW"],
    ["Errors", s.errors, "accent-err", "✕", "#/rawdata?table=cargo_messages&f=parse_status:eq:PARSE_ERROR"],
    ["Duplicates", s.duplicates, "accent-info", "⧉", "#/rawdata?table=cargo_messages&f=parse_status:eq:DUPLICATE"],
  ];

  const statusEntries = Object.entries(s.statusCounts || {});
  const totalStatus = statusEntries.reduce((a, [, c]) => a + c, 0) || 1;

  v.innerHTML = `
    <div class="cards">${cards.map(([l, val, cls, ic, href]) => `
      <div class="stat-card ${cls}" onclick="location.hash='${href}'">
        <span class="icon">${ic}</span>
        <div class="label">${l}</div><div class="value">${val ?? 0}</div>
      </div>`).join("")}
    </div>
    <div class="grid-2">
      <div class="panel">
        <h2>Match Status Distribution</h2>
        <div class="chart-flex">
          <svg id="donut" width="180" height="180" viewBox="0 0 42 42"></svg>
          <div class="legend">${statusEntries.length ? statusEntries.map(([st, c]) => `
            <div class="row"><span class="dot" style="background:${DONUT_COLORS[st] || "#8fa3c8"}"></span>
              ${esc(st)} <b style="margin-left:auto">${c}</b></div>`).join("") :
            '<span class="muted" style="color:var(--muted)">ยังไม่มีข้อมูล — import ไฟล์ก่อน</span>'}
          </div>
        </div>
        <div class="section-title"><h3>Messages by Type</h3></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${Object.entries(s.typeCounts || {}).map(([t, c]) =>
            `<span class="badge info">${esc(t)} · ${c}</span>`).join("") || "—"}
        </div>
      </div>
      <div class="panel">
        <h2>Imports (last 14 days)</h2>
        <div class="bars">${(s.importsByDay || []).map(d => {
          const max = Math.max(...s.importsByDay.map(x => x.c), 1);
          return `<div class="bar-col"><span class="bv">${d.c}</span>
            <div class="bar" style="height:${Math.round(d.c / max * 120)}px"></div>
            <span class="bl">${d.day.slice(5)}</span></div>`;
        }).join("") || '<div class="empty">ยังไม่มีการ import</div>'}</div>
        <div class="section-title"><h3>Recent Match Activity</h3>
          <a class="btn sm" href="#/matches">ดูทั้งหมด →</a></div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>MAWB</th><th>Status</th><th class="num">Score</th><th class="num">FHL</th><th>Last Matched</th></tr></thead>
          <tbody>${(s.recent || []).map(r => `
            <tr class="clickable" onclick="openDetail('${esc(r.mawb_number)}')">
              <td class="mono"><b>${esc(r.mawb_number)}</b></td>
              <td>${badge(r.match_status)}</td>
              <td class="num"><span class="score-pill">${r.match_score}</span></td>
              <td class="num">${r.fhl_count}</td><td>${fmtD(r.last_matched_at)}</td></tr>`).join("") ||
            '<tr><td colspan="5" class="empty">ยังไม่มีผลการจับคู่</td></tr>'}
          </tbody></table></div>
      </div>
    </div>`;

  // donut
  const svg = $("#donut");
  let offset = 25;
  svg.innerHTML = `<circle cx="21" cy="21" r="15.9" fill="none" stroke="#edf0f7" stroke-width="6"></circle>` +
    statusEntries.map(([st, c]) => {
      const pct = c / totalStatus * 100;
      const seg = `<circle cx="21" cy="21" r="15.9" fill="none"
        stroke="${DONUT_COLORS[st] || "#8fa3c8"}" stroke-width="6"
        stroke-dasharray="${pct} ${100 - pct}" stroke-dashoffset="${offset}"></circle>`;
      offset -= pct;
      return seg;
    }).join("") +
    `<text x="21" y="20" text-anchor="middle" font-size="7" font-weight="800" fill="#172b4d">${totalStatus === 1 && !statusEntries.length ? 0 : statusEntries.reduce((a, [, c]) => a + c, 0)}</text>
     <text x="21" y="27" text-anchor="middle" font-size="3.2" fill="#6b7a99">MAWB</text>`;
}

/* ---------------- import ---------------- */
let importQueue = [];

function renderImport() {
  importQueue = [];
  $("#view").innerHTML = `
    <div class="panel">
      <div class="tabs">
        <button class="active" data-tab="upload">Upload Files</button>
        <button data-tab="paste">Paste Text</button>
      </div>
      <div id="tab-upload">
        <div class="dropzone" id="dz">
          <div class="big">🛫</div>
          <div><b>ลากไฟล์มาวางที่นี่</b> หรือคลิกเพื่อเลือกไฟล์</div>
          <div style="font-size:.78rem;margin-top:6px">รองรับ .txt (Cargo-IMP: FWB, FHL, FFM, FSU) — เลือกได้หลายไฟล์</div>
          <input type="file" id="file-input" multiple accept=".txt,text/plain" hidden>
        </div>
        <div class="queue" id="queue"></div>
        <div style="margin-top:16px;display:flex;gap:10px">
          <button class="btn gold" id="btn-import" disabled>⇪ Import &amp; Match</button>
          <button class="btn" id="btn-clear">Clear</button>
        </div>
      </div>
      <div id="tab-paste" style="display:none">
        <textarea class="paste" id="paste-area" placeholder="FWB/16&#10;217-08722685HKGBKK/T1K149.0&#10;..."></textarea>
        <div style="margin-top:14px"><button class="btn gold" id="btn-paste">⇪ Import Text</button></div>
      </div>
      <div id="import-results"></div>
    </div>`;

  $$(".tabs button").forEach(b => b.onclick = () => {
    $$(".tabs button").forEach(x => x.classList.toggle("active", x === b));
    $("#tab-upload").style.display = b.dataset.tab === "upload" ? "" : "none";
    $("#tab-paste").style.display = b.dataset.tab === "paste" ? "" : "none";
  });

  const dz = $("#dz"), fi = $("#file-input");
  dz.onclick = () => fi.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("drag"); };
  dz.ondragleave = () => dz.classList.remove("drag");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("drag"); addFiles(e.dataTransfer.files); };
  fi.onchange = () => addFiles(fi.files);
  $("#btn-clear").onclick = () => { importQueue = []; drawQueue(); };
  $("#btn-import").onclick = doImport;
  $("#btn-paste").onclick = doPaste;
}

function addFiles(list) {
  for (const f of list) importQueue.push(f);
  drawQueue();
}
function drawQueue() {
  $("#queue").innerHTML = importQueue.map((f, i) => `
    <div class="queue-item"><span>📄</span>
      <span class="fname">${esc(f.name)}</span>
      <span style="color:var(--muted);font-size:.78rem">${(f.size / 1024).toFixed(1)} KB</span>
      <button class="btn sm" onclick="removeQueued(${i})">✕</button></div>`).join("");
  $("#btn-import").disabled = !importQueue.length;
}
window.removeQueued = (i) => { importQueue.splice(i, 1); drawQueue(); };

async function doImport() {
  const fd = new FormData();
  importQueue.forEach(f => fd.append("files", f));
  $("#btn-import").disabled = true;
  try {
    const res = await api("/imports/files", { method: "POST", body: fd });
    showImportResults(res);
    toast(`Batch ${res.batchNo}: import ${res.totalFiles} ไฟล์สำเร็จ`);
    importQueue = []; drawQueue();
  } catch (e) { toast("Import ล้มเหลว: " + e.message, true); }
  $("#btn-import").disabled = !importQueue.length;
}
async function doPaste() {
  const raw = $("#paste-area").value.trim();
  if (!raw) return;
  try {
    const res = await api("/imports/text", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rawMessage: raw }),
    });
    showImportResults(res);
    toast(`Batch ${res.batchNo} imported`);
    $("#paste-area").value = "";
  } catch (e) { toast("Import ล้มเหลว: " + e.message, true); }
}
function showImportResults(res) {
  $("#import-results").innerHTML = `
    <div class="section-title"><h3>ผลการ Import — ${esc(res.batchNo)}</h3></div>
    <div class="tbl-wrap"><table class="tbl">
      <thead><tr><th>File</th><th>Type</th><th>Status</th><th>MAWB</th><th>Error</th><th></th></tr></thead>
      <tbody>${res.results.map(r => `
        <tr><td>${esc(r.filename || "(pasted text)")}</td>
          <td>${r.messageType ? `<span class="badge info">${esc(r.messageType)}/${esc(r.version)}</span>` : "—"}</td>
          <td>${badge(r.status)}</td>
          <td class="mono">${(r.mawbNumbers || []).map(esc).join(", ") || "—"}</td>
          <td style="color:var(--err);font-size:.8rem">${esc(r.errorMessage || "")}</td>
          <td>${(r.mawbNumbers || [])[0]
            ? `<button class="btn sm" onclick="openDetail('${esc(r.mawbNumbers[0])}')">${
                r.status === "DUPLICATE" ? "ดูรายการเดิม" : "View match"}</button>`
            : ""}</td>
        </tr>`).join("")}
      </tbody></table></div>`;
}

/* ---------------- matches ---------------- */
async function renderMatches(params) {
  const state = {
    search: params.get("search") || "", status: params.get("status") || "",
    origin: "", destination: "", airlinePrefix: "", flight: "", version: "",
    duplicate: "", dateFrom: "", dateTo: "", reviewed: "", page: 1,
  };
  const v = $("#view");
  v.innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <input type="search" id="m-search" placeholder="MAWB / HAWB / Shipper / Flight / Filename / Batch…" value="${esc(state.search)}" style="width:300px">
        <select id="m-status">
          <option value="">ทุกสถานะ</option>
          ${Object.keys(STATUS_META).filter(s => s !== "PARSED").map(s =>
            `<option value="${s}" ${state.status === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <input type="text" id="m-origin" placeholder="Origin" style="width:96px" maxlength="3">
        <input type="text" id="m-dest" placeholder="Dest" style="width:96px" maxlength="3">
        <button class="btn sm" id="m-more">⋯ ตัวกรองเพิ่ม</button>
        <button class="btn primary sm" id="m-apply">Apply</button>
        <div class="spacer"></div>
        <button class="btn sm" id="m-export">⇓ Export</button>
      </div>
      <div class="filter-bar" id="m-more-bar" style="display:none">
        <input type="text" id="m-prefix" placeholder="Airline prefix เช่น 217" style="width:170px" maxlength="3">
        <input type="text" id="m-flight" placeholder="Flight เช่น TG601" style="width:150px">
        <input type="text" id="m-version" placeholder="FWB version" style="width:130px">
        <select id="m-duplicate">
          <option value="">Duplicate: ทั้งหมด</option>
          <option value="true">มี duplicate</option><option value="false">ไม่มี duplicate</option>
        </select>
        <select id="m-reviewed">
          <option value="">Reviewed: ทั้งหมด</option>
          <option value="true">Reviewed</option><option value="false">Unreviewed</option>
        </select>
        <label style="font-size:.82rem;color:var(--muted)">Matched</label>
        <input type="date" id="m-from" style="width:150px">
        <input type="date" id="m-to" style="width:150px">
      </div>
      <div id="m-table"></div>
    </div>`;

  const collectFilters = () => {
    state.search = $("#m-search").value.trim();
    state.status = $("#m-status").value;
    state.origin = $("#m-origin").value.trim();
    state.destination = $("#m-dest").value.trim();
    state.airlinePrefix = $("#m-prefix").value.trim();
    state.flight = $("#m-flight").value.trim();
    state.version = $("#m-version").value.trim();
    state.duplicate = $("#m-duplicate").value;
    state.reviewed = $("#m-reviewed").value;
    state.dateFrom = $("#m-from").value;
    state.dateTo = $("#m-to").value;
  };

  async function load() {
    collectFilters();
    const q = new URLSearchParams({
      page: state.page, pageSize: 25, search: state.search, status: state.status,
      origin: state.origin, destination: state.destination,
      airlinePrefix: state.airlinePrefix, flight: state.flight,
      version: state.version, duplicate: state.duplicate,
      dateFrom: state.dateFrom, dateTo: state.dateTo, reviewed: state.reviewed,
    });
    let data;
    try { data = await api("/matches?" + q); }
    catch (e) { $("#m-table").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    $("#m-table").innerHTML = data.items.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr>
          <th>Status</th><th>MAWB</th><th>Route</th><th>Flight</th>
          <th class="num">FHL</th><th>HAWB</th>
          <th class="num">Pieces (FWB/FHL)</th><th class="num">Weight (FWB/FHL)</th>
          <th class="num">Δ Weight</th><th class="num">Score</th><th>Reviewed</th><th>Last Matched</th>
        </tr></thead>
        <tbody>${data.items.map(r => `
          <tr class="clickable" onclick="openDetail('${esc(r.mawb_number)}')">
            <td>${badge(r.effective_status || r.match_status)}${
              r.override_status ? ' <span class="badge muted" title="กำหนดโดยผู้ดูแล">manual</span>' : ""}</td>
            <td class="mono"><b>${esc(r.mawb_number)}</b></td>
            <td>${r.origin ? esc(r.origin) + "→" + esc(r.destination) : "—"}</td>
            <td>${esc(r.flight_number || "—")}</td>
            <td class="num">${r.fhl_count}</td>
            <td class="mono" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(r.hawb_numbers || "—")}</td>
            <td class="num">${r.fwb_pieces ?? "?"} / ${r.fhl_total_pieces ?? "?"}</td>
            <td class="num">${fmtW(r.fwb_weight)} / ${fmtW(r.fhl_total_weight)}</td>
            <td class="num">${fmtW(r.weight_difference)}</td>
            <td class="num"><span class="score-pill">${r.match_score}</span></td>
            <td>${r.reviewed ? '<span class="badge ok">✓</span>' : '<span class="badge muted">—</span>'}</td>
            <td>${fmtD(r.last_matched_at)}</td>
          </tr>`).join("")}
        </tbody></table></div>
      <div class="pager">
        <span>${data.total} รายการ</span>
        <button class="btn sm" id="pg-prev" ${state.page <= 1 ? "disabled" : ""}>←</button>
        <span>หน้า ${state.page}</span>
        <button class="btn sm" id="pg-next" ${state.page * 25 >= data.total ? "disabled" : ""}>→</button>
      </div>` :
      `<div class="empty"><div class="big">🗂</div>ไม่พบผลการจับคู่ — ลอง import ไฟล์ที่หน้า Import</div>`;
    const prev = $("#pg-prev"), next = $("#pg-next");
    if (prev) prev.onclick = () => { state.page--; load(); };
    if (next) next.onclick = () => { state.page++; load(); };
  }
  $("#m-apply").onclick = () => { state.page = 1; load(); };
  $("#m-search").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; load(); } };
  $("#m-more").onclick = () => {
    const bar = $("#m-more-bar");
    bar.style.display = bar.style.display === "none" ? "flex" : "none";
  };
  $("#m-export").onclick = () => {
    collectFilters();
    openExportMenu({
      status: state.status, dateFrom: state.dateFrom, dateTo: state.dateTo,
      search: state.search,
    });
  };
  load();
}

/* ---------------- export menu ---------------- */
const EXPORT_CHOICES = [
  ["XLSX", "Excel (.xlsx)", "6 sheet: Summary, FWB, FHL, Validation Results, Errors, Audit Log"],
  ["CSV", "CSV", "หนึ่งบรรทัดต่อ MAWB (สรุปผลการจับคู่)"],
  ["JSON", "JSON", "ทุก section ในไฟล์เดียว เหมาะกับการนำไปประมวลผลต่อ"],
  ["RAW", "Raw Package (.zip)", "ไฟล์ข้อความต้นฉบับแยกตาม MAWB พร้อม manifest.json"],
];

window.openExportMenu = (filters) => {
  const active = Object.entries(filters).filter(([, v]) => v);
  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this)closeModal()">
      <div class="modal" style="max-width:620px">
        <div class="modal-head"><h2>Export รายงาน</h2>
          <button class="close" onclick="closeModal()">✕</button></div>
        <div class="modal-body">
          <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">
            ใช้ตัวกรองเดียวกับหน้าจอปัจจุบัน${active.length
              ? `: ${active.map(([k, v]) => `<b>${esc(k)}</b>=${esc(v)}`).join(" · ")}`
              : " (ไม่มีตัวกรอง — ส่งออกทั้งหมด)"}
          </p>
          <div class="export-grid">${EXPORT_CHOICES.map(([fmt, name, desc]) => `
            <button class="export-choice" onclick="runExport('${fmt}')">
              <b>${esc(name)}</b><span>${esc(desc)}</span></button>`).join("")}
          </div>
        </div></div></div>`;
  window.__exportFilters = filters;
};
window.runExport = (format) => {
  const q = new URLSearchParams({ format, ...window.__exportFilters });
  window.open(`${API}/exports?${q}`, "_blank");
  closeModal();
  toast(`กำลังดาวน์โหลด ${format}`);
};

/* ---------------- match detail modal ---------------- */
window.openDetail = async function (mawb) {
  let d;
  try { d = await api("/matches/" + encodeURIComponent(mawb)); }
  catch (e) { toast(e.message, true); return; }
  const r = d.result;
  const fwb = d.fwb;

  const tabs = ["Overview", "Houses", "Comparison", "Raw", "Parsed", "History"];
  const status = r.effective_status || r.match_status;
  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <div class="modal-head">
          <h2>MAWB <span class="mono">${esc(mawb)}</span></h2>
          ${badge(status)} <span class="score-pill" style="background:rgba(255,255,255,.15);color:#ffe9a8">${r.match_score}</span>
          ${r.override_status ? `<span class="badge muted" title="${esc(r.override_reason || "")}">ตั้งค่าโดย ${esc(r.override_by || "admin")}</span>` : ""}
          <div style="margin-left:14px;display:flex;gap:8px">
          ${isAdmin() ? `<button class="btn sm" onclick="doRematch('${esc(mawb)}')">↻ Re-match</button>` : ""}
          ${canImport() ? `<button class="btn sm" onclick="doReview('${esc(mawb)}')">${r.reviewed ? "✓ Reviewed" : "Mark reviewed"}</button>` : ""}
          ${isAdmin() ? `<button class="btn sm" onclick="doOverride('${esc(mawb)}')">⚑ Resolve / Reject</button>` : ""}
          </div>
          <button class="close" onclick="closeModal()">✕</button>
        </div>
        <div class="modal-body">
          <div class="tabs" id="d-tabs">${tabs.map((t, i) =>
            `<button class="${i === 0 ? "active" : ""}" data-t="${t}">${t}</button>`).join("")}</div>
          <div id="d-body"></div>
        </div>
      </div>
    </div>`;

  const body = $("#d-body");
  const render = {
    Overview: () => `
      <div class="kv">
        ${kv("Route", fwb ? `${fwb.origin} → ${fwb.destination}` : "—")}
        ${kv("Flight", fwb ? `${fwb.flight_number || "—"} / ${fwb.flight_date || ""}` : "—")}
        ${kv("FWB Pieces", r.fwb_pieces)} ${kv("FHL Total Pieces", r.fhl_total_pieces)}
        ${kv("FWB Weight", fmtW(r.fwb_weight) + " KG")} ${kv("FHL Total Weight", fmtW(r.fhl_total_weight) + " KG")}
        ${kv("Weight Diff", fmtW(r.weight_difference) + " KG")}
        ${kv("Nature of Goods", fwb?.nature_of_goods)}
        ${kv("Shipper (Master)", fwb?.shipper_name)} ${kv("Consignee (Master)", fwb?.consignee_name)}
        ${kv("Agent", fwb ? `${fwb.agent_name || ""} (${fwb.agent_code || "—"})` : "—")}
        ${kv("Issue", fwb ? `${fwb.issue_date || ""} ${fwb.issue_place || ""}` : "—")}
        ${kv("Freight Charge", fwb ? `${fmtW(fwb.freight_charge)} ${fwb.currency || ""}` : "—")}
        ${kv("Total Charge", fwb ? `${fmtW(fwb.total_charge)} ${fwb.currency || ""}` : "—")}
        ${kv("SPH Codes", fwb?.special_handling_codes ? JSON.parse(fwb.special_handling_codes || "[]").join(", ") : "—")}
        ${kv("Reviewed", r.reviewed ? `✓ ${r.reviewed_by || ""} ${fmtD(r.reviewed_at)}` : "ยังไม่ review")}
      </div>
      ${d.fsuEvents.length ? `
        <div class="section-title"><h3>Shipment Timeline (FSU)</h3></div>
        <div class="timeline">${d.fsuEvents.map(e => `
          <div class="tl-item"><div class="tl-dot"></div>
            <div class="tl-body"><b>${esc(e.status_code)}</b> @ ${esc(e.airport || "")}
              ${e.hawb_number ? `· HAWB <span class="mono">${esc(e.hawb_number)}</span>` : ""}
              <div class="muted">${esc(e.status_date || "")} ${esc(e.flight_number || "")}
                ${e.weight ? `· ${fmtW(e.weight)} ${esc(e.weight_unit || "")}` : ""}</div>
            </div></div>`).join("")}</div>` : ""}`,
    Houses: () => `
      ${d.houses.length ? `${canImport() && d.houses.length > 1 ? `
        <div class="filter-bar" style="margin-bottom:12px">
          <label class="cp-item"><input type="checkbox" id="hs-all"> เลือกทั้งหมด</label>
          <span id="hs-count" style="color:var(--muted);font-size:.83rem"></span>
          <div class="spacer"></div>
          <button class="btn gold sm" id="hs-combine" disabled
            onclick="openCombineDialog('${esc(mawb)}')">🧾 รวมเป็น DO ใบเดียว</button>
        </div>` : ""}
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr>${canImport() && d.houses.length > 1 ? "<th></th>" : ""}
          <th>HAWB</th><th>Link</th><th>Shipper</th><th>Consignee</th><th>Commodity</th>
          <th class="num">Pieces</th><th class="num">Weight</th><th>HS Code</th><th>Tax ID</th>
          <th></th></tr></thead>
        <tbody>${d.houses.map(h => `
          <tr>${canImport() && d.houses.length > 1
            ? `<td><input type="checkbox" class="hs-pick" value="${esc(h.id)}"
                 onclick="event.stopPropagation();updateCombineButton()"></td>` : ""}
            <td class="mono"><b>${esc(h.hawb_number)}</b></td>
            <td>${h.linked_by === "MANUAL"
              ? '<span class="badge warn">MANUAL</span>'
              : '<span class="badge muted">AUTO</span>'}</td>
            <td class="trunc" title="${esc(h.shipper_name || "")}">${esc(h.shipper_name || "—")}</td>
            <td class="trunc" title="${esc(h.consignee_name || "")}">${esc(h.consignee_name || "—")}</td>
            <td class="trunc">${esc(h.commodity || "—")}</td>
            <td class="num">${h.pieces ?? "—"}</td>
            <td class="num">${fmtW(h.gross_weight)} ${esc(h.weight_unit || "")}</td>
            <td class="mono">${esc(h.hs_code || "—")}</td>
            <td class="mono">${esc(h.consignee_tax_id || "—")}</td>
            <td style="white-space:nowrap">
              ${canImport() ? `<button class="btn gold sm" onclick="event.stopPropagation();openDoDialog('${esc(mawb)}','${esc(h.id)}','${esc(h.hawb_number)}')">🧾 สร้าง DO</button>` : ""}
              ${isAdmin() ? `<button class="btn sm" onclick="event.stopPropagation();doUnlink('${esc(mawb)}','${esc(h.id)}','${esc(h.hawb_number)}')">Unlink</button>` : ""}
            </td>
          </tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ยังไม่มี FHL สำหรับ MAWB นี้</div>`}
      ${d.unlinkedHouses?.length ? `
        <div class="section-title"><h3>House ที่ถูก Unlink ไว้</h3></div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>HAWB</th><th class="num">Pieces</th><th class="num">Weight</th>
            <th>เหตุผล</th><th>โดย</th>${isAdmin() ? "<th></th>" : ""}</tr></thead>
          <tbody>${d.unlinkedHouses.map(h => `<tr>
            <td class="mono">${esc(h.hawb_number)}</td>
            <td class="num">${h.pieces ?? "—"}</td>
            <td class="num">${fmtW(h.gross_weight)}</td>
            <td style="white-space:normal">${esc(h.reason || "—")}</td>
            <td>${esc(h.performed_by || "—")}</td>
            ${isAdmin() ? `<td><button class="btn sm" onclick="doClearLink('${esc(mawb)}','${esc(h.id)}')">คืนค่าอัตโนมัติ</button></td>` : ""}
          </tr>`).join("")}</tbody></table></div>` : ""}
      ${isAdmin() ? `<div style="margin-top:18px">
        <button class="btn gold" onclick="openLinkPicker('${esc(mawb)}')">+ Link house เข้ากับ MAWB นี้</button>
      </div>` : ""}`,
    Comparison: () => d.validations.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>Validation Rule</th><th>Severity</th><th>FWB Value</th>
          <th>FHL Aggregate</th><th>Difference</th><th>Result</th></tr></thead>
        <tbody>${d.validations.map(x => `
          <tr><td><b>${esc(x.rule_code)}</b></td>
            <td><span class="badge ${x.severity === "ERROR" ? "err" : "warn"}">${esc(x.severity)}</span></td>
            <td class="mono">${esc(x.fwb_value ?? "—")}</td><td class="mono">${esc(x.fhl_value ?? "—")}</td>
            <td class="mono">${esc(x.difference_value ?? "—")}</td>
            <td>${x.result === "PASS" ? '<span class="badge ok">PASS</span>' : '<span class="badge err">FAIL</span>'}</td>
          </tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ยังไม่มีผล validation (รอข้อมูลครบ)</div>`,
    Raw: () => d.rawMessages.map(m => `
      <div class="section-title"><h3>${esc(m.message_type)}/${esc(m.message_version)} —
        ${esc(m.original_filename || "pasted")} · ${badge(m.parse_status)}</h3>
        <button class="btn sm" onclick="navigator.clipboard.writeText(this.closest('div').nextElementSibling.textContent).then(()=>toastCopy())">⎘ Copy</button>
      </div>
      <pre class="raw">${esc(m.raw_message)}</pre>`).join("") || `<div class="empty">ไม่มีข้อความ</div>`,
    Parsed: () => `
      ${fwb ? `<div class="section-title"><h3>FWB Parsed</h3></div>
        <pre class="jsonview">${esc(JSON.stringify(JSON.parse(fwb.parsed_data || "{}"), null, 2))}</pre>` : ""}
      ${d.houses.map(h => `<div class="section-title"><h3>FHL ${esc(h.hawb_number)} Parsed</h3></div>
        <pre class="jsonview">${esc(JSON.stringify(JSON.parse(h.parsed_data || "{}"), null, 2))}</pre>`).join("")}`,
    History: () => d.history.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>Event</th><th>Status</th><th class="num">Score</th><th>By</th><th>At</th></tr></thead>
        <tbody>${d.history.map(h => `
          <tr><td><b>${esc(h.event_type)}</b></td>
            <td>${h.previous_status ? badge(h.previous_status) + " → " : ""}${badge(h.new_status)}</td>
            <td class="num">${h.previous_score ?? "—"} → ${h.new_score}</td>
            <td>${esc(h.performed_by || "—")}</td><td>${fmtD(h.performed_at)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ไม่มีประวัติ</div>`,
  };
  const show = (t) => {
    body.innerHTML = render[t]();
    const all = $("#hs-all");
    if (all) {
      all.onclick = () => {
        $$(".hs-pick").forEach(cb => { cb.checked = all.checked; });
        updateCombineButton();
      };
      updateCombineButton();
    }
  };
  $$("#d-tabs button").forEach(b => b.onclick = () => {
    $$("#d-tabs button").forEach(x => x.classList.toggle("active", x === b));
    show(b.dataset.t);
  });
  show("Overview");
};
const kv = (k, v) => `<div class="item"><div class="k">${esc(k)}</div><div class="v">${v ?? "—"}</div></div>`;
window.closeModal = () => {
  $("#modal-root").innerHTML = "";
  // Issuing a document changes the list underneath, so closing the result
  // has to redraw it however the modal was dismissed.
  if (window.__refreshOnClose) {
    window.__refreshOnClose = false;
    navigate();
  }
};
document.addEventListener("keydown", (e) => {
  // A forced password change has no close button, so Escape must not skip it.
  if (e.key === "Escape" && $("#modal-root").innerHTML
      && !CURRENT_USER?.mustChangePassword) closeModal();
});
window.toastCopy = () => toast("คัดลอกแล้ว");
window.doRematch = async (mawb) => {
  try {
    const r = await api(`/matches/${encodeURIComponent(mawb)}/rematch`, { method: "POST" });
    toast(`Re-match แล้ว: ${r.status} (score ${r.score})`);
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.doReview = async (mawb) => {
  const note = prompt("หมายเหตุการ review (ไม่บังคับ):");
  if (note === null) return;
  try {
    await api(`/matches/${encodeURIComponent(mawb)}/review`,
              jsonPost({ reviewed: true, note }));
    toast("Mark as reviewed แล้ว");
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.doOverride = async (mawb) => {
  const choice = prompt(
    "กำหนดสถานะเอง — พิมพ์ RESOLVED, REJECTED, NEEDS_REVIEW " +
    "หรือ CLEAR เพื่อกลับไปใช้ผลที่ระบบคำนวณ:");
  if (choice === null) return;
  const value = choice.trim().toUpperCase();
  const status = value === "CLEAR" ? null : value;
  const reason = prompt("เหตุผล (บันทึกลง audit log):") ?? "";
  try {
    await api(`/matches/${encodeURIComponent(mawb)}/status`,
              jsonPost({ status, reason }));
    toast(status ? `ตั้งสถานะเป็น ${status}` : "คืนค่าสถานะที่ระบบคำนวณแล้ว");
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.doUnlink = async (mawb, fhlId, hawb) => {
  const reason = prompt(`เหตุผลที่ unlink ${hawb} ออกจาก ${mawb}:`);
  if (reason === null) return;
  try {
    const r = await api(`/matches/${encodeURIComponent(mawb)}/houses/${fhlId}/unlink`,
                        jsonPost({ reason }));
    toast(`Unlink แล้ว — สถานะใหม่ ${r.status} (score ${r.score})`);
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.doClearLink = async (mawb, fhlId) => {
  try {
    await api(`/matches/${encodeURIComponent(mawb)}/houses/${fhlId}/link`,
              { method: "DELETE" });
    toast("คืนค่าการจับคู่อัตโนมัติแล้ว");
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.openLinkPicker = async (mawb) => {
  const render = (items) => `
    <div class="modal-back" onclick="if(event.target===this)openDetail('${esc(mawb)}')">
      <div class="modal" style="max-width:820px">
        <div class="modal-head"><h2>Link house เข้ากับ <span class="mono">${esc(mawb)}</span></h2>
          <button class="close" onclick="openDetail('${esc(mawb)}')">✕</button></div>
        <div class="modal-body">
          <div class="filter-bar">
            <input type="search" id="lp-search" placeholder="ค้นหา HAWB หรือ MAWB…" style="width:280px">
            <button class="btn primary sm" id="lp-go">ค้นหา</button>
          </div>
          <div class="tbl-wrap"><table class="tbl">
            <thead><tr><th>HAWB</th><th>MAWB เดิม</th><th class="num">Pieces</th>
              <th class="num">Weight</th><th>Commodity</th><th></th></tr></thead>
            <tbody>${items.map(h => `<tr>
              <td class="mono"><b>${esc(h.hawb_number)}</b></td>
              <td class="mono">${esc(h.mawb_number)}${h.mawb_number !== mawb
                ? ' <span class="badge warn">ต่าง MAWB</span>' : ""}</td>
              <td class="num">${h.pieces ?? "—"}</td>
              <td class="num">${fmtW(h.gross_weight)}</td>
              <td>${esc(h.commodity || "—")}</td>
              <td><button class="btn gold sm" onclick="doLink('${esc(mawb)}','${esc(h.id)}','${esc(h.hawb_number)}')">Link</button></td>
            </tr>`).join("") || `<tr><td colspan="6" class="empty">ไม่พบ house</td></tr>`}
            </tbody></table></div>
        </div></div></div>`;
  const load = async (search = "") => {
    const d = await api(`/houses/unassigned?${new URLSearchParams({ search })}`);
    $("#modal-root").innerHTML = render(d.items);
    $("#lp-go").onclick = () => load($("#lp-search").value.trim());
    $("#lp-search").onkeydown = (e) => { if (e.key === "Enter") load(e.target.value.trim()); };
    $("#lp-search").value = search;
  };
  try { await load(); } catch (e) { toast(e.message, true); }
};
/* ---------------- combined delivery order ---------------- */
window.updateCombineButton = () => {
  const picked = $$(".hs-pick").filter(cb => cb.checked);
  const btn = $("#hs-combine"), count = $("#hs-count");
  if (btn) btn.disabled = picked.length < 2;
  if (count) {
    count.textContent = picked.length
      ? `เลือกไว้ ${picked.length} house` + (picked.length < 2
          ? " — ต้องเลือกอย่างน้อย 2 ใบจึงจะรวมได้" : "")
      : "";
  }
};

window.openCombineDialog = (mawb, preset = null) => {
  // preset comes from the combinable worklist; otherwise use the ticked rows
  const ids = preset ? preset.ids : $$(".hs-pick").filter(c => c.checked).map(c => c.value);
  const label = preset ? preset.label : `${ids.length} house ของ ${mawb}`;
  const back = mawb ? `openDetail('${esc(mawb)}')` : "closeModal();navigate()";

  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this){${back}}">
      <div class="modal" style="max-width:680px">
        <div class="modal-head"><h2>รวมเป็น Delivery Order ใบเดียว</h2>
          <button class="close" onclick="${back}">✕</button></div>
        <div class="modal-body">
          <p style="font-size:.88rem;margin-bottom:14px">
            จะออก DO <b>1 ใบ</b> ที่ครอบคลุม <b>${esc(label)}</b>
            — ผู้รับปลายทางมารับของทั้งหมดด้วยเอกสารใบเดียว</p>
          <p style="color:var(--muted);font-size:.82rem;margin-bottom:16px">
            ทุก house ต้องมีปลายทางเดียวกันและเป็นผู้รับรายเดียวกัน
            วันหมดอายุจะนับจากเที่ยวบินที่ลงหลังสุด</p>
          <div class="settings-grid">
            <div class="setting-item"><div class="k">Landed on / ATA</div>
              <input type="datetime-local" id="cb-landed">
              <div class="hint">เว้นว่างไว้ = ใช้เวลาที่ลงหลังสุดจาก FSU</div></div>
            <div class="setting-item"><div class="k">Aircraft Registration</div>
              <input type="text" id="cb-acreg" placeholder="เว้นว่างได้"></div>
            <div class="setting-item"><div class="k">Customer Code</div>
              <input type="text" id="cb-cust" placeholder="เว้นว่างได้"></div>
            <div class="setting-item"><div class="k">Issued By</div>
              <input type="text" id="cb-issuer" placeholder="เช่น TG40441"></div>
          </div>
          <div class="setting-item" style="margin-top:14px">
            <div class="k">เหตุผล / หมายเหตุ</div>
            <input type="text" id="cb-reason" placeholder="บันทึกลง audit log">
          </div>
          ${isAdmin() ? `
            <label class="cp-item" style="margin-top:14px">
              <input type="checkbox" id="cb-force">
              ยืนยันว่าเป็นผู้รับรายเดียวกัน แม้ชื่อจะสะกดต่างกัน</label>
            <label class="cp-item" style="margin-top:8px">
              <input type="checkbox" id="cb-supersede">
              แทนที่ DO เดิมของ house เหล่านี้ (ใบเก่าจะกลายเป็น SUPERSEDED)</label>` : ""}
          <div style="margin-top:18px;display:flex;gap:10px;align-items:center">
            <button class="btn gold" id="cb-save">🧾 ออก DO รวม</button>
            <button class="btn" onclick="${back}">ยกเลิก</button>
          </div>
          <div id="cb-status" style="color:var(--err);font-size:.85rem;margin-top:12px;white-space:pre-wrap"></div>
        </div></div></div>`;

  $("#cb-save").onclick = async () => {
    $("#cb-status").style.color = "var(--muted)";
    $("#cb-status").textContent = "กำลังออกเอกสาร…";
    try {
      const r = await api("/do/combine", jsonPost({
        fhlIds: ids,
        landedAt: $("#cb-landed").value,
        aircraftRegistration: $("#cb-acreg").value.trim(),
        customerCode: $("#cb-cust").value.trim(),
        issuedBy: $("#cb-issuer").value.trim(),
        reason: $("#cb-reason").value.trim(),
        forceConsignee: $("#cb-force")?.checked || false,
        supersede: $("#cb-supersede")?.checked || false,
      }));
      showDoResult(mawb, r);
      toast(`ออก DO รวมเลขที่ ${r.doNumber} ครอบคลุม ${r.lines.length} house`);
    } catch (e) {
      $("#cb-status").style.color = "var(--err)";
      $("#cb-status").textContent = e.message;
    }
  };
};

window.togglePartFields = (maxPieces, maxWeight) => {
  const on = $("#do-part").checked;
  $("#do-part-fields").style.display = on ? "grid" : "none";
  if (on && !$("#do-pieces").value) {
    $("#do-pieces").value = maxPieces;
    $("#do-weight").value = maxWeight;
  }
};

/* ---------------- split a delivery order ---------------- */
window.openSplitDialog = async (doId, doNumber) => {
  let d;
  try { d = await api(`/do?search=${encodeURIComponent(doNumber)}`); }
  catch (e) { toast(e.message, true); return; }
  const row = d.items.find(i => i.do_number === doNumber);
  if (!row || row.line_count < 2) {
    toast("DO ใบนี้มี house เดียว แยกไม่ได้ — ถ้าจะปล่อยของบางส่วน ใช้ 'ออก DO บางส่วน'", true);
    return;
  }
  let lines;
  try { lines = (await api(`/data/delivery_order_lines?filter=do_id:eq:${doId}&pageSize=100`)).rows; }
  catch (e) { toast(e.message, true); return; }

  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this){closeModal();navigate()}">
      <div class="modal" style="max-width:720px">
        <div class="modal-head"><h2>แยก DO <span class="mono">${esc(doNumber)}</span></h2>
          <button class="close" onclick="closeModal();navigate()">✕</button></div>
        <div class="modal-body">
          <p style="font-size:.88rem;margin-bottom:6px">
            เลือกว่า house ใบไหนจะอยู่บนเอกสารใบใหม่ ใบที่เหลือจะไปอยู่อีกใบหนึ่ง</p>
          <p style="color:var(--muted);font-size:.82rem;margin-bottom:16px">
            DO เดิมจะกลายเป็น <b>SUPERSEDED</b> และระบบออกเลข DO ใหม่ให้ทั้งสองใบ
            เอกสารที่พิมพ์ออกไปแล้วยังอ่านย้อนหลังได้เหมือนเดิม</p>
          <div class="tbl-wrap"><table class="tbl">
            <thead><tr><th></th><th>HAWB</th><th>MAWB</th><th class="num">Pieces</th>
              <th class="num">Weight</th><th>Nature of Goods</th></tr></thead>
            <tbody>${lines.map(l => `<tr>
              <td><input type="checkbox" class="sp-pick" value="${esc(l.fhl_id)}"
                   onclick="updateSplitSummary()"></td>
              <td class="mono"><b>${esc(l.hawb_number)}</b></td>
              <td class="mono">${esc(l.mawb_number)}</td>
              <td class="num">${l.pieces ?? "—"}</td>
              <td class="num">${fmtW(l.weight)}</td>
              <td>${esc(l.nature_of_goods || "—")}</td></tr>`).join("")}
            </tbody></table></div>
          <div id="sp-summary" style="margin-top:14px;font-size:.85rem;color:var(--muted)"></div>
          <div class="setting-item" style="margin-top:14px">
            <div class="k">เหตุผล</div>
            <input type="text" id="sp-reason" placeholder="บันทึกลง audit log">
          </div>
          <div style="margin-top:18px;display:flex;gap:10px;align-items:center">
            <button class="btn gold" id="sp-save" disabled>✂ แยกเป็น 2 ใบ</button>
            <button class="btn" onclick="closeModal();navigate()">ยกเลิก</button>
          </div>
          <div id="sp-status" style="color:var(--err);font-size:.85rem;margin-top:12px;white-space:pre-wrap"></div>
        </div></div></div>`;

  window.__splitAll = lines.map(l => l.fhl_id);
  updateSplitSummary();

  $("#sp-save").onclick = async () => {
    const picked = $$(".sp-pick").filter(c => c.checked).map(c => c.value);
    const rest = window.__splitAll.filter(id => !picked.includes(id));
    $("#sp-status").style.color = "var(--muted)";
    $("#sp-status").textContent = "กำลังแยกเอกสาร…";
    try {
      const r = await api(`/do/${doId}/split`, jsonPost({
        groups: [picked, rest], reason: $("#sp-reason").value.trim(),
      }));
      closeModal();
      toast(`แยก DO ${r.splitFrom.doNumber} เป็น ` +
            r.documents.map(x => x.doNumber).join(" และ ") + " แล้ว");
      navigate();
    } catch (e) {
      $("#sp-status").style.color = "var(--err)";
      $("#sp-status").textContent = e.message;
    }
  };
};

window.updateSplitSummary = () => {
  const picked = $$(".sp-pick").filter(c => c.checked).length;
  const total = ($$(".sp-pick") || []).length;
  const rest = total - picked;
  const ok = picked > 0 && rest > 0;
  const btn = $("#sp-save");
  if (btn) btn.disabled = !ok;
  const summary = $("#sp-summary");
  if (summary) {
    summary.textContent = ok
      ? `ใบใหม่ที่ 1: ${picked} house · ใบใหม่ที่ 2: ${rest} house`
      : "เลือก house อย่างน้อย 1 ใบ และต้องเหลือไว้อีกอย่างน้อย 1 ใบ";
  }
};

/* ---------------- delivery order ---------------- */
window.openDoDialog = async (mawb, fhlId, hawb) => {
  // Prefill the ATA from the FSU arrival event when the message carried a time.
  let landed = "";
  try {
    const d = await api("/matches/" + encodeURIComponent(mawb));
    // An event carrying a clock time beats one that only has a date, whichever
    // arrived first — a DO needs the ATA to the minute.
    const byCode = (code) => d.fsuEvents.filter(e => e.status_code === code);
    const ranked = [...byCode("RCF"), ...byCode("ARR")];
    const arrival = ranked.find(e => e.status_time) || ranked[ranked.length - 1];
    if (arrival?.status_date) {
      const m = arrival.status_date.match(/^(\d{1,2})([A-Z]{3})(\d{2})$/);
      const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
      if (m) {
        const mm = String(months.indexOf(m[2]) + 1).padStart(2, "0");
        const t = arrival.status_time
          ? `${arrival.status_time.slice(0,2)}:${arrival.status_time.slice(2)}` : "00:00";
        landed = `20${m[3]}-${mm}-${m[1].padStart(2, "0")}T${t}`;
      }
    }
  } catch { /* the dialog still works without a prefill */ }

  let bal = null;
  try { bal = await api(`/do/houses/${fhlId}/balance`); } catch { /* optional */ }
  const partly = bal && bal.releasedPieces > 0;

  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this)openDetail('${esc(mawb)}')">
      <div class="modal" style="max-width:660px">
        <div class="modal-head"><h2>สร้าง Delivery Order — <span class="mono">${esc(hawb)}</span></h2>
          <button class="close" onclick="openDetail('${esc(mawb)}')">✕</button></div>
        <div class="modal-body">
          <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">
            ทุกช่องที่เหลือดึงจากข้อมูลที่ match มาอัตโนมัติ
            ช่องด้านล่างคือส่วนที่ข้อความ Cargo-IMP ไม่มีข้อมูลให้ กรอกเพิ่มได้ตามต้องการ
          </p>
          ${bal ? `<div class="balance-box">
            <b>ยอดของ House นี้</b> — ทั้งหมด ${bal.totalPieces} ชิ้น /
            ${fmtW(bal.totalWeight)}${esc(bal.weightUnit || "")}
            ${partly ? `· ปล่อยไปแล้ว ${bal.releasedPieces} ชิ้น /
              ${fmtW(bal.releasedWeight)} · <b>เหลือ ${bal.remainingPieces} ชิ้น /
              ${fmtW(bal.remainingWeight)}</b>` : "· ยังไม่ได้ปล่อยเลย"}
          </div>
          <label class="cp-item" style="margin-bottom:14px">
            <input type="checkbox" id="do-part" onclick="togglePartFields(${bal.remainingPieces}, ${bal.remainingWeight})">
            ปล่อยของบางส่วน (Part Delivery) — ที่เหลือเก็บไว้ออก DO ใบหลัง</label>
          <div class="settings-grid" id="do-part-fields" style="display:none;margin-bottom:14px">
            <div class="setting-item"><div class="k">จำนวนที่ปล่อยครั้งนี้ (ชิ้น)</div>
              <input type="number" id="do-pieces" min="1" max="${bal.remainingPieces}">
              <div class="hint">สูงสุด ${bal.remainingPieces} ชิ้น</div></div>
            <div class="setting-item"><div class="k">น้ำหนักที่ปล่อยครั้งนี้</div>
              <input type="number" id="do-weight" step="0.1" min="0.1" max="${bal.remainingWeight}">
              <div class="hint">สูงสุด ${fmtW(bal.remainingWeight)}${esc(bal.weightUnit || "")}</div></div>
          </div>` : ""}
          <div class="settings-grid">
            <div class="setting-item"><div class="k">Landed on / ATA</div>
              <input type="datetime-local" id="do-landed" value="${esc(landed)}">
              <div class="hint">${landed ? "ดึงจาก FSU มาให้แล้ว แก้ได้" : "FSU ไม่มีเวลามาให้ — กรอกเอง"}</div></div>
            <div class="setting-item"><div class="k">Aircraft Registration</div>
              <input type="text" id="do-acreg" placeholder="เช่น HSTKO">
              <div class="hint">พิมพ์ใต้หมายเลขเที่ยวบิน</div></div>
            <div class="setting-item"><div class="k">Customer Code</div>
              <input type="text" id="do-cust" placeholder="เว้นว่างได้">
              <div class="hint">รหัสลูกค้าที่มารับของ</div></div>
            <div class="setting-item"><div class="k">Issued By</div>
              <input type="text" id="do-issuer" placeholder="เช่น TG40441">
              <div class="hint">ถ้าเว้นว่างจะใช้ค่าจากหน้า Settings</div></div>
          </div>
          ${isAdmin() ? `<label class="cp-item" style="margin-top:16px">
            <input type="checkbox" id="do-amend">
            แก้ไข DO ที่ออกไปแล้ว (ใช้เลขเดิม เขียนทับข้อมูลด้วยค่าปัจจุบัน)</label>` : ""}
          <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
            <button class="btn gold" id="do-create">🧾 ออก DO</button>
            <button class="btn" onclick="openDetail('${esc(mawb)}')">ยกเลิก</button>
            <span id="do-status" style="color:var(--muted);font-size:.85rem"></span>
          </div>
        </div></div></div>`;

  $("#do-create").onclick = async () => {
    $("#do-status").textContent = "กำลังออกเอกสาร…";
    try {
      const r = await api(
        `/matches/${encodeURIComponent(mawb)}/houses/${fhlId}/do`,
        jsonPost({
          landedAt: $("#do-landed").value,
          aircraftRegistration: $("#do-acreg").value.trim(),
          customerCode: $("#do-cust").value.trim(),
          issuedBy: $("#do-issuer").value.trim(),
          amend: $("#do-amend")?.checked || false,
          releasePieces: $("#do-part")?.checked
            ? Number($("#do-pieces").value) || null : null,
          releaseWeight: $("#do-part")?.checked
            ? Number($("#do-weight").value) || null : null,
        }));
      showDoResult(mawb, r);
      toast(r.amended ? `แก้ไข DO ${r.doNumber} แล้ว (เลขเดิม)`
        : r.reprint ? `DO ${r.doNumber} มีอยู่แล้ว — เปิดเป็นการพิมพ์ซ้ำ`
        : `ออก DO เลขที่ ${r.doNumber} แล้ว`);
    } catch (e) { $("#do-status").textContent = ""; toast(e.message, true); }
  };
};

function showDoResult(mawb, r) {
  window.__refreshOnClose = !mawb;
  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this)openDetail('${esc(mawb)}')">
      <div class="modal" style="max-width:640px">
        <div class="modal-head"><h2>Delivery Order <span class="mono">${esc(r.doNumber)}</span></h2>
          ${r.amended ? '<span class="badge info">แก้ไขแล้ว</span>'
            : r.reprint ? '<span class="badge warn">REPRINT</span>'
            : '<span class="badge ok">ออกใหม่</span>'}
          <button class="close" onclick="openDetail('${esc(mawb)}')">✕</button></div>
        <div class="modal-body">
          <div class="kv">
            ${kv(r.doType === "COMBINED" ? `House (${r.lines.length} ใบ)` : "HAWB",
                 r.doType === "COMBINED"
                   ? r.lines.map(l => esc(l.hawbNumber)).join("<br>")
                   : esc(r.hawbNumber))}
            ${kv("Station", esc(r.station))}
            ${kv("Consignee", esc(r.consignee?.name))}
            ${kv("Flight", esc(r.flightNumber) + (r.aircraftRegistration ? " / " + esc(r.aircraftRegistration) : ""))}
            ${r.doType === "COMBINED"
              ? kv("รวมทั้งใบ", `${esc(r.totalPieces)} ชิ้น / ${esc(r.totalWeight)} ${esc(r.weightUnit || "")}`)
              : kv("Pieces", `${esc(r.pieces)} of ${esc(r.masterPieces)}`)
                + kv("Weight", `${esc(r.weight)} of ${esc(r.masterWeight)}${esc(r.weightUnit)}`)}
            ${r.lines?.[0]?.isPartial
              ? kv("ปล่อยครั้งนี้", `${esc(r.lines[0].pieces)} จาก ${esc(r.lines[0].housePieces)} ชิ้น`)
                + kv("คงเหลือ", `${esc(r.lines[0].balancePieces)} ชิ้น / ${esc(r.lines[0].balanceWeight)}`)
              : ""}
            ${kv("Landed / ATA", esc((r.landedAt || "—").replace("T", " ")))}
            ${kv("หมดอายุ (48 ชม.)", esc((r.expiryAt || "—").replace("T", " ")))}
          </div>
          <div class="export-grid" style="margin-top:20px">
            <button class="export-choice" onclick="window.open('${API}/do/${esc(r.id)}/preview','_blank')">
              <b>เปิดหน้าพิมพ์</b><span>ดูบนหน้าจอ แล้วสั่งพิมพ์หรือบันทึกเป็น PDF จากเบราว์เซอร์</span></button>
            <button class="export-choice" onclick="window.open('${API}/do/${esc(r.id)}/pdf','_blank')">
              <b>ดาวน์โหลด PDF</b><span>ไฟล์ PDF ขนาด A4 พร้อมบาร์โค้ด HAWB</span></button>
          </div>
        </div></div></div>`;
}

window.doLink = async (mawb, fhlId, hawb) => {
  const reason = prompt(`เหตุผลที่ link ${hawb} เข้ากับ ${mawb}:`);
  if (reason === null) return;
  try {
    const r = await api(`/matches/${encodeURIComponent(mawb)}/houses/${fhlId}/link`,
                        jsonPost({ reason }));
    toast(`Link แล้ว — สถานะใหม่ ${r.status} (score ${r.score})`);
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};

/* ---------------- raw data explorer ---------------- */
const OPS = [
  ["eq", "="], ["ne", "≠"], ["contains", "contains"], ["startswith", "starts with"],
  ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["isnull", "is empty"], ["notnull", "not empty"],
];

const NO_VALUE_OPS = new Set(["isnull", "notnull"]);
const PAGE_SIZE = 50;

async function renderRawData(params) {
  let tables;
  try { tables = (await api("/data/tables")).tables; }
  catch (e) { $("#view").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const state = {
    table: params.get("table") || "cargo_messages",
    filters: params.get("f") ? params.get("f").split(";") : [],
    match: "and", hidden: new Set(), page: 1, sortBy: "", sortDirection: "desc",
    lastRows: [], lastColumns: [],
  };

  $("#view").innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <label style="font-weight:600;font-size:.85rem">Table</label>
        <select id="rd-table">${tables.map(t =>
          `<option value="${t.table}" ${t.table === state.table ? "selected" : ""}>${t.table} (${t.rowCount})</option>`).join("")}
        </select>
        <button class="btn sm" id="rd-add-filter">+ เพิ่มเงื่อนไข</button>
        <label style="font-size:.82rem;color:var(--muted)">รวมเงื่อนไขแบบ</label>
        <select id="rd-match" style="width:88px">
          <option value="and">AND</option><option value="or">OR</option>
        </select>
        <div class="spacer"></div>
        <button class="btn sm" id="rd-cols">▦ คอลัมน์</button>
        <button class="btn sm" id="rd-analyze">📊 Group by</button>
        <button class="btn primary sm" id="rd-apply">Apply</button>
        <button class="btn sm" id="rd-export">⇓ Export CSV</button>
      </div>
      <div id="rd-filters"></div>
      <div id="rd-colpicker" class="colpicker" style="display:none"></div>
      <div id="rd-agg"></div>
      <div id="rd-table-view"></div>
    </div>`;

  const meta = () => tables.find(t => t.table === state.table);
  const visibleCols = () => meta().columns.filter(c => !state.hidden.has(c));
  const activeFilters = () =>
    state.filters.filter(f => {
      const [col, op, val] = f.split(":");
      return col && op && (NO_VALUE_OPS.has(op) || (val ?? "") !== "");
    });

  /* ---- filters ---- */
  function drawFilters() {
    const cols = meta().columns;
    $("#rd-filters").innerHTML = state.filters.map((f, i) => {
      const [col, op, val] = f.split(":");
      return `<div class="fb-row" data-i="${i}">
        <select class="fb-col">${cols.map(c =>
          `<option ${c === col ? "selected" : ""}>${c}</option>`).join("")}</select>
        <select class="fb-op">${OPS.map(([k, l]) =>
          `<option value="${k}" ${k === op ? "selected" : ""}>${l}</option>`).join("")}</select>
        <input type="text" class="fb-val" list="dl-${i}" value="${esc(val || "")}"
               placeholder="value" style="flex:1" ${NO_VALUE_OPS.has(op) ? "disabled" : ""}>
        <datalist id="dl-${i}"></datalist>
        <button class="fb-remove" title="ลบเงื่อนไข" onclick="rdRemoveFilter(${i})">✕</button>
      </div>`;
    }).join("");
    $$("#rd-filters .fb-row").forEach((row, i) => {
      $(".fb-col", row).onchange = () => { collect(); drawFilters(); suggest(i); };
      $(".fb-op", row).onchange = () => { collect(); drawFilters(); };
      suggest(i);
    });
  }
  async function suggest(i) {
    const row = $$("#rd-filters .fb-row")[i];
    if (!row) return;
    const col = $(".fb-col", row).value;
    try {
      const d = await api(`/data/${state.table}/distinct?column=${encodeURIComponent(col)}&limit=60`);
      const dl = $(`#dl-${i}`);
      if (dl) dl.innerHTML = d.values.map(v =>
        `<option value="${esc(v.v)}">${esc(v.v)} (${v.c})</option>`).join("");
    } catch { /* distinct is a convenience only */ }
  }
  window.rdRemoveFilter = (i) => { collect(); state.filters.splice(i, 1); drawFilters(); };
  function collect() {
    state.filters = $$("#rd-filters .fb-row").map(row =>
      `${$(".fb-col", row).value}:${$(".fb-op", row).value}:${$(".fb-val", row).value}`);
    state.match = $("#rd-match").value;
  }

  /* ---- column picker ---- */
  function drawColPicker() {
    $("#rd-colpicker").innerHTML = meta().columns.map(c =>
      `<label class="cp-item"><input type="checkbox" data-col="${c}"
        ${state.hidden.has(c) ? "" : "checked"}> ${c}</label>`).join("") +
      `<button class="btn sm" id="cp-all" style="margin-left:8px">เลือกทั้งหมด</button>`;
    $$("#rd-colpicker input").forEach(cb => cb.onchange = () => {
      cb.checked ? state.hidden.delete(cb.dataset.col) : state.hidden.add(cb.dataset.col);
      draw();
    });
    $("#cp-all").onclick = () => { state.hidden.clear(); drawColPicker(); draw(); };
  }

  /* ---- group-by panel ---- */
  let aggOpen = false;
  function drawAggPanel() {
    if (!aggOpen) { $("#rd-agg").innerHTML = ""; return; }
    const cols = meta().columns;
    $("#rd-agg").innerHTML = `
      <div class="agg-box">
        <div class="filter-bar" style="margin-bottom:10px">
          <label style="font-size:.82rem;font-weight:600">Group by</label>
          <select id="ag-group">${cols.map(c => `<option>${c}</option>`).join("")}</select>
          <label style="font-size:.82rem;font-weight:600">Metric</label>
          <select id="ag-metric">
            <option value="count">COUNT(*)</option><option value="sum">SUM</option>
            <option value="avg">AVG</option><option value="min">MIN</option><option value="max">MAX</option>
          </select>
          <select id="ag-mcol" style="display:none">${cols.map(c => `<option>${c}</option>`).join("")}</select>
          <button class="btn primary sm" id="ag-run">คำนวณ</button>
          <div class="spacer"></div>
          <button class="btn sm" id="ag-close">✕ ปิด</button>
        </div>
        <div id="ag-result"></div>
      </div>`;
    $("#ag-metric").onchange = (e) => {
      $("#ag-mcol").style.display = e.target.value === "count" ? "none" : "";
    };
    $("#ag-close").onclick = () => { aggOpen = false; drawAggPanel(); };
    $("#ag-run").onclick = runAgg;
    runAgg();
  }
  async function runAgg() {
    collect();
    const q = new URLSearchParams({
      groupBy: $("#ag-group").value, metric: $("#ag-metric").value, match: state.match,
    });
    if ($("#ag-metric").value !== "count") q.set("metricColumn", $("#ag-mcol").value);
    activeFilters().forEach(f => q.append("filter", f));
    let d;
    try { d = await api(`/data/${state.table}/aggregate?` + q); }
    catch (e) { $("#ag-result").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const max = Math.max(...d.buckets.map(b => Math.abs(b.value || 0)), 1);
    $("#ag-result").innerHTML = d.buckets.length ? `
      <table class="tbl"><thead><tr>
        <th>${esc(d.groupBy)}</th>
        <th class="num">${esc(d.metric.toUpperCase())}${d.metricColumn ? `(${esc(d.metricColumn)})` : "(*)"}</th>
        <th style="width:45%">&nbsp;</th><th class="num">rows</th></tr></thead>
        <tbody>${d.buckets.map(b => `<tr>
          <td><b>${esc(b.bucket ?? "(null)")}</b></td>
          <td class="num">${fmtW(b.value)}</td>
          <td><div class="agg-bar" style="width:${Math.max(2, Math.abs(b.value || 0) / max * 100)}%"></div></td>
          <td class="num">${b.rows}</td></tr>`).join("")}
        </tbody></table>` : `<div class="empty">ไม่มีข้อมูล</div>`;
  }

  /* ---- grid ---- */
  function draw() {
    const cols = visibleCols();
    const rows = state.lastRows;
    $("#rd-table-view").innerHTML = `
      <div class="tbl-wrap" style="max-height:58vh;overflow:auto"><table class="tbl">
        <thead><tr>${cols.map(c =>
          `<th style="cursor:pointer" onclick="rdSort('${c}')">${c}${
            state.sortBy === c ? (state.sortDirection === "asc" ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r, i) => `<tr class="clickable" onclick="rdRow(${i})">${cols.map(c => {
          let v = r[c];
          if (c === "match_status" || c === "parse_status") return `<td>${badge(v)}</td>`;
          if (v != null && String(v).length > 48) v = String(v).slice(0, 48) + "…";
          return `<td class="mono" style="font-size:.78rem">${esc(v ?? "")}</td>`;
        }).join("")}</tr>`).join("") ||
          `<tr><td colspan="${cols.length}" class="empty">ไม่มีข้อมูลตามเงื่อนไข</td></tr>`}
        </tbody></table></div>
      <div class="pager">
        <span>${state.total} แถว${activeFilters().length
          ? ` · ${activeFilters().length} เงื่อนไข (${state.match.toUpperCase()})` : ""}</span>
        <button class="btn sm" id="rd-prev" ${state.page <= 1 ? "disabled" : ""}>←</button>
        <span>หน้า ${state.page}</span>
        <button class="btn sm" id="rd-next" ${state.page * PAGE_SIZE >= state.total ? "disabled" : ""}>→</button>
      </div>`;
    const prev = $("#rd-prev"), next = $("#rd-next");
    if (prev) prev.onclick = () => { state.page--; load(); };
    if (next) next.onclick = () => { state.page++; load(); };
  }
  window.rdSort = (c) => {
    if (state.sortBy === c) state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
    else { state.sortBy = c; state.sortDirection = "asc"; }
    load();
  };
  window.rdRow = (i) => {
    const r = state.lastRows[i];
    $("#modal-root").innerHTML = `
      <div class="modal-back" onclick="if(event.target===this)closeModal()">
        <div class="modal" style="max-width:760px">
          <div class="modal-head"><h2>${esc(state.table)} — row detail</h2>
            <button class="close" onclick="closeModal()">✕</button></div>
          <div class="modal-body"><div class="kv">${
            state.lastColumns.map(c => kv(c, esc(r[c] ?? "—"))).join("")}</div>
            ${r.mawb_number ? `<div style="margin-top:16px">
              <button class="btn gold" onclick="closeModal();openDetail('${esc(r.mawb_number)}')">
                ดู Match Detail ของ ${esc(r.mawb_number)} →</button></div>` : ""}
          </div></div></div>`;
  };

  async function load() {
    collect();
    const q = new URLSearchParams({ page: state.page, pageSize: PAGE_SIZE, match: state.match });
    if (state.sortBy) { q.set("sortBy", state.sortBy); q.set("sortDirection", state.sortDirection); }
    activeFilters().forEach(f => q.append("filter", f));
    let data;
    try { data = await api(`/data/${state.table}?` + q); }
    catch (e) { $("#rd-table-view").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    state.lastRows = data.rows;
    state.lastColumns = data.columns;
    state.total = data.total;
    draw();
  }

  $("#rd-table").onchange = () => {
    state.table = $("#rd-table").value;
    state.filters = []; state.hidden.clear(); state.page = 1; state.sortBy = "";
    drawFilters(); drawColPicker(); drawAggPanel(); load();
  };
  $("#rd-add-filter").onclick = () => {
    collect(); state.filters.push(`${meta().columns[0]}:contains:`); drawFilters();
  };
  $("#rd-cols").onclick = () => {
    const el = $("#rd-colpicker");
    el.style.display = el.style.display === "none" ? "flex" : "none";
  };
  $("#rd-analyze").onclick = () => { aggOpen = !aggOpen; drawAggPanel(); };
  $("#rd-apply").onclick = () => { state.page = 1; load(); };
  $("#rd-export").onclick = () => {
    collect();
    const q = new URLSearchParams({ match: state.match });
    activeFilters().forEach(f => q.append("filter", f));
    window.open(`${API}/data/${state.table}/export?` + q, "_blank");
  };

  drawFilters();
  drawColPicker();
  load();
}

/* ---------------- delivery orders page ---------------- */
async function renderDeliveryOrders(params) {
  const state = { search: params.get("search") || "", status: "", page: 1 };
  $("#view").innerHTML = `
    <div class="panel" id="combinable-panel"></div>
    <div class="panel">
      <div class="filter-bar">
        <input type="search" id="do-search" placeholder="ค้นหา DO No / MAWB / HAWB…"
               value="${esc(state.search)}" style="width:280px">
        <select id="do-status">
          <option value="">ทุกสถานะ</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="SUPERSEDED">SUPERSEDED</option>
          <option value="CANCELLED">CANCELLED</option>
        </select>
        <button class="btn primary sm" id="do-apply">ค้นหา</button>
        <div class="spacer"></div>
        <span style="color:var(--muted);font-size:.83rem">
          ออก DO ใหม่ได้จากแท็บ Houses ในหน้ารายละเอียดของแต่ละ MAWB</span>
      </div>
      <div id="do-table"></div>
    </div>`;

  // Consignees waiting on more than one shipment — the reason to combine.
  (async () => {
    let d;
    try { d = await api("/do/combinable"); }
    catch { $("#combinable-panel").remove(); return; }
    if (!d.groups.length) { $("#combinable-panel").remove(); return; }
    $("#combinable-panel").innerHTML = `
      <h2>รวม DO ได้ (${d.groups.length} ราย)</h2>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">
        ผู้รับเหล่านี้มีของมากกว่า 1 house ที่ยังไม่ได้ออก DO
        รวมเป็นใบเดียวได้เพื่อให้มารับของครั้งเดียวจบ</p>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>ผู้รับปลายทาง</th><th>ปลายทาง</th><th class="num">House</th>
          <th class="num">MAWB</th><th>HAWB</th><th class="num">Pieces</th>
          <th class="num">Weight</th>${canImport() ? "<th></th>" : ""}</tr></thead>
        <tbody>${d.groups.map((g, i) => `<tr>
          <td class="trunc" title="${esc(g.consignee)}"><b>${esc(g.consignee)}</b></td>
          <td>${esc(g.destination || "—")}</td>
          <td class="num">${g.houseCount}</td>
          <td class="num">${g.mawbCount}</td>
          <td class="mono" style="font-size:.76rem">${
            g.houses.map(h => esc(h.hawb_number)).join(", ")}</td>
          <td class="num">${g.totalPieces}</td>
          <td class="num">${fmtW(g.totalWeight)}</td>
          ${canImport() ? `<td><button class="btn gold sm"
            onclick="combineGroup(${i})">🧾 รวมเป็นใบเดียว</button></td>` : ""}
        </tr>`).join("")}
        </tbody></table></div>`;
    window.__combinableGroups = d.groups;
  })();

  async function load() {
    state.search = $("#do-search").value.trim();
    state.status = $("#do-status").value;
    let d;
    try {
      d = await api(`/do?${new URLSearchParams({
        page: state.page, pageSize: 50, search: state.search, status: state.status })}`);
    } catch (e) { $("#do-table").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const statusBadge = (s) => s === "ACTIVE" ? '<span class="badge ok">ACTIVE</span>'
      : s === "SUPERSEDED" ? '<span class="badge warn">SUPERSEDED</span>'
      : '<span class="badge muted">CANCELLED</span>';
    $("#do-table").innerHTML = d.items.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>DO No</th><th>ชนิด</th><th>สถานะ</th><th>MAWB</th><th>HAWB</th>
          <th>Consignee</th><th>Station</th><th class="num">Pcs</th><th class="num">Weight</th>
          <th>หมดอายุ</th><th>ออกโดย</th><th></th></tr></thead>
        <tbody>${d.items.map(r => `<tr>
          <td class="mono"><b>${esc(r.do_number)}</b></td>
          <td>${r.do_type === "COMBINED"
            ? `<span class="badge info">รวม ${r.line_count}</span>`
            : '<span class="badge muted">เดี่ยว</span>'}</td>
          <td>${statusBadge(r.status)}</td>
          <td class="mono clickable" onclick="openDetail('${esc(r.mawb_number)}')">${esc(r.mawb_number)}</td>
          <td class="mono trunc" title="${esc(r.hawbs || "")}">${esc(r.hawbs || r.hawb_number || "—")}</td>
          <td class="trunc" title="${esc(r.consignee_name)}">${esc(r.consignee_name || "—")}</td>
          <td>${esc(r.station || "—")}</td>
          <td class="num">${r.pieces ?? "—"}</td>
          <td class="num">${fmtW(r.weight)}</td>
          <td>${esc((r.expiry_at || "—").replace("T", " "))}</td>
          <td>${esc(r.issued_by || r.created_by || "—")}</td>
          <td style="white-space:nowrap">
            <button class="btn sm" onclick="window.open('${API}/do/${esc(r.id)}/preview','_blank')">พิมพ์</button>
            <button class="btn sm" onclick="window.open('${API}/do/${esc(r.id)}/pdf','_blank')">PDF</button>
            ${canImport() && r.status === "ACTIVE" && r.line_count > 1
              ? `<button class="btn sm" onclick="openSplitDialog('${esc(r.id)}','${esc(r.do_number)}')">✂ แยก</button>` : ""}
            ${isAdmin() && r.status === "ACTIVE"
              ? `<button class="btn sm" onclick="cancelDo('${esc(r.id)}','${esc(r.do_number)}')">ยกเลิก</button>` : ""}
          </td></tr>`).join("")}
        </tbody></table></div>
      <div class="pager"><span>${d.total} ฉบับ</span>
        <button class="btn sm" id="do-prev" ${state.page <= 1 ? "disabled" : ""}>←</button>
        <span>หน้า ${state.page}</span>
        <button class="btn sm" id="do-next" ${state.page * 50 >= d.total ? "disabled" : ""}>→</button>
      </div>` :
      `<div class="empty"><div class="big">🧾</div>ยังไม่มี Delivery Order —
        เปิดหน้ารายละเอียด MAWB แล้วไปที่แท็บ Houses เพื่อออก DO</div>`;
    const p = $("#do-prev"), n = $("#do-next");
    if (p) p.onclick = () => { state.page--; load(); };
    if (n) n.onclick = () => { state.page++; load(); };
  }
  $("#do-apply").onclick = () => { state.page = 1; load(); };
  $("#do-search").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; load(); } };
  load();
}

window.combineGroup = (index) => {
  const group = (window.__combinableGroups || [])[index];
  if (!group) return;
  openCombineDialog(null, {
    ids: group.houses.map(h => h.id),
    label: `${group.houseCount} house ของ ${group.consignee}`,
  });
};

window.cancelDo = async (doId, doNumber) => {
  const reason = prompt(`เหตุผลที่ยกเลิก DO ${doNumber}\n` +
                        "(house ในใบนี้จะกลับมาออก DO ใหม่ได้):");
  if (reason === null) return;
  try {
    await api(`/do/${doId}/cancel`, jsonPost({ reason }));
    toast(`ยกเลิก DO ${doNumber} แล้ว`);
    navigate();
  } catch (e) { toast(e.message, true); }
};

/* ---------------- errors page ---------------- */
async function renderErrors() {
  const v = $("#view");
  v.innerHTML = `<div class="empty">Loading…</div>`;
  let d;
  try { d = await api("/errors"); }
  catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const sevBadge = (s) => `<span class="badge ${s === "ERROR" ? "err" : "warn"}">${esc(s)}</span>`;
  v.innerHTML = `
    <div class="cards">
      <div class="stat-card accent-err"><div class="label">Parse Errors</div>
        <div class="value">${d.parseErrors.length}</div></div>
      <div class="stat-card accent-warn"><div class="label">Failed Rules</div>
        <div class="value">${d.validationFailures.length}</div></div>
      <div class="stat-card accent-info"><div class="label">Duplicates</div>
        <div class="value">${d.duplicates.length}</div></div>
    </div>
    <div class="panel">
      <h2>ไฟล์ที่ Parse ไม่สำเร็จ</h2>
      ${d.parseErrors.length ? `<div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>File</th><th>Type</th><th>Status</th><th>Error Code</th>
          <th>Message</th><th>By</th><th>Imported</th></tr></thead>
        <tbody>${d.parseErrors.map(r => `<tr>
          <td>${esc(r.original_filename || "(pasted)")}</td>
          <td>${esc(r.message_type || "—")}</td>
          <td>${badge(r.parse_status)}</td>
          <td class="mono">${esc(r.parse_error_code || "—")}</td>
          <td style="white-space:normal">${esc(r.parse_error_message || "")}</td>
          <td>${esc(r.imported_by || "—")}</td><td>${fmtD(r.imported_at)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ไม่มีไฟล์ที่ parse ไม่สำเร็จ</div>`}
    </div>
    <div class="panel">
      <h2>Validation Rules ที่ไม่ผ่าน</h2>
      ${d.validationFailures.length ? `<div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>MAWB</th><th>Rule</th><th>Severity</th><th>FWB</th>
          <th>FHL</th><th>Difference</th><th></th></tr></thead>
        <tbody>${d.validationFailures.map(r => `<tr class="clickable" onclick="openDetail('${esc(r.mawb_number)}')">
          <td class="mono"><b>${esc(r.mawb_number)}</b></td>
          <td><b>${esc(r.rule_code)}</b></td><td>${sevBadge(r.severity)}</td>
          <td class="mono">${esc(r.fwb_value ?? "—")}</td>
          <td class="mono">${esc(r.fhl_value ?? "—")}</td>
          <td class="mono">${esc(r.difference_value ?? "—")}</td>
          <td><button class="btn sm">ตรวจสอบ →</button></td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ทุกกฎผ่านหมด</div>`}
    </div>
    <div class="panel">
      <h2>ข้อความซ้ำ</h2>
      ${d.duplicates.length ? `<div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>File</th><th>Type</th><th>Duplicate Type</th>
          <th>Detail</th><th>Imported</th></tr></thead>
        <tbody>${d.duplicates.map(r => `<tr>
          <td>${esc(r.original_filename || "(pasted)")}</td>
          <td>${esc(r.message_type || "—")}</td>
          <td><span class="badge warn">${esc(r.duplicate_type || "EXACT")}</span></td>
          <td style="white-space:normal;font-size:.8rem">${esc(r.parse_error_message || "ข้อมูลธุรกิจซ้ำ (revision)")}</td>
          <td>${fmtD(r.imported_at)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ไม่มีข้อความซ้ำ</div>`}
    </div>`;
}

/* ---------------- history page ---------------- */
async function renderHistory(params) {
  const state = { mawb: params.get("mawb") || "", page: 1 };
  $("#view").innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <input type="search" id="h-mawb" placeholder="กรองด้วย MAWB…" value="${esc(state.mawb)}" style="width:240px">
        <button class="btn primary sm" id="h-apply">Apply</button>
      </div>
      <div id="h-table"></div>
    </div>`;
  async function load() {
    state.mawb = $("#h-mawb").value.trim();
    let d;
    try { d = await api(`/history?${new URLSearchParams({ page: state.page, pageSize: 50, mawb: state.mawb })}`); }
    catch (e) { $("#h-table").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    $("#h-table").innerHTML = d.items.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>When</th><th>MAWB</th><th>Event</th><th>Status change</th>
          <th class="num">Score</th><th>By</th></tr></thead>
        <tbody>${d.items.map(h => `<tr class="clickable" onclick="openDetail('${esc(h.mawb_number)}')">
          <td>${fmtD(h.performed_at)}</td>
          <td class="mono"><b>${esc(h.mawb_number)}</b></td>
          <td><span class="badge info">${esc(h.event_type)}</span></td>
          <td>${h.previous_status ? badge(h.previous_status) + " → " : ""}${badge(h.new_status)}</td>
          <td class="num">${h.previous_score ?? "—"} → <b>${h.new_score ?? "—"}</b></td>
          <td>${esc(h.performed_by || "—")}</td></tr>`).join("")}
        </tbody></table></div>
      <div class="pager"><span>${d.total} เหตุการณ์</span>
        <button class="btn sm" id="h-prev" ${state.page <= 1 ? "disabled" : ""}>←</button>
        <span>หน้า ${state.page}</span>
        <button class="btn sm" id="h-next" ${state.page * 50 >= d.total ? "disabled" : ""}>→</button>
      </div>` : `<div class="empty">ยังไม่มีประวัติ</div>`;
    const p = $("#h-prev"), n = $("#h-next");
    if (p) p.onclick = () => { state.page--; load(); };
    if (n) n.onclick = () => { state.page++; load(); };
  }
  $("#h-apply").onclick = () => { state.page = 1; load(); };
  $("#h-mawb").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; load(); } };
  load();
}

/* ---------------- audit page ---------------- */
async function renderAudit() {
  const state = { eventType: "", page: 1 };
  $("#view").innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <label style="font-size:.85rem;font-weight:600">Event type</label>
        <select id="a-type"><option value="">ทั้งหมด</option></select>
        <button class="btn primary sm" id="a-apply">Apply</button>
      </div>
      <div id="a-table"></div>
    </div>`;
  async function load() {
    state.eventType = $("#a-type").value;
    let d;
    try { d = await api(`/audit?${new URLSearchParams({ page: state.page, pageSize: 50, eventType: state.eventType })}`); }
    catch (e) { $("#a-table").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const sel = $("#a-type");
    if (sel.options.length === 1) {
      d.eventTypes.forEach(t => sel.add(new Option(t, t)));
      sel.value = state.eventType;
    }
    $("#a-table").innerHTML = d.items.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>When</th><th>Event</th><th>User</th><th>Entity</th>
          <th>Reason</th><th>IP</th></tr></thead>
        <tbody>${d.items.map(a => `<tr>
          <td>${fmtD(a.created_at)}</td>
          <td><span class="badge info">${esc(a.event_type)}</span></td>
          <td><b>${esc(a.user_id || "—")}</b></td>
          <td class="mono" style="font-size:.76rem">${esc(a.entity_type || "")} ${esc((a.entity_id || "").slice(0, 20))}</td>
          <td style="white-space:normal">${esc(a.reason || "—")}</td>
          <td class="mono" style="font-size:.76rem">${esc(a.ip_address || "—")}</td></tr>`).join("")}
        </tbody></table></div>
      <div class="pager"><span>${d.total} รายการ</span>
        <button class="btn sm" id="a-prev" ${state.page <= 1 ? "disabled" : ""}>←</button>
        <span>หน้า ${state.page}</span>
        <button class="btn sm" id="a-next" ${state.page * 50 >= d.total ? "disabled" : ""}>→</button>
      </div>` : `<div class="empty">ยังไม่มี audit log</div>`;
    const p = $("#a-prev"), n = $("#a-next");
    if (p) p.onclick = () => { state.page--; load(); };
    if (n) n.onclick = () => { state.page++; load(); };
  }
  $("#a-apply").onclick = () => { state.page = 1; load(); };
  load();
}

/* ---------------- settings page ---------------- */
async function renderSettings() {
  const v = $("#view");
  v.innerHTML = `<div class="empty">Loading…</div>`;
  let d;
  try { d = await api("/settings"); }
  catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  const editable = isAdmin();
  const field = (s) => {
    if (s.type === "severity") {
      return `<select data-key="${s.key}" ${editable ? "" : "disabled"}>
        ${["ERROR", "WARNING", "INFO"].map(x =>
          `<option ${x === s.value ? "selected" : ""}>${x}</option>`).join("")}</select>`;
    }
    const value = Array.isArray(s.value) ? s.value.join(",") : s.value;
    return `<input type="text" data-key="${s.key}" value="${esc(value)}" ${editable ? "" : "disabled"}>`;
  };
  v.innerHTML = `
    <div class="panel">
      <h2>Matching Rules</h2>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">
        ${editable
          ? "แก้ค่าแล้วกดบันทึก ระบบจะ re-match ทุก MAWB ใหม่ทันทีและบันทึก audit log"
          : `บทบาท ${esc(CURRENT_USER.role)} ดูได้อย่างเดียว — เฉพาะ Administrator เท่านั้นที่แก้ไขได้`}
      </p>
      <div class="settings-grid">
        ${d.settings.map(s => `<div class="setting-item">
          <div class="k">${esc(s.label)}</div>
          ${field(s)}
          <div class="hint">key: <code>${esc(s.key)}</code> · default:
            ${esc(Array.isArray(s.default) ? s.default.join(",") : s.default)}</div>
        </div>`).join("")}
      </div>
      ${editable ? `<div style="margin-top:20px;display:flex;gap:10px;align-items:center">
        <button class="btn gold" id="set-save">บันทึกและ Re-match ทั้งหมด</button>
        <button class="btn" id="set-reset">คืนค่าเริ่มต้น</button>
        <span id="set-status" style="color:var(--muted);font-size:.85rem"></span>
      </div>` : ""}
    </div>
    <div class="panel">
      <h2>บัญชีผู้ใช้และสิทธิ์</h2>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>บทบาท</th><th>สิทธิ์ตามเอกสารออกแบบ §4</th></tr></thead>
        <tbody>
          <tr><td><span class="badge err">ADMINISTRATOR</span></td>
            <td style="white-space:normal">Import, Reprocess/Re-match, Manual link/unlink, Resolve &amp; Reject, ตั้งค่า Matching Rule, ดู Audit Log, Export</td></tr>
          <tr><td><span class="badge warn">OPERATOR</span></td>
            <td style="white-space:normal">Import, ดู Dashboard และ Match Result, Mark as Reviewed, เพิ่มหมายเหตุ, Export</td></tr>
          <tr><td><span class="badge info">VIEWER</span></td>
            <td style="white-space:normal">ดู Dashboard, Match Result, Message Detail และ Export</td></tr>
        </tbody></table></div>
      <div id="user-list"></div>
    </div>`;

  if (editable) {
    $("#set-save").onclick = async () => {
      const changes = {};
      $$("[data-key]").forEach(el => { changes[el.dataset.key] = el.value; });
      $("#set-status").textContent = "กำลังบันทึก…";
      try {
        const r = await api("/settings", { ...jsonPost({ changes, rematch: true }), method: "PUT" });
        const changed = Object.entries(r.applied)
          .filter(([, x]) => String(x.before) !== String(x.after));
        $("#set-status").textContent =
          `บันทึกแล้ว · เปลี่ยน ${changed.length} ค่า · re-match ${r.rematched} MAWB`;
        toast(`บันทึกการตั้งค่าแล้ว — re-match ${r.rematched} MAWB`);
      } catch (e) { $("#set-status").textContent = ""; toast(e.message, true); }
    };
    $("#set-reset").onclick = () => {
      d.settings.forEach(s => {
        const el = $(`[data-key="${s.key}"]`);
        el.value = Array.isArray(s.default) ? s.default.join(",") : s.default;
      });
      $("#set-status").textContent = "คืนค่าเริ่มต้นในฟอร์มแล้ว — กดบันทึกเพื่อยืนยัน";
    };
    api("/users").then(u => {
      $("#user-list").innerHTML = `
        <div class="section-title"><h3>ผู้ใช้ในระบบ</h3></div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>Username</th><th>ชื่อ</th><th>Role</th><th>Active</th><th>Last login</th></tr></thead>
          <tbody>${u.items.map(x => `<tr>
            <td class="mono"><b>${esc(x.username)}</b></td><td>${esc(x.display_name || "—")}</td>
            <td>${esc(x.role)}</td>
            <td>${x.active ? '<span class="badge ok">✓</span>' : '<span class="badge muted">—</span>'}</td>
            <td>${fmtD(x.last_login_at)}</td></tr>`).join("")}
          </tbody></table></div>`;
    }).catch(() => {});
  }
}

/* ---------------- users page ---------------- */
const ROLE_BADGE = {
  ADMINISTRATOR: "err", OPERATOR: "warn", VIEWER: "info",
};

async function renderUsers() {
  const v = $("#view");
  v.innerHTML = `<div class="empty">Loading…</div>`;
  let d;
  try { d = await api("/users"); }
  catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

  v.innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <h2 style="margin:0">ผู้ใช้ในระบบ (${d.items.length})</h2>
        <div class="spacer"></div>
        <button class="btn gold sm" id="u-new">+ เพิ่มผู้ใช้</button>
      </div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>Username</th><th>ชื่อ</th><th>บทบาท</th><th>สถานะ</th>
          <th>เข้าใช้ล่าสุด</th><th>สร้างเมื่อ</th><th></th></tr></thead>
        <tbody>${d.items.map(u => `<tr>
          <td class="mono"><b>${esc(u.username)}</b>${
            u.username === CURRENT_USER.username
              ? ' <span class="badge muted">คุณ</span>' : ""}</td>
          <td>${esc(u.display_name || "—")}</td>
          <td><span class="badge ${ROLE_BADGE[u.role] || "muted"}">${esc(u.role)}</span></td>
          <td>${u.active ? '<span class="badge ok">ใช้งาน</span>'
                         : '<span class="badge muted">ปิดใช้งาน</span>'}
              ${u.must_change_password
                ? ' <span class="badge warn" title="ต้องตั้งรหัสผ่านใหม่ตอนเข้าระบบ">ต้องเปลี่ยนรหัส</span>' : ""}</td>
          <td>${fmtD(u.last_login_at)}</td>
          <td>${fmtD(u.created_at)}</td>
          <td style="white-space:nowrap">
            <button class="btn sm" onclick="editUser('${esc(u.id)}','${esc(u.username)}','${esc(u.role)}',${u.active ? 1 : 0})">แก้ไข</button>
            <button class="btn sm" onclick="resetUserPassword('${esc(u.id)}','${esc(u.username)}')">ตั้งรหัสใหม่</button>
          </td></tr>`).join("")}
        </tbody></table></div>
    </div>
    <div class="panel">
      <h2>สิทธิ์ของแต่ละบทบาท</h2>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>บทบาท</th><th>ทำอะไรได้</th></tr></thead>
        <tbody>
          <tr><td><span class="badge err">ADMINISTRATOR</span></td>
            <td style="white-space:normal">ทุกอย่าง — Import, Re-match, Manual link/unlink,
              Resolve/Reject, ตั้งค่า Matching Rule, จัดการผู้ใช้, แก้ไข DO, ดู Audit Log</td></tr>
          <tr><td><span class="badge warn">OPERATOR</span></td>
            <td style="white-space:normal">Import, Mark as Reviewed, ออก DO, Export
              และดูข้อมูลทุกหน้ายกเว้น Audit Log กับ Users</td></tr>
          <tr><td><span class="badge info">VIEWER</span></td>
            <td style="white-space:normal">ดูอย่างเดียว + Export และพิมพ์ DO ที่ออกแล้ว</td></tr>
        </tbody></table></div>
    </div>`;

  $("#u-new").onclick = () => {
    $("#modal-root").innerHTML = `
      <div class="modal-back" onclick="if(event.target===this)closeModal()">
        <div class="modal" style="max-width:560px">
          <div class="modal-head"><h2>เพิ่มผู้ใช้ใหม่</h2>
            <button class="close" onclick="closeModal()">✕</button></div>
          <div class="modal-body">
            <div class="settings-grid">
              <div class="setting-item"><div class="k">Username</div>
                <input type="text" id="nu-name" placeholder="a-z 0-9 . _ - (3-32 ตัว)">
                <div class="hint">ใช้เข้าระบบ เปลี่ยนภายหลังไม่ได้</div></div>
              <div class="setting-item"><div class="k">ชื่อที่แสดง</div>
                <input type="text" id="nu-display" placeholder="เช่น สมชาย ใจดี"></div>
              <div class="setting-item"><div class="k">บทบาท</div>
                <select id="nu-role">
                  <option value="OPERATOR">OPERATOR</option>
                  <option value="VIEWER">VIEWER</option>
                  <option value="ADMINISTRATOR">ADMINISTRATOR</option>
                </select></div>
              <div class="setting-item"><div class="k">รหัสผ่านชั่วคราว</div>
                <input type="text" id="nu-pass" placeholder="อย่างน้อย 8 ตัว มีตัวอักษร+ตัวเลข">
                <div class="hint">ผู้ใช้ต้องตั้งรหัสใหม่ตอนเข้าระบบครั้งแรก</div></div>
            </div>
            <div style="margin-top:18px;display:flex;gap:10px;align-items:center">
              <button class="btn gold" id="nu-save">สร้างผู้ใช้</button>
              <button class="btn" onclick="closeModal()">ยกเลิก</button>
              <span id="nu-status" style="color:var(--err);font-size:.85rem"></span>
            </div>
          </div></div></div>`;
    $("#nu-save").onclick = async () => {
      try {
        await api("/users", jsonPost({
          username: $("#nu-name").value.trim(),
          displayName: $("#nu-display").value.trim(),
          role: $("#nu-role").value,
          password: $("#nu-pass").value,
        }));
        closeModal();
        toast("สร้างผู้ใช้แล้ว");
        renderUsers();
      } catch (e) { $("#nu-status").textContent = e.message; }
    };
  };
}

window.editUser = async (id, username, role, active) => {
  const newRole = prompt(
    `บทบาทของ ${username} (ADMINISTRATOR / OPERATOR / VIEWER):`, role);
  if (newRole === null) return;
  const body = { role: newRole.trim().toUpperCase() };
  if (confirm(active ? `ปิดการใช้งานบัญชี ${username} ด้วยหรือไม่?`
                     : `เปิดใช้งานบัญชี ${username} ด้วยหรือไม่?`)) {
    body.active = !active;
  }
  try {
    await api(`/users/${id}`, { ...jsonPost(body), method: "PATCH" });
    toast(`อัปเดต ${username} แล้ว`);
    renderUsers();
  } catch (e) { toast(e.message, true); }
};

window.resetUserPassword = async (id, username) => {
  const pass = prompt(`ตั้งรหัสผ่านชั่วคราวให้ ${username}\n` +
                      "(อย่างน้อย 8 ตัว มีทั้งตัวอักษรและตัวเลข):");
  if (!pass) return;
  try {
    await api(`/users/${id}/password`, jsonPost({ newPassword: pass }));
    toast(`ตั้งรหัสใหม่ให้ ${username} แล้ว — ผู้ใช้ต้องเปลี่ยนตอนเข้าระบบ`);
    renderUsers();
  } catch (e) { toast(e.message, true); }
};

/* ---------------- password change ---------------- */
window.openPasswordDialog = (forced = false) => {
  $("#modal-root").innerHTML = `
    <div class="modal-back" ${forced ? "" : 'onclick="if(event.target===this)closeModal()"'}>
      <div class="modal" style="max-width:520px">
        <div class="modal-head"><h2>${forced ? "ต้องตั้งรหัสผ่านใหม่" : "เปลี่ยนรหัสผ่าน"}</h2>
          ${forced ? "" : '<button class="close" onclick="closeModal()">✕</button>'}</div>
        <div class="modal-body">
          ${forced ? `<p style="color:var(--warn);font-size:.88rem;margin-bottom:16px;font-weight:600">
            บัญชีนี้ยังใช้รหัสผ่านเริ่มต้นที่ประกาศไว้ในเอกสาร
            ต้องตั้งรหัสใหม่ก่อนจึงจะใช้งานระบบได้</p>` : ""}
          <div class="settings-grid">
            <div class="setting-item"><div class="k">รหัสผ่านเดิม</div>
              <input type="password" id="pw-current" autocomplete="current-password"></div>
            <div class="setting-item"><div class="k">รหัสผ่านใหม่</div>
              <input type="password" id="pw-new" autocomplete="new-password">
              <div class="hint">อย่างน้อย 8 ตัว มีทั้งตัวอักษรและตัวเลข</div></div>
            <div class="setting-item"><div class="k">ยืนยันรหัสผ่านใหม่</div>
              <input type="password" id="pw-confirm" autocomplete="new-password"></div>
          </div>
          <div style="margin-top:18px;display:flex;gap:10px;align-items:center">
            <button class="btn gold" id="pw-save">บันทึกรหัสผ่าน</button>
            ${forced ? "" : '<button class="btn" onclick="closeModal()">ยกเลิก</button>'}
            <span id="pw-status" style="color:var(--err);font-size:.85rem"></span>
          </div>
        </div></div></div>`;

  $("#pw-save").onclick = async () => {
    const next = $("#pw-new").value;
    if (next !== $("#pw-confirm").value) {
      $("#pw-status").textContent = "รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน";
      return;
    }
    try {
      await api("/auth/password", jsonPost({
        currentPassword: $("#pw-current").value, newPassword: next,
      }));
      closeModal();
      $("#view").innerHTML = "";
      showLogin("เปลี่ยนรหัสผ่านแล้ว กรุณาเข้าสู่ระบบใหม่");
    } catch (e) { $("#pw-status").textContent = e.message; }
  };
};

$("#btn-password").addEventListener("click", () => openPasswordDialog(false));

/* ---------------- auth ---------------- */
function showLogin(message = "") {
  CURRENT_USER = null;
  $("#login-root").hidden = false;
  $("#login-error").textContent = message;
  $("#login-user").focus();
}
function applyUser(user) {
  CURRENT_USER = user;
  $("#login-root").hidden = true;
  $("#user-name").textContent = user.displayName || user.username;
  $("#user-role").textContent = user.role;
  $("#user-avatar").textContent = (user.username || "?").slice(0, 2).toUpperCase();
  $$(".nav a").forEach(a => {
    const allowed = a.dataset.roles;
    a.hidden = !!allowed && !allowed.split(",").includes(user.role);
  });
  navigate();
  // A seeded or reset account cannot be used until its password is replaced.
  if (user.mustChangePassword) openPasswordDialog(true);
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-submit");
  btn.disabled = true;
  $("#login-error").textContent = "";
  try {
    const r = await api("/auth/login", jsonPost({
      username: $("#login-user").value.trim(),
      password: $("#login-pass").value,
    }));
    $("#login-pass").value = "";
    applyUser(r.user);
    toast(`ยินดีต้อนรับ ${r.user.displayName || r.user.username}`);
  } catch (err) { $("#login-error").textContent = err.message; }
  btn.disabled = false;
});

$("#btn-logout").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch { /* already gone */ }
  $("#view").innerHTML = "";
  showLogin("ออกจากระบบแล้ว");
});

/* ---------------- boot ---------------- */
(async function boot() {
  fetch("/health/ready").then(r => {
    const chip = $("#health-chip");
    if (r.ok) { chip.textContent = "● system online"; }
    else { chip.textContent = "● system degraded"; chip.classList.add("down"); }
  }).catch(() => {
    const chip = $("#health-chip");
    chip.textContent = "● offline"; chip.classList.add("down");
  });
  try {
    const r = await fetch(API + "/auth/me");
    if (r.ok) { applyUser((await r.json()).user); return; }
  } catch { /* fall through to login */ }
  showLogin();
})();
