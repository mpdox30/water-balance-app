// report.js — Phase 4: ฟอร์มรายงานพืช/ปศุสัตว์รายเดือนของตัวแทนหมู่บ้าน
// หลักการ:
// - village_rep ผูก village_id อัตโนมัติจาก JWT (login.village_id) ไม่มีช่องเลือกหมู่บ้านเอง
// - admin login เข้ามาหน้านี้ได้เหมือนกัน (backend อนุญาต — check_can_write_village) เลยเปิดช่อง
//   เลือกตำบล/หมู่บ้านให้ เพื่อให้ admin ทดสอบฟอร์มเองได้ก่อนมีบัญชี village_rep จริง (ตามที่คุยกันไว้)
// - backend ยังไม่มี endpoint แก้ไข/ลบรายงาน (มีแค่ POST สร้างใหม่) จึงกันข้อมูลซ้ำด้วยการ block
//   ไม่ให้ส่งพืช/สัตว์ชนิดเดียวกันซ้ำในเดือนเดียวกัน (ต้องติดต่อ admin ถ้ากรอกผิดจริงๆ)
// - ตรวจพื้นที่ปลูกรวมไม่ให้เกินพื้นที่เกษตรทั้งหมู่บ้าน (agri_rai) แบบ "ห้าม" (block จริง ไม่ใช่แค่เตือน)
//   ตามที่ระบุใน 01-phased-work-plan.md Phase 4 — ต่างจาก validation ขอบเขต geometry ใน Phase 3 ที่เป็น
//   แค่ soft-warning เพราะอันนั้นเป็นความคลาดเคลื่อนของการวัดพื้นที่จริง แต่นี่เป็นกฎเลขคณิตตรงไปตรงมา

const auth = requireAuth();
if (auth) {
  const roleLabel = auth.role === "admin" ? "admin" : "ตัวแทนหมู่บ้าน";
  document.getElementById("whoami").textContent = (auth.display_name || auth.username || "") + " (" + roleLabel + ")";
}

const LIVESTOCK_SPECIES = ["โคเนื้อ", "โคนม", "กระบือ", "สุกร", "ไก่", "เป็ด", "ห่าน", "แพะ", "แกะ"];

// ค่า sentinel แทน "ยืนยันแล้วว่าไม่มีปศุสัตว์เดือนนี้" — ใช้ endpoint POST /livestock-reports เดิม
// (species=ค่านี้, head_count=0) แทนที่จะเพิ่ม backend/DB ใหม่ เพราะ backend ยังไม่มีสถานะ "ยืนยันว่าไม่มี"
// แยกจาก "ยังไม่ได้รายงาน" เลย — การไม่มีแถวใดๆ ใน livestock_report เดือนนั้นแปลได้ 2 อย่าง (ไม่มีจริง
// หรือลืมกรอก) การมี sentinel row ทำให้แยกออกจากกันได้ชัดเจนโดยไม่ต้องแก้ schema/backend
// **สำคัญ: ถ้าจะทำ Phase 5 (balance engine) ต่อ ต้อง filter แถว species=NO_LIVESTOCK_SENTINEL ออกก่อน
// เอาไปคำนวณความต้องการน้ำปศุสัตว์ ไม่งั้นจะนับเป็นสัตว์ชนิดหนึ่งที่มี head_count=0 (ไม่ผิดเชิงตัวเลข
// แต่ไม่ควรโผล่ในรายงาน/dashboard เป็นชื่อชนิดสัตว์)**
const NO_LIVESTOCK_SENTINEL = "ไม่มีปศุสัตว์";

let currentVillage = null; // { village_id, moo, name_th, agri_rai, ... }
let reportMonthValue = ""; // "YYYY-MM"
let existingCrops = [];
let existingLivestock = [];
let cropRowCounter = 0;
let livestockRowCounter = 0;

