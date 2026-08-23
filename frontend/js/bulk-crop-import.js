// bulk-crop-import.js — Phase 6: นำเข้าพื้นที่เกษตรหลายหมู่บ้านพร้อมกันจากตารางสรุป (admin เท่านั้น)
//
// ที่มา: ก่อนหน้านี้หน้า report.html (ขั้นตอน "2) พืชที่ปลูก") บังคับกรอกได้ทีละหมู่บ้านเท่านั้น (ผูกกับ
// currentVillage ตัวเดียวจาก report.js) — ถ้ามีตารางสรุปพื้นที่เกษตรทั้งตำบลอยู่แล้ว (เช่น สกัดจากชั้นข้อมูล
// Landuse แบบ 1 แถวต่อ 1 หมู่บ้าน หลายคอลัมน์ = พืชแต่ละชนิด) ก็ต้องมานั่งกรอกทีละหมู่ทีละพืชผ่านฟอร์มเดิม
// ทั้งที่ข้อมูลมีพร้อมอยู่แล้ว — ส่วนนี้เปิดให้ upload ไฟล์แบบ "กว้าง" (wide format) 1 ครั้ง แล้ว map
// คอลัมน์ -> ชื่อพืชเอง (ยืดหยุ่นเพราะแต่ละไฟล์ตั้งชื่อคอลัมน์ไม่เหมือนกัน) ก่อนยิงเข้า backend endpoint ใหม่
// POST /crop-reports/bulk (ดู routes.py bulk_create_crop_reports สำหรับ semantics ฝั่ง backend)
//
// ทำงานคู่กับ tabular-import.js (parseWorkbookAllSheetsAOA, guessHeaderRowIndex) และใช้ตัวแปร global `auth`
// จาก report.js (โหลดก่อนไฟล์นี้ใน report.html) เพื่อเช็คสิทธิ์ admin — ไม่ทำอะไรเลยถ้าไม่ใช่ admin

let bulkSheetNames = [];
let bulkSheetsAOA = {}; // {sheetName: AOA} — ไฟล์จริงมักมีหลายแผ่นงาน (เช่น "ข้อมูลดิบ" แบบยาวปนกับ
// "สรุป...รายหมู่บ้าน" แบบ pivot) ให้ผู้ใช้เลือกแผ่นงานที่จะ import เอง แทนที่จะเดา sheet แรกเสมอ
let bulkAoa = null; // raw rows ของแผ่นงานที่เลือกอยู่ (array of array)
let bulkVillages = []; // หมู่บ้านของตำบลที่เลือก [{village_id, moo, name_th, agri_rai, ...}]
let bulkHeaderRowIndex = 0;
let bulkPreviewItems = []; // [{village_id, crop_name, planted_area_rai}] — คำนวณตอนกด "แสดงตัวอย่าง"
let bulkVillageAgriTotals = {}; // village_id -> พื้นที่เกษตรรวมที่จะใช้อัปเดต agri_rai (ถ้าเลือกอัปเดต)

const BULK_SKIP_HEADER_HINTS = ["ชื่อ", "รวม", "ปศุสัตว์", "ประมง", "เพาะเลี้ยง", "โรงเรือน", "หมายเหตุ"];

function bulkInit() {
  if (!auth || auth.role !== "admin") return; // ฟีเจอร์นี้สำหรับ admin เท่านั้น (import ข้ามหมู่บ้านได้)
  document.getElementById("step-bulk-crop").style.display = "block";
  loadBulkTambons();
}

async function loadBulkTambons() {
  const sel = document.getElementById("bulk-crop-tambon");
  try {
    const res = await fetch(BACKEND_URL + "/tambons");
    const tambons = await res.json();
    tambons
      .slice()
      .sort((a, b) => a.name_th.localeCompare(b.name_th, "th"))
      .forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.tambon_id;
        opt.textContent = t.name_th + (t.amphoe_th ? " (" + t.amphoe_th + ")" : "");
        sel.appendChild(opt);
      });
  } catch (err) {
    document.getElementById("bulk-crop-status").textContent = "โหลดรายชื่อตำบลไม่สำเร็จ: " + err.message;
  }
}

