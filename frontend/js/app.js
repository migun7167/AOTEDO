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

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.code || res.statusText);
  return data;
}
function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- router ---------------- */
const routes = { dashboard: renderDashboard, import: renderImport, matches: renderMatches, rawdata: renderRawData };
const titles = { dashboard: "Dashboard", import: "Import Messages", matches: "Match Results", rawdata: "Raw Data / Analysis" };

function navigate() {
  const hash = location.hash.replace(/^#\//, "") || "dashboard";
  const [route, qs] = hash.split("?");
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
    origin: "", destination: "", reviewed: "", page: 1,
  };
  const v = $("#view");
  v.innerHTML = `
    <div class="panel">
      <div class="filter-bar">
        <input type="search" id="m-search" placeholder="MAWB / HAWB / Shipper / Flight…" value="${esc(state.search)}" style="width:260px">
        <select id="m-status">
          <option value="">ทุกสถานะ</option>
          ${Object.keys(STATUS_META).filter(s => !["PARSED"].includes(s)).map(s =>
            `<option value="${s}" ${state.status === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <input type="text" id="m-origin" placeholder="Origin เช่น HKG" style="width:120px" maxlength="3">
        <input type="text" id="m-dest" placeholder="Dest เช่น BKK" style="width:120px" maxlength="3">
        <select id="m-reviewed">
          <option value="">Reviewed: ทั้งหมด</option>
          <option value="true">Reviewed</option><option value="false">Unreviewed</option>
        </select>
        <button class="btn primary sm" id="m-apply">Apply</button>
        <div class="spacer"></div>
        <a class="btn sm" href="${API}/data/matching_results/export" download>⇓ Export CSV</a>
      </div>
      <div id="m-table"></div>
    </div>`;

  async function load() {
    state.search = $("#m-search").value.trim();
    state.status = $("#m-status").value;
    state.origin = $("#m-origin").value.trim();
    state.destination = $("#m-dest").value.trim();
    state.reviewed = $("#m-reviewed").value;
    const q = new URLSearchParams({
      page: state.page, pageSize: 25, search: state.search, status: state.status,
      origin: state.origin, destination: state.destination, reviewed: state.reviewed,
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
            <td>${badge(r.match_status)}</td>
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
  load();
}

/* ---------------- match detail modal ---------------- */
window.openDetail = async function (mawb) {
  let d;
  try { d = await api("/matches/" + encodeURIComponent(mawb)); }
  catch (e) { toast(e.message, true); return; }
  const r = d.result;
  const fwb = d.fwb;

  const tabs = ["Overview", "Houses", "Comparison", "Raw", "Parsed", "History"];
  $("#modal-root").innerHTML = `
    <div class="modal-back" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <div class="modal-head">
          <h2>MAWB <span class="mono">${esc(mawb)}</span></h2>
          ${badge(r.match_status)} <span class="score-pill" style="background:rgba(255,255,255,.15);color:#ffe9a8">${r.match_score}</span>
          <button class="btn sm" style="margin-left:14px" onclick="doRematch('${esc(mawb)}')">↻ Re-match</button>
          <button class="btn sm" onclick="doReview('${esc(mawb)}')">${r.reviewed ? "✓ Reviewed" : "Mark reviewed"}</button>
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
    Houses: () => d.houses.length ? `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>HAWB</th><th>Shipper</th><th>Consignee</th><th>Commodity</th>
          <th class="num">Pieces</th><th class="num">Weight</th><th>HS Code</th><th>Tax ID</th></tr></thead>
        <tbody>${d.houses.map(h => `
          <tr><td class="mono"><b>${esc(h.hawb_number)}</b></td>
            <td>${esc(h.shipper_name || "—")}</td><td>${esc(h.consignee_name || "—")}</td>
            <td>${esc(h.commodity || "—")}</td>
            <td class="num">${h.pieces ?? "—"}</td>
            <td class="num">${fmtW(h.gross_weight)} ${esc(h.weight_unit || "")}</td>
            <td class="mono">${esc(h.hs_code || "—")}</td>
            <td class="mono">${esc(h.consignee_tax_id || "—")}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">ยังไม่มี FHL สำหรับ MAWB นี้</div>`,
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
  const show = (t) => { body.innerHTML = render[t](); };
  $$("#d-tabs button").forEach(b => b.onclick = () => {
    $$("#d-tabs button").forEach(x => x.classList.toggle("active", x === b));
    show(b.dataset.t);
  });
  show("Overview");
};
const kv = (k, v) => `<div class="item"><div class="k">${esc(k)}</div><div class="v">${v ?? "—"}</div></div>`;
window.closeModal = () => { $("#modal-root").innerHTML = ""; };
window.toastCopy = () => toast("คัดลอกแล้ว");
window.doRematch = async (mawb) => {
  try {
    const r = await api(`/matches/${encodeURIComponent(mawb)}/rematch`, { method: "POST" });
    toast(`Re-match แล้ว: ${r.status} (score ${r.score})`);
    openDetail(mawb);
  } catch (e) { toast(e.message, true); }
};
window.doReview = async (mawb) => {
  const note = prompt("หมายเหตุการ review (ไม่บังคับ):") ?? "";
  try {
    await api(`/matches/${encodeURIComponent(mawb)}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed: true, note, reviewer: "operator" }),
    });
    toast("Mark as reviewed แล้ว");
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

/* ---------------- boot ---------------- */
(function boot() {
  fetch("/health/ready").then(r => {
    const chip = $("#health-chip");
    if (r.ok) { chip.textContent = "● system online"; }
    else { chip.textContent = "● system degraded"; chip.classList.add("down"); }
  }).catch(() => {
    const chip = $("#health-chip");
    chip.textContent = "● offline"; chip.classList.add("down");
  });
  navigate();
})();