document.getElementById("step-done").classList.add("active"); // แค่ข้อมูล/ลิงก์กลับ ไม่ต้อง gate

// ---------- เลือกหมู่บ้าน ----------

async function initVillageSelection() {
  if (auth.role === "admin") {
    document.getElementById("admin-village-picker").style.display = "block";
    try {
      const res = await fetch(BACKEND_URL + "/tambons");
      const tambons = await res.json();
      const sel = document.getElementById("sel-tambon-r");
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
      document.getElementById("village-month-status").textContent = "โหลดรายชื่อตำบลไม่สำเร็จ: " + err.message;
    }
  } else {
    // village_rep — ผูกหมู่บ้านอัตโนมัติจาก JWT ไม่ต้องเลือกเอง
    if (!auth.village_id) {
      document.getElementById("village-info").innerHTML =
        '<span class="fail">บัญชีนี้ไม่ได้ผูกกับหมู่บ้านใดเลย — กรุณาติดต่อ admin เพื่อแก้ไขบัญชี</span>';
      return;
    }
    try {
      const res = await authFetch("/villages/" + auth.village_id);
      const village = await res.json();
      if (!res.ok) throw new Error(village.detail || "โหลดข้อมูลหมู่บ้านไม่สำเร็จ");
      setCurrentVillage(village);
    } catch (err) {
      document.getElementById("village-info").innerHTML =
        '<span class="fail">โหลดข้อมูลหมู่บ้านไม่สำเร็จ: ' + err.message + "</span>";
    }
  }
}

document.getElementById("sel-tambon-r").addEventListener("change", async (e) => {
  const selVillage = document.getElementById("sel-village-r");
  selVillage.innerHTML = '<option value="">-- เลือกหมู่บ้าน --</option>';
  selVillage.disabled = true;
  currentVillage = null;
  refreshFormGating();
  if (!e.target.value) return;
  try {
    const res = await fetch(BACKEND_URL + "/villages?tambon_id=" + encodeURIComponent(e.target.value));
    const villages = await res.json();
    villages
      .slice()
      .sort((a, b) => a.moo - b.moo)
      .forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v.village_id;
        opt.textContent = "หมู่ " + v.moo + " " + v.name_th;
        opt.dataset.village = JSON.stringify(v);
        selVillage.appendChild(opt);
      });
    selVillage.disabled = false;
  } catch (err) {
    document.getElementById("village-month-status").textContent = "โหลดรายชื่อหมู่บ้านไม่สำเร็จ: " + err.message;
  }
});

document.getElementById("sel-village-r").addEventListener("change", (e) => {
  const opt = e.target.selectedOptions[0];
  if (!opt || !opt.dataset.village) {
    currentVillage = null;
    refreshFormGating();
    return;
  }
  setCurrentVillage(JSON.parse(opt.dataset.village));
});

function setCurrentVillage(village) {
  currentVillage = village;
  const agriText =
    village.agri_rai !== null && village.agri_rai !== undefined
      ? village.agri_rai.toLocaleString("th-TH") + " ไร่"
      : "ไม่มีข้อมูล (จะไม่ตรวจสอบพื้นที่รวมเกิน)";
  document.getElementById("village-info").innerHTML =
    "หมู่ " + village.moo + " " + village.name_th + " — พื้นที่เกษตรทั้งหมู่บ้าน: <strong>" + agriText + "</strong>";
  refreshFormGating();
}

// ---------- เดือนที่รายงาน ----------

(function initMonthPicker() {
  const monthInput = document.getElementById("report-month");
  const today = new Date();
  const defaultMonth = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0");
  monthInput.value = defaultMonth;
  reportMonthValue = defaultMonth;
  monthInput.addEventListener("change", (e) => {
    reportMonthValue = e.target.value;
    refreshFormGating();
  });
})();

function refreshFormGating() {
  const ready = !!(currentVillage && reportMonthValue);
  document.getElementById("step-crop").classList.toggle("active", ready);
  document.getElementById("step-livestock").classList.toggle("active", ready);
  if (ready) {
    loadExistingReports();
  }
}