document.getElementById("bulk-crop-tambon").addEventListener("change", async (e) => {
  const fileInput = document.getElementById("bulk-crop-file");
  fileInput.disabled = true;
  fileInput.value = "";
  bulkVillages = [];
  resetBulkMapping();
  if (!e.target.value) return;
  const statusEl = document.getElementById("bulk-crop-status");
  statusEl.textContent = "กำลังโหลดรายชื่อหมู่บ้าน...";
  try {
    const res = await fetch(BACKEND_URL + "/villages?tambon_id=" + encodeURIComponent(e.target.value));
    bulkVillages = await res.json();
    statusEl.textContent = "โหลดหมู่บ้านแล้ว " + bulkVillages.length + " หมู่ — เลือกไฟล์ตารางสรุปได้เลย";
    fileInput.disabled = false;
  } catch (err) {
    statusEl.textContent = "โหลดรายชื่อหมู่บ้านไม่สำเร็จ: " + err.message;
  }
});

function resetBulkMapping() {
  bulkAoa = null;
  bulkSheetNames = [];
  bulkSheetsAOA = {};
  document.getElementById("bulk-crop-mapping").style.display = "none";
  document.getElementById("bulk-crop-preview").innerHTML = "";
  document.getElementById("btn-bulk-crop-submit").style.display = "none";
  document.getElementById("bulk-crop-submit-status").textContent = "";
}

