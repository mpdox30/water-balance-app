// data-completeness.js — แดชบอร์ดความครบถ้วนข้อมูล (future-tambon-onboarding-plan.md ขั้นตอนที่ 8)
// อ่านจาก GET /data-completeness?tambon_id=... (backend/routes.py) — ไม่มีการเขียนข้อมูลใดๆ ในหน้านี้
// เป็นหน้าเฉพาะ admin (เกณฑ์เขียว/เหลือง/แดง อิงตารางข้อ 2 ของเอกสารเดียวกัน)

const auth = requireAdmin();
if (auth) {
  document.getElementById("whoami").textContent =
    (auth.display_name || auth.username || "admin") + " (admin)";
}

const STATUS_LABEL = { green: "ครบ", yellow: "บางส่วน", red: "ยังไม่มี" };

function statusCellHtml(cat) {
  const dot = `<span class="dot dot-${cat.status}"></span>`;
  const label = STATUS_LABEL[cat.status] || cat.status;
  const detail = cat.detail ? `<span class="cell-detail">${escapeHtml(cat.detail)}</span>` : "";
  return `<span class="cell-status">${dot}${label}</span>${detail}`;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

// ---------- โหลดรายชื่อตำบล ----------
(async () => {
  try {
    const res = await fetch(BACKEND_URL + "/tambons");
    const tambons = await res.json();
    const sel = document.getElementById("sel-tambon-c");
    tambons.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.tambon_id;
      opt.textContent = `${t.name_th} (อ.${t.amphoe_th} จ.${t.province_th})`;
      sel.appendChild(opt);
    });
  } catch (err) {
    document.getElementById("load-status").textContent = "โหลดรายชื่อตำบลไม่สำเร็จ: " + err.message;
    document.getElementById("load-status").className = "fail";
  }
})();

document.getElementById("sel-tambon-c").addEventListener("change", async (e) => {
  const tambonId = e.target.value;
  const statusEl = document.getElementById("load-status");
  const resultSection = document.getElementById("result-section");
  if (!tambonId) {
    resultSection.style.display = "none";
    statusEl.textContent = "";
    return;
  }
  statusEl.textContent = "กำลังโหลด...";
  statusEl.className = "muted";
  try {
    const res = await fetch(BACKEND_URL + "/data-completeness?tambon_id=" + encodeURIComponent(tambonId));
    if (!res.ok) throw new Error("โหลดข้อมูลไม่สำเร็จ (HTTP " + res.status + ")");
    const data = await res.json();
    renderCompleteness(data);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "โหลดข้อมูลไม่สำเร็จ: " + err.message;
    statusEl.className = "fail";
    resultSection.style.display = "none";
  }
});

function renderCompleteness(data) {
  document.getElementById("result-section").style.display = "";
  document.getElementById("result-heading").textContent = "ตำบล" + data.tambon_name;

  document.getElementById("summary-villages-green").textContent =
    `${data.villages_green} / ${data.total_villages}`;

  const resDot = `<span class="dot dot-${data.reservoir.status}"></span>`;
  document.getElementById("summary-reservoir").innerHTML =
    `${resDot}${data.reservoir.reservoirs_with_usage} / ${data.reservoir.total_reservoirs} แห่ง`;
  document.getElementById("summary-reservoir-detail").textContent = data.reservoir.detail || "";

  const gateEl = document.getElementById("summary-gate");
  if (data.can_compute_balance) {
    gateEl.textContent = "พร้อมคำนวณ ✓";
    gateEl.className = "summary-num gate-ready";
  } else {
    gateEl.textContent = "ยังไม่พร้อม";
    gateEl.className = "summary-num gate-blocked";
  }

  const tbody = document.getElementById("completeness-tbody");
  tbody.innerHTML = "";
  data.villages.forEach((v) => {
    const tr = document.createElement("tr");
    tr.className = "overall-" + v.overall_status;
    tr.innerHTML = `
      <td>${escapeHtml(v.moo)}</td>
      <td>${escapeHtml(v.name_th)}</td>
      <td>${statusCellHtml(v.village_info)}</td>
      <td>${statusCellHtml(v.boundary)}</td>
      <td>${statusCellHtml(v.water_supply)}</td>
      <td>${statusCellHtml(v.crop)}</td>
      <td>${statusCellHtml(v.livestock)}</td>
    `;
    tbody.appendChild(tr);
  });
}