async function loadExistingReports() {
  const statusEl = document.getElementById("village-month-status");
  statusEl.textContent = "กำลังโหลดรายงานที่ส่งไปแล้ว...";
  document.getElementById("crop-carry-note").textContent = "";
  document.getElementById("livestock-carry-note").textContent = "";
  const monthDate = reportMonthValue + "-01";
  try {
    const [cropRes, livestockRes] = await Promise.all([
      fetch(BACKEND_URL + "/crop-reports?village_id=" + encodeURIComponent(currentVillage.village_id) + "&month=" + monthDate),
      fetch(BACKEND_URL + "/livestock-reports?village_id=" + encodeURIComponent(currentVillage.village_id) + "&month=" + monthDate),
    ]);
    existingCrops = await cropRes.json();
    existingLivestock = await livestockRes.json();
    statusEl.textContent = "";
    renderExistingCrops();
    renderExistingLivestock();
    await maybeCarryForwardFromPreviousMonth();
  } catch (err) {
    statusEl.textContent = "โหลดรายงานที่ส่งไปแล้วไม่สำเร็จ: " + err.message;
  }
}

/** "YYYY-MM" ของเดือนก่อนหน้า "YYYY-MM" ที่ให้มา */
function previousMonthOf(monthStr) {
  const [y, m] = monthStr.split("-").map(Number);
  const d = new Date(y, m - 2, 1); // เดือนใน Date ของ JS นับ 0 = ม.ค. ดังนั้น m-2 คือเดือนก่อนหน้า
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
}

/** ดึงรายงานพืช/ปศุสัตว์ของเดือนก่อนหน้ามา pre-fill ให้อัตโนมัติ ถ้าเดือนที่กำลังดูอยู่ยังไม่มีใครกรอกเลย
 * (ลดภาระพิมพ์ซ้ำทุกเดือนสำหรับพืช/สัตว์ที่ยังปลูก/เลี้ยงต่อเนื่อง — ผู้ใช้แค่ตรวจสอบ/แก้ตัวเลขแล้วกดบันทึก
 * ไม่ได้ auto-submit ให้เอง เพื่อไม่ให้มีข้อมูลที่ไม่ได้ยืนยันหลุดเข้าระบบ) ถ้าดึงเดือนก่อนไม่สำเร็จก็แค่
 * ไม่ pre-fill ให้ ไม่ block การกรอกใหม่ตามปกติ */
async function maybeCarryForwardFromPreviousMonth() {
  if (existingCrops.length || existingLivestock.length) return; // เดือนนี้มีรายงานอยู่แล้ว ไม่ต้อง carry-forward ทับ
  const prevMonthLabel = previousMonthOf(reportMonthValue);
  const prevMonthDate = prevMonthLabel + "-01";
  try {
    const [cropRes, livestockRes] = await Promise.all([
      fetch(BACKEND_URL + "/crop-reports?village_id=" + encodeURIComponent(currentVillage.village_id) + "&month=" + prevMonthDate),
      fetch(BACKEND_URL + "/livestock-reports?village_id=" + encodeURIComponent(currentVillage.village_id) + "&month=" + prevMonthDate),
    ]);
    const prevCrops = await cropRes.json();
    const prevLivestock = (await livestockRes.json()).filter((l) => l.species !== NO_LIVESTOCK_SENTINEL);

    if (prevCrops.length) {
      document.getElementById("crop-rows").innerHTML = "";
      prevCrops.forEach((c) => addCropRow(c.crop_name, c.planted_area_rai));
      document.getElementById("crop-carry-note").textContent =
        "ดึงรายการจากเดือน " + prevMonthLabel + " มาให้อัตโนมัติ — ตรวจสอบ/แก้ตัวเลขแล้วกดบันทึกได้เลย " +
        "(หรือลบแถวที่ไม่ปลูกแล้วออกก่อนบันทึก)";
    }
    if (prevLivestock.length) {
      document.getElementById("livestock-rows").innerHTML = "";
      prevLivestock.forEach((l) => addLivestockRow(l.species, l.head_count));
      document.getElementById("livestock-carry-note").textContent =
        "ดึงรายการจากเดือน " + prevMonthLabel + " มาให้อัตโนมัติ — ตรวจสอบ/แก้จำนวนแล้วกดบันทึกได้เลย " +
        "(หรือลบแถวที่ไม่มีแล้วออกก่อนบันทึก)";
    }
  } catch (err) {
    // เงียบๆ พอ — carry-forward เป็นแค่ตัวช่วย ไม่ใช่ขั้นตอนบังคับ
  }
}