document.getElementById("bulk-crop-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("bulk-crop-status");
  statusEl.textContent = "กำลังอ่านไฟล์...";
  try {
    const wb = await parseWorkbookAllSheetsAOA(file);
    bulkSheetNames = wb.sheetNames;
    bulkSheetsAOA = wb.sheetsAOA;
    if (!bulkSheetNames.length) {
      statusEl.textContent = "ไฟล์นี้ไม่มีแผ่นงาน";
      return;
    }

    const sheetSel = document.getElementById("bulk-crop-sheet");
    sheetSel.innerHTML = "";
    // เดาแผ่นงานที่ "น่าจะใช่" จากแถวหัวตารางที่กว้างที่สุด (ตารางแบบ pivot 1 แถว/หมู่บ้านมักมีคอลัมน์เยอะ
    // กว่าตารางแบบยาว 1 แถว/รายการ ที่มักมีแค่ไม่กี่คอลัมน์คงที่) ให้คะแนนพิเศษถ้าชื่อแผ่นงานมีคำว่า "สรุป"
    let bestSheet = bulkSheetNames[0];
    let bestScore = -1;
    bulkSheetNames.forEach((name) => {
      const aoa = bulkSheetsAOA[name];
      const headerIdx = guessHeaderRowIndex(aoa);
      const colCount = (aoa[headerIdx] || []).filter((c) => c !== null && c !== undefined && String(c).trim() !== "").length;
      const score = colCount + (name.includes("สรุป") ? 100 : 0);
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name + " (" + aoa.length + " แถว)";
      sheetSel.appendChild(opt);
      if (score > bestScore) {
        bestScore = score;
        bestSheet = name;
      }
    });
    sheetSel.value = bestSheet;
    statusEl.innerHTML = '<span class="ok">อ่านไฟล์สำเร็จ</span> — ตรวจสอบว่าเลือกแผ่นงาน/แถวหัวตารางถูกต้องด้านล่าง';
    document.getElementById("bulk-crop-mapping").style.display = "block";
    loadBulkSheet(bestSheet);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("bulk-crop-sheet").addEventListener("change", (e) => loadBulkSheet(e.target.value));

function loadBulkSheet(sheetName) {
  bulkAoa = bulkSheetsAOA[sheetName] || [];
  const guessed = guessHeaderRowIndex(bulkAoa);
  const headerSel = document.getElementById("bulk-crop-header-row");
  headerSel.innerHTML = "";
  bulkAoa.slice(0, Math.min(bulkAoa.length, 15)).forEach((row, idx) => {
    const preview = (row || [])
      .filter((c) => c !== null && c !== undefined && String(c).trim() !== "")
      .slice(0, 4)
      .join(" | ");
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = "แถวที่ " + (idx + 1) + ": " + (preview || "(ว่าง)");
    headerSel.appendChild(opt);
  });
  headerSel.value = guessed;
  buildBulkColumnMapping(guessed);
}

document.getElementById("bulk-crop-header-row").addEventListener("change", (e) => {
  buildBulkColumnMapping(parseInt(e.target.value, 10));
});

/** สร้าง UI เลือกคอลัมน์ "หมู่ที่" / คอลัมน์ผลรวม / รายการคอลัมน์พืชที่จะนำเข้า จากแถว header ที่เลือก */
function buildBulkColumnMapping(headerRowIndex) {
  bulkHeaderRowIndex = headerRowIndex;
  const headerRow = bulkAoa[headerRowIndex] || [];
  const sampleRow = bulkAoa[headerRowIndex + 1] || [];
  const columns = [];
  headerRow.forEach((h, idx) => {
    const text = h === null || h === undefined ? "" : String(h).trim();
    if (text) columns.push({ idx, header: text });
  });

  const mooSel = document.getElementById("bulk-crop-moo-col");
  const totalSel = document.getElementById("bulk-crop-total-col");
  mooSel.innerHTML = "";
  totalSel.innerHTML = '<option value="">-- ไม่มี / ไม่ใช้ --</option>';
  columns.forEach((c) => {
    const opt1 = document.createElement("option");
    opt1.value = c.idx;
    opt1.textContent = c.header;
    mooSel.appendChild(opt1);
    const opt2 = document.createElement("option");
    opt2.value = c.idx;
    opt2.textContent = c.header;
    totalSel.appendChild(opt2);
  });

  const mooGuess = columns.find((c) => c.header === "หมู่ที่" || c.header === "หมู่") || columns.find((c) => c.header.includes("หมู่") && !c.header.includes("ชื่อ"));
  if (mooGuess) mooSel.value = mooGuess.idx;
  const totalGuess = columns.find((c) => c.header.includes("รวม"));
  if (totalGuess) totalSel.value = totalGuess.idx;

  renderBulkColumnCheckboxes(columns, sampleRow);
  mooSel.onchange = () => renderBulkColumnCheckboxes(columns, sampleRow);
  totalSel.onchange = () => renderBulkColumnCheckboxes(columns, sampleRow);
}

function renderBulkColumnCheckboxes(columns, sampleRow) {
  const mooIdx = parseInt(document.getElementById("bulk-crop-moo-col").value, 10);
  const totalIdx = document.getElementById("bulk-crop-total-col").value
    ? parseInt(document.getElementById("bulk-crop-total-col").value, 10)
    : null;
  const container = document.getElementById("bulk-crop-column-mapping");
  container.innerHTML = "";
  columns
    .filter((c) => c.idx !== mooIdx && c.idx !== totalIdx)
    .forEach((c) => {
      const sample = sampleRow[c.idx];
      const shouldDefaultCheck = !BULK_SKIP_HEADER_HINTS.some((hint) => c.header.includes(hint));
      const row = document.createElement("div");
      row.className = "bulk-col-row";
      row.dataset.colIdx = c.idx;
      row.innerHTML =
        '<input type="checkbox" class="bulk-col-include" ' + (shouldDefaultCheck ? "checked" : "") + '>' +
        '<span class="col-header">' + c.header + "</span>" +
        '<span class="col-sample">ตัวอย่าง: ' + (sample === null || sample === undefined ? "-" : sample) + "</span>" +
        '<input type="text" class="bulk-col-crop-name" value="' + c.header.replace(/"/g, "&quot;") + '">';
      container.appendChild(row);
    });
}

document.getElementById("btn-bulk-crop-preview").addEventListener("click", () => {
  const statusEl = document.getElementById("bulk-crop-status");
  const previewEl = document.getElementById("bulk-crop-preview");
  const submitBtn = document.getElementById("btn-bulk-crop-submit");
  submitBtn.style.display = "none";
  document.getElementById("bulk-crop-submit-status").textContent = "";

  const mooIdx = parseInt(document.getElementById("bulk-crop-moo-col").value, 10);
  if (isNaN(mooIdx)) {
    statusEl.textContent = "กรุณาเลือกคอลัมน์ที่เป็น \"หมู่ที่\" ก่อน";
    return;
  }
  const totalColRaw = document.getElementById("bulk-crop-total-col").value;
  const totalIdx = totalColRaw ? parseInt(totalColRaw, 10) : null;

  const colRows = Array.from(document.querySelectorAll("#bulk-crop-column-mapping .bulk-col-row"))
    .map((row) => ({
      idx: parseInt(row.dataset.colIdx, 10),
      include: row.querySelector(".bulk-col-include").checked,
      cropName: row.querySelector(".bulk-col-crop-name").value.trim(),
    }))
    .filter((c) => c.include && c.cropName);

  if (!colRows.length) {
    statusEl.textContent = "กรุณาเลือกอย่างน้อย 1 คอลัมน์ที่จะนำเข้าเป็นพืช";
    return;
  }

  const dataRows = bulkAoa.slice(bulkHeaderRowIndex + 1);
  bulkPreviewItems = [];
  bulkVillageAgriTotals = {};
  const matchedVillageRows = [];
  const unmatchedMoo = [];

  dataRows.forEach((row) => {
    if (!row) return;
    const mooRaw = row[mooIdx];
    if (mooRaw === null || mooRaw === undefined || String(mooRaw).trim() === "") return;
    const moo = Math.round(parseFloat(mooRaw));
    if (isNaN(moo)) return; // ข้ามแถวสรุปท้ายตาราง เช่น "รวมทั้งตำบล" ที่ไม่มีเลขหมู่
    const village = bulkVillages.find((v) => v.moo === moo);
    if (!village) {
      unmatchedMoo.push(moo);
      return;
    }
    let sumIncluded = 0;
    const cropsForVillage = [];
    colRows.forEach((c) => {
      const raw = row[c.idx];
      if (raw === null || raw === undefined || raw === "") return;
      const num = parseFloat(raw);
      if (isNaN(num) || num <= 0) return;
      bulkPreviewItems.push({ village_id: village.village_id, crop_name: c.cropName, planted_area_rai: num });
      cropsForVillage.push(c.cropName + " (" + num.toLocaleString("th-TH") + " ไร่)");
      sumIncluded += num;
    });
    const fileTotal = totalIdx !== null ? parseFloat(row[totalIdx]) : NaN;
    bulkVillageAgriTotals[village.village_id] = !isNaN(fileTotal) ? fileTotal : sumIncluded;
    matchedVillageRows.push({ village, crops: cropsForVillage, total: bulkVillageAgriTotals[village.village_id] });
  });

  if (!bulkPreviewItems.length) {
    statusEl.textContent = "ไม่พบข้อมูลที่นำเข้าได้ — ตรวจสอบการเลือกคอลัมน์และแถวหัวตารางอีกครั้ง";
    return;
  }

  const totalArea = bulkPreviewItems.reduce((s, r) => s + r.planted_area_rai, 0);
  let html =
    '<p class="ok">พร้อมนำเข้า ' + bulkPreviewItems.length + " รายการ (" + matchedVillageRows.length +
    " หมู่บ้าน, รวมพื้นที่ " + totalArea.toLocaleString("th-TH", { maximumFractionDigits: 2 }) + " ไร่)</p>";
  if (unmatchedMoo.length) {
    html +=
      '<p class="fail">หาหมู่บ้านไม่พบสำหรับหมู่ที่: ' + unmatchedMoo.join(", ") +
      " (ตรวจว่าเลือกตำบลถูกต้อง หรือหมู่บ้านนั้นยังไม่ถูกสร้างในระบบ) — แถวเหล่านี้จะไม่ถูกนำเข้า</p>";
  }
  html +=
    "<table><thead><tr><th>หมู่</th><th>หมู่บ้าน</th><th>พืชที่จะนำเข้า</th><th>รวม (ไร่)</th></tr></thead><tbody>" +
    matchedVillageRows
      .map(
        (r) =>
          "<tr><td>" + r.village.moo + "</td><td>" + r.village.name_th + "</td><td>" + (r.crops.join(", ") || "-") +
          "</td><td>" + r.total.toLocaleString("th-TH", { maximumFractionDigits: 2 }) + "</td></tr>"
      )
      .join("") +
    "</tbody></table>";
  previewEl.innerHTML = html;
  statusEl.textContent = "";
  submitBtn.style.display = "inline-block";
});

document.getElementById("btn-bulk-crop-submit").addEventListener("click", async () => {
  const statusEl = document.getElementById("bulk-crop-submit-status");
  const submitBtn = document.getElementById("btn-bulk-crop-submit");
  const monthValue = document.getElementById("report-month").value; // ใช้ตัวเลือกเดือนร่วมกับขั้นตอนที่ 1 ด้านล่าง
  if (!monthValue) {
    statusEl.innerHTML = '<span class="fail">กรุณาเลือก "เดือนที่รายงาน" ในขั้นตอนที่ 1 ด้านล่างก่อน</span>';
    return;
  }
  if (!bulkPreviewItems.length) {
    statusEl.innerHTML = '<span class="fail">กรุณากด "แสดงตัวอย่างก่อนบันทึก" ก่อน</span>';
    return;
  }
  const monthDate = monthValue + "-01";
  const replaceExisting = document.getElementById("bulk-crop-replace").checked;
  const updateAgri = document.getElementById("bulk-crop-agri-update").checked;

  submitBtn.disabled = true;
  try {
    if (updateAgri) {
      statusEl.textContent = "กำลังอัปเดตพื้นที่เกษตรทั้งหมู่บ้าน...";
      const villageIds = Object.keys(bulkVillageAgriTotals);
      for (const villageId of villageIds) {
        const res = await authFetch("/villages/" + villageId, {
          method: "PATCH",
          body: JSON.stringify({ agri_rai: bulkVillageAgriTotals[villageId] }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error((body.detail || "อัปเดตพื้นที่เกษตรไม่สำเร็จ") + " (village_id " + villageId + ")");
      }
    }
    statusEl.textContent = "กำลังบันทึกรายงานพืช...";
    const res = await authFetch("/crop-reports/bulk", {
      method: "POST",
      body: JSON.stringify({ reported_month: monthDate, items: bulkPreviewItems, replace_existing: replaceExisting }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกไม่สำเร็จ");
    let html =
      '<span class="ok">นำเข้าสำเร็จ ✓ (' + body.length + " รายการ" +
      (updateAgri ? ", อัปเดตพื้นที่เกษตรแล้ว" : "") + ")</span>";
    const uniqueWarnings = [...new Set(body.map((r) => r.unmapped_crop_warning).filter(Boolean))];
    if (uniqueWarnings.length) {
      html += '<div class="fail" style="margin-top:0.5rem;">⚠ ' + uniqueWarnings.join("<br>⚠ ") + "</div>";
    }
    statusEl.innerHTML = html;
    document.getElementById("btn-bulk-crop-submit").style.display = "none";
    // ถ้าหมู่บ้านที่กำลังเลือกอยู่ในขั้นตอนที่ 1 อยู่ในชุดที่เพิ่ง import ไป ให้รีเฟรชตารางที่แสดงอยู่ด้วย
    if (typeof currentVillage !== "undefined" && currentVillage && bulkVillageAgriTotals[currentVillage.village_id] !== undefined) {
      if (typeof loadExistingReports === "function") loadExistingReports();
    }
  } catch (err) {
    statusEl.innerHTML = '<span class="fail">บันทึกไม่สำเร็จ: ' + err.message + "</span>";
  } finally {
    submitBtn.disabled = false;
  }
});

if (typeof auth !== "undefined") bulkInit();