function renderExistingCrops() {
  const el = document.getElementById("crop-existing");
  if (!existingCrops.length) {
    el.innerHTML = '<p class="muted">ยังไม่มีรายงานพืชของเดือนนี้</p>';
    return;
  }
  const rows = existingCrops
    .map((c) => "<tr><td>" + c.crop_name + "</td><td>" + c.planted_area_rai.toLocaleString("th-TH") + " ไร่</td></tr>")
    .join("");
  const total = existingCrops.reduce((s, c) => s + c.planted_area_rai, 0);
  el.innerHTML =
    '<p class="muted already-note">รายงานพืชที่ส่งไปแล้วเดือนนี้ (รวม ' + total.toLocaleString("th-TH") + " ไร่):</p>" +
    "<table><thead><tr><th>พืช</th><th>พื้นที่ปลูก</th></tr></thead><tbody>" + rows + "</tbody></table>";
}

function hasNoLivestockConfirmed() {
  return existingLivestock.some((l) => l.species === NO_LIVESTOCK_SENTINEL);
}

function renderExistingLivestock() {
  const el = document.getElementById("livestock-existing");
  const noLivestockBtn = document.getElementById("btn-no-livestock");
  const addRowBtn = document.getElementById("btn-add-livestock-row");
  const submitBtn = document.getElementById("btn-submit-livestock");

  if (hasNoLivestockConfirmed()) {
    el.innerHTML = '<p class="ok already-note">ยืนยันแล้วว่าหมู่บ้านนี้ไม่มีปศุสัตว์เดือนนี้ ✓ ' +
      "(ถ้าข้อมูลเปลี่ยนไป กรุณาติดต่อ admin)</p>";
    noLivestockBtn.disabled = true;
    noLivestockBtn.textContent = "ยืนยันแล้วว่าไม่มีปศุสัตว์เดือนนี้ ✓";
    addRowBtn.disabled = true;
    submitBtn.disabled = true;
    return;
  }
  noLivestockBtn.disabled = false;
  noLivestockBtn.textContent = "หมู่บ้านนี้ไม่มีปศุสัตว์เดือนนี้ (ยืนยัน)";
  addRowBtn.disabled = false;
  submitBtn.disabled = false;

  const realEntries = existingLivestock.filter((l) => l.species !== NO_LIVESTOCK_SENTINEL);
  if (!realEntries.length) {
    el.innerHTML = '<p class="muted">ยังไม่มีรายงานปศุสัตว์ของเดือนนี้</p>';
    return;
  }
  const rows = realEntries
    .map((l) => "<tr><td>" + l.species + "</td><td>" + l.head_count.toLocaleString("th-TH") + " ตัว</td></tr>")
    .join("");
  el.innerHTML =
    '<p class="muted already-note">รายงานปศุสัตว์ที่ส่งไปแล้วเดือนนี้:</p>' +
    "<table><thead><tr><th>ชนิด</th><th>จำนวน</th></tr></thead><tbody>" + rows + "</tbody></table>";
}

document.getElementById("btn-no-livestock").addEventListener("click", async () => {
  if (!currentVillage || !reportMonthValue) return;
  const statusEl = document.getElementById("livestock-submit-status");
  const btn = document.getElementById("btn-no-livestock");
  statusEl.textContent = "";
  btn.disabled = true;
  try {
    const res = await authFetch("/livestock-reports", {
      method: "POST",
      body: JSON.stringify({
        village_id: currentVillage.village_id,
        species: NO_LIVESTOCK_SENTINEL,
        head_count: 0,
        reported_month: reportMonthValue + "-01",
      }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกไม่สำเร็จ");
    await loadExistingReports();
  } catch (err) {
    statusEl.innerHTML = '<span class="fail">บันทึกไม่สำเร็จ: ' + err.message + "</span>";
    btn.disabled = false;
  }
});

// ---------- แถวเพิ่มพืช ----------

function addCropRow(prefillName, prefillArea) {
  cropRowCounter += 1;
  const id = "crop-row-" + cropRowCounter;
  const div = document.createElement("div");
  div.className = "row-group";
  div.id = id;
  div.innerHTML =
    '<div><label>ชื่อพืช</label><input type="text" class="crop-name-input" list="crop-name-suggestions" placeholder="เช่น ข้าว"></div>' +
    '<div><label>พื้นที่ปลูก โดยประมาณ (ไร่)</label><input type="number" class="crop-area-input" min="0" step="0.01"></div>' +
    '<button type="button" class="secondary remove-row">ลบ</button>';
  if (prefillName) div.querySelector(".crop-name-input").value = prefillName;
  if (prefillArea !== undefined && prefillArea !== null) div.querySelector(".crop-area-input").value = prefillArea;
  div.querySelector(".remove-row").addEventListener("click", () => div.remove());
  document.getElementById("crop-rows").appendChild(div);
}
document.getElementById("btn-add-crop-row").addEventListener("click", () => addCropRow());
addCropRow(); // เริ่มด้วย 1 แถวว่างให้กรอกทันที

document.getElementById("btn-submit-crops").addEventListener("click", async () => {
  const validationEl = document.getElementById("crop-validation");
  const statusEl = document.getElementById("crop-submit-status");
  validationEl.textContent = "";
  statusEl.textContent = "";

  const rows = Array.from(document.querySelectorAll("#crop-rows .row-group"))
    .map((div) => ({
      crop_name: div.querySelector(".crop-name-input").value.trim(),
      planted_area_rai: parseFloat(div.querySelector(".crop-area-input").value),
    }))
    .filter((r) => r.crop_name || !isNaN(r.planted_area_rai));

  if (!rows.length) {
    validationEl.textContent = "กรุณากรอกอย่างน้อย 1 รายการ";
    return;
  }
  for (const r of rows) {
    if (!r.crop_name || isNaN(r.planted_area_rai) || r.planted_area_rai < 0) {
      validationEl.textContent = "กรุณากรอกชื่อพืชและพื้นที่ปลูก (ตัวเลข ≥ 0) ให้ครบทุกแถว";
      return;
    }
  }

  // กันชื่อพืชซ้ำกันเองในแถวที่กำลังจะส่ง
  const seenInBatch = new Set();
  for (const r of rows) {
    const key = r.crop_name.toLowerCase();
    if (seenInBatch.has(key)) {
      validationEl.textContent = 'มีพืชชื่อ "' + r.crop_name + '" ซ้ำกันในแบบฟอร์มนี้ — กรุณารวมเป็นแถวเดียว';
      return;
    }
    seenInBatch.add(key);
  }

  // กันซ้ำกับที่ส่งไปแล้วเดือนนี้ (ระบบยังไม่มีปุ่มแก้ไข จึงต้อง block ไม่ให้สร้างซ้ำ)
  const existingNames = new Set(existingCrops.map((c) => c.crop_name.toLowerCase()));
  const dupWithExisting = rows.find((r) => existingNames.has(r.crop_name.toLowerCase()));
  if (dupWithExisting) {
    validationEl.textContent =
      'พืช "' + dupWithExisting.crop_name + '" ถูกรายงานไปแล้วในเดือนนี้ — ถ้ากรอกผิด กรุณาติดต่อ admin เพื่อแก้ไข ' +
      "แทนการส่งซ้ำ";
    return;
  }

  // ตรวจพื้นที่ปลูกรวม (เดิม + ใหม่) ต้องไม่เกินพื้นที่เกษตรทั้งหมู่บ้าน
  if (currentVillage.agri_rai !== null && currentVillage.agri_rai !== undefined) {
    const existingTotal = existingCrops.reduce((s, c) => s + c.planted_area_rai, 0);
    const newTotal = rows.reduce((s, r) => s + r.planted_area_rai, 0);
    const grandTotal = existingTotal + newTotal;
    if (grandTotal > currentVillage.agri_rai) {
      validationEl.textContent =
        "พื้นที่ปลูกรวมทั้งหมด (" + grandTotal.toLocaleString("th-TH") + " ไร่) เกินพื้นที่เกษตรทั้งหมู่บ้าน (" +
        currentVillage.agri_rai.toLocaleString("th-TH") + " ไร่) — กรุณาตรวจสอบตัวเลขอีกครั้ง";
      return;
    }
  }

  const submitBtn = document.getElementById("btn-submit-crops");
  submitBtn.disabled = true;
  const monthDate = reportMonthValue + "-01";
  try {
    for (const r of rows) {
      const res = await authFetch("/crop-reports", {
        method: "POST",
        body: JSON.stringify({
          village_id: currentVillage.village_id,
          crop_name: r.crop_name,
          planted_area_rai: r.planted_area_rai,
          reported_month: monthDate,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error((body.detail || "บันทึกไม่สำเร็จ") + ' (พืช "' + r.crop_name + '")');
    }
    statusEl.innerHTML = '<span class="ok">บันทึกรายงานพืชสำเร็จ ✓ (' + rows.length + " รายการ)</span>";
    document.getElementById("crop-rows").innerHTML = "";
    addCropRow();
    await loadExistingReports();
  } catch (err) {
    statusEl.innerHTML = '<span class="fail">บันทึกไม่สำเร็จ: ' + err.message + "</span>";
  } finally {
    submitBtn.disabled = false;
  }
});

// ---------- แถวเพิ่มปศุสัตว์ ----------

function addLivestockRow(prefillSpecies, prefillCount) {
  livestockRowCounter += 1;
  const id = "livestock-row-" + livestockRowCounter;
  const div = document.createElement("div");
  div.className = "row-group";
  div.id = id;

  const speciesOptions = LIVESTOCK_SPECIES.map((s) => '<option value="' + s + '">' + s + "</option>").join("");
  div.innerHTML =
    '<div><label>ชนิดสัตว์</label><select class="livestock-species-select">' +
    '<option value="">-- เลือกชนิด --</option>' + speciesOptions +
    '<option value="__other__">อื่นๆ (ระบุเอง)</option>' +
    "</select>" +
    '<input type="text" class="livestock-species-other" placeholder="ระบุชนิดสัตว์" style="display:none; margin-top:0.5rem;"></div>' +
    '<div><label>จำนวน (ตัว)</label><input type="number" class="livestock-count-input" min="0" step="1"></div>' +
    '<button type="button" class="secondary remove-row">ลบ</button>';

  const select = div.querySelector(".livestock-species-select");
  const otherInput = div.querySelector(".livestock-species-other");
  select.addEventListener("change", () => {
    otherInput.style.display = select.value === "__other__" ? "block" : "none";
  });
  if (prefillSpecies) {
    if (LIVESTOCK_SPECIES.includes(prefillSpecies)) {
      select.value = prefillSpecies;
    } else {
      select.value = "__other__";
      otherInput.style.display = "block";
      otherInput.value = prefillSpecies;
    }
  }
  if (prefillCount !== undefined && prefillCount !== null) div.querySelector(".livestock-count-input").value = prefillCount;
  div.querySelector(".remove-row").addEventListener("click", () => div.remove());
  document.getElementById("livestock-rows").appendChild(div);
}
document.getElementById("btn-add-livestock-row").addEventListener("click", () => addLivestockRow());
addLivestockRow();

document.getElementById("btn-submit-livestock").addEventListener("click", async () => {
  const validationEl = document.getElementById("livestock-validation");
  const statusEl = document.getElementById("livestock-submit-status");
  validationEl.textContent = "";
  statusEl.textContent = "";

  if (hasNoLivestockConfirmed()) {
    validationEl.textContent = "เดือนนี้ยืนยันไปแล้วว่าไม่มีปศุสัตว์ — ถ้าข้อมูลเปลี่ยนไป กรุณาติดต่อ admin";
    return;
  }

  const rows = Array.from(document.querySelectorAll("#livestock-rows .row-group"))
    .map((div) => {
      const select = div.querySelector(".livestock-species-select");
      const species = select.value === "__other__" ? div.querySelector(".livestock-species-other").value.trim() : select.value;
      return { species, head_count: parseInt(div.querySelector(".livestock-count-input").value, 10) };
    })
    .filter((r) => r.species || !isNaN(r.head_count));

  if (!rows.length) {
    validationEl.textContent = "กรุณากรอกอย่างน้อย 1 รายการ";
    return;
  }
  for (const r of rows) {
    if (!r.species || isNaN(r.head_count) || r.head_count < 0) {
      validationEl.textContent = "กรุณาเลือกชนิดสัตว์และกรอกจำนวน (ตัวเลข ≥ 0) ให้ครบทุกแถว";
      return;
    }
  }

  const seenInBatch = new Set();
  for (const r of rows) {
    const key = r.species.toLowerCase();
    if (seenInBatch.has(key)) {
      validationEl.textContent = 'มีชนิดสัตว์ "' + r.species + '" ซ้ำกันในแบบฟอร์มนี้ — กรุณารวมเป็นแถวเดียว';
      return;
    }
    seenInBatch.add(key);
  }

  const existingSpecies = new Set(existingLivestock.map((l) => l.species.toLowerCase()));
  const dupWithExisting = rows.find((r) => existingSpecies.has(r.species.toLowerCase()));
  if (dupWithExisting) {
    validationEl.textContent =
      'ชนิดสัตว์ "' + dupWithExisting.species + '" ถูกรายงานไปแล้วในเดือนนี้ — ถ้ากรอกผิด กรุณาติดต่อ admin เพื่อแก้ไข ' +
      "แทนการส่งซ้ำ";
    return;
  }

  const submitBtn = document.getElementById("btn-submit-livestock");
  submitBtn.disabled = true;
  const monthDate = reportMonthValue + "-01";
  try {
    for (const r of rows) {
      const res = await authFetch("/livestock-reports", {
        method: "POST",
        body: JSON.stringify({
          village_id: currentVillage.village_id,
          species: r.species,
          head_count: r.head_count,
          reported_month: monthDate,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error((body.detail || "บันทึกไม่สำเร็จ") + ' (ชนิด "' + r.species + '")');
    }
    statusEl.innerHTML = '<span class="ok">บันทึกรายงานปศุสัตว์สำเร็จ ✓ (' + rows.length + " รายการ)</span>";
    document.getElementById("livestock-rows").innerHTML = "";
    addLivestockRow();
    await loadExistingReports();
  } catch (err) {
    statusEl.innerHTML = '<span class="fail">บันทึกไม่สำเร็จ: ' + err.message + "</span>";
  } finally {
    submitBtn.disabled = false;
  }
});

if (auth) initVillageSelection();
