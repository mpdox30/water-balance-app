// admin-setup.js — Phase 3: onboarding ตำบลใหม่แบบเต็มรูปแบบ (nationwide, ไม่ใช่เฉพาะแม่นาเรือ)
// หลักการ: ทุกช่อง "ตำแหน่ง/พื้นที่" มาจาก dropdown (ผูก admin_boundary_lookup.json) หรือ
// การวาด/คลิกบนแผนที่ (Leaflet + Leaflet.draw) เท่านั้น — ไม่มีช่องพิมพ์พิกัด/geometry อิสระเลย

const auth = requireAdmin();
if (auth) {
  document.getElementById("whoami").textContent =
    (auth.display_name || auth.username || "admin") + " (admin)";
}

// ---------- state ----------
let lookupTree = {}; // { [province_th]: { [amphoe_th]: [ {tambon_th, area_km2, ...}, ... ] } }
let currentTambonId = null;
let currentTambonBoundaryGeojson = null;
let pendingLookupResult = null; // ผลจาก POST /admin/thai-tambon-lookup ก่อนกดยืนยัน
let villages = []; // [{village_id, moo, name_th, area_rai, population, households, residential_rai, agri_rai, forest_rai, other_rai, data_year_be}]
let editingVillageId = null; // village_id ที่กำลังแก้ไขอยู่ (null = โหมดเพิ่มใหม่)
let sources = []; // [{source_id, name_th, source_type, village_id}] — village_id null = แหล่งน้ำระดับตำบล
let activeDrawVillageId = null;
let pinMode = false;
let pendingMarker = null;
let villageGeometries = {}; // { [village_id]: [geojson geometry, ...] } — สะสมไว้เช็คทับซ้อนกัน (draw + upload)
const OVERLAP_WARN_THRESHOLD_PCT = 15; // % ที่เริ่มเตือน (ไม่ block) ทั้งกรณีล้นนอกตำบล และทับกับหมู่บ้านอื่น

// ---------- map setup ----------
const map = L.map("map").setView([13.75, 100.5], 6); // เริ่มที่ตำแหน่งกลางประเทศไทย

// สลับแผนที่ถนน/ภาพถ่ายดาวเทียมได้ — ใช้ Esri World Imagery (ฟรี ไม่ต้องมี API key) เป็นชั้นดาวเทียม
// เพื่อให้เห็นตำแหน่งแหล่งน้ำจริงชัดเจนตอนปักหมุด (ตามที่ขอเพิ่มใน Phase 3)
const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap",
  maxZoom: 19,
});
const satelliteLayer = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Imagery &copy; Esri", maxZoom: 19 }
);
osmLayer.addTo(map);
L.control.layers({ "แผนที่ถนน": osmLayer, "ภาพถ่ายดาวเทียม": satelliteLayer }, null, { position: "topright" }).addTo(map);

const previewLayerGroup = L.layerGroup().addTo(map);
const drawnVillageLayers = new L.FeatureGroup().addTo(map);
const sourceMarkersGroup = L.layerGroup().addTo(map);

let drawControl = null;

function enableVillageDrawTool() {
  if (drawControl) return;
  drawControl = new L.Control.Draw({
    edit: { featureGroup: drawnVillageLayers, edit: false, remove: false },
    draw: {
      polygon: { allowIntersection: false, showArea: true },
      polyline: false,
      rectangle: false,
      circle: false,
      circlemarker: false,
      marker: false,
    },
  });
  map.addControl(drawControl);
}

map.on(L.Draw.Event.CREATED, async (e) => {
  const layer = e.layer;
  if (!activeDrawVillageId) {
    alert("กรุณาเลือกหมู่บ้านที่จะวาดขอบเขตให้ก่อน (กดปุ่ม \"วาดขอบเขต\" ในตารางหมู่บ้าน)");
    return;
  }
  const geojson = layer.toGeoJSON().geometry;
  const warning = boundaryWarningText(geojson, activeDrawVillageId);
  try {
    const res = await authFetch("/village-boundary-parts", {
      method: "POST",
      body: JSON.stringify({ village_id: activeDrawVillageId, part_label: null, geom_geojson: geojson }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกขอบเขตไม่สำเร็จ");
    const vName = villages.find((v) => v.village_id === activeDrawVillageId).name_th;
    layer.bindPopup(vName + " (" + body.area_rai + " ไร่)" + (warning ? " ⚠️ " + warning : ""));
    drawnVillageLayers.addLayer(layer);
    recordVillageGeometry(activeDrawVillageId, geojson);
    const v = villages.find((x) => x.village_id === activeDrawVillageId);
    v.area_rai = (v.area_rai || 0) + body.area_rai;
    renderVillageTable();
    document.getElementById("draw-hint").style.display = "none";
    if (warning) alert("บันทึกสำเร็จ แต่มีข้อควรระวัง: " + warning);
    activeDrawVillageId = null;
  } catch (err) {
    alert("บันทึกขอบเขตไม่สำเร็จ: " + err.message);
  }
});

/** เก็บ geometry ของหมู่บ้าน (ทั้งจากวาดมือและอัปโหลด) ไว้เช็คทับซ้อนกับหมู่บ้านอื่นในรอบถัดไป */
function recordVillageGeometry(village_id, geom) {
  villageGeometries[village_id] = villageGeometries[village_id] || [];
  villageGeometries[village_id].push(geom);
}

/** เช็คว่า geometry นี้ล้นนอกตำบล หรือทับกับหมู่บ้านอื่นที่บันทึกไว้แล้วเกิน threshold ไหม
 * คืนข้อความเตือน (string) หรือ null ถ้าไม่มีอะไรน่าห่วง — ไม่เคย block การบันทึก แค่เตือน */
function boundaryWarningText(geom, forVillageId) {
  const warnings = [];
  if (currentTambonBoundaryGeojson) {
    const outsidePct = percentOutside(geom, currentTambonBoundaryGeojson);
    if (outsidePct !== null && outsidePct > OVERLAP_WARN_THRESHOLD_PCT) {
      warnings.push("อยู่นอกขอบเขตตำบล ~" + outsidePct.toFixed(0) + "%");
    }
  }
  const otherGeoms = Object.keys(villageGeometries)
    .filter((vid) => vid !== forVillageId)
    .flatMap((vid) => villageGeometries[vid]);
  const overlapPct = percentOverlap(geom, otherGeoms);
  if (overlapPct !== null && overlapPct > OVERLAP_WARN_THRESHOLD_PCT) {
    warnings.push("ทับกับขอบเขตหมู่บ้านอื่น ~" + overlapPct.toFixed(0) + "%");
  }
  return warnings.length ? warnings.join(" และ ") : null;
}

map.on("click", (e) => {
  if (!pinMode) return;
  if (pendingMarker) map.removeLayer(pendingMarker);
  pendingMarker = L.marker(e.latlng, { draggable: true }).addTo(map);
  document.getElementById("pin-status").textContent =
    "ปักหมุดที่ " + e.latlng.lat.toFixed(5) + ", " + e.latlng.lng.toFixed(5) + " (ลากหมุดเพื่อปรับตำแหน่งได้)";
  document.getElementById("btn-save-source").disabled = false;
});

// ---------- step 1: เลือกตำบล ----------
async function loadLookupData() {
  const res = await fetch("data/admin_boundary_lookup.json");
  const rows = await res.json();
  for (const row of rows) {
    lookupTree[row.province_th] = lookupTree[row.province_th] || {};
    lookupTree[row.province_th][row.amphoe_th] = lookupTree[row.province_th][row.amphoe_th] || [];
    lookupTree[row.province_th][row.amphoe_th].push(row);
  }
  const selProvince = document.getElementById("sel-province");
  Object.keys(lookupTree).sort().forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    selProvince.appendChild(opt);
  });
}

document.getElementById("sel-province").addEventListener("change", (e) => {
  const selAmphoe = document.getElementById("sel-amphoe");
  const selTambon = document.getElementById("sel-tambon");
  selAmphoe.innerHTML = '<option value="">-- เลือกอำเภอ --</option>';
  selTambon.innerHTML = '<option value="">-- เลือกตำบล --</option>';
  selTambon.disabled = true;
  document.getElementById("btn-load-boundary").disabled = true;
  if (!e.target.value) {
    selAmphoe.disabled = true;
    return;
  }
  Object.keys(lookupTree[e.target.value]).sort().forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a;
    opt.textContent = a;
    selAmphoe.appendChild(opt);
  });
  selAmphoe.disabled = false;
});

document.getElementById("sel-amphoe").addEventListener("change", (e) => {
  const province = document.getElementById("sel-province").value;
  const selTambon = document.getElementById("sel-tambon");
  selTambon.innerHTML = '<option value="">-- เลือกตำบล --</option>';
  document.getElementById("btn-load-boundary").disabled = true;
  if (!e.target.value) {
    selTambon.disabled = true;
    return;
  }
  lookupTree[province][e.target.value]
    .slice()
    .sort((a, b) => a.tambon_th.localeCompare(b.tambon_th, "th"))
    .forEach((row) => {
      const opt = document.createElement("option");
      opt.value = row.tambon_th;
      opt.textContent = row.tambon_th + " (~" + row.area_km2.toFixed(1) + " ตร.กม.)";
      selTambon.appendChild(opt);
    });
  selTambon.disabled = false;
});

document.getElementById("sel-tambon").addEventListener("change", (e) => {
  document.getElementById("btn-load-boundary").disabled = !e.target.value;
  document.getElementById("btn-confirm-tambon").disabled = true;
  document.getElementById("tambon-preview").textContent = "";
  document.getElementById("tambon-upload-status").textContent = "";
  document.getElementById("tambon-upload-file").value = "";
  previewLayerGroup.clearLayers();
  pendingLookupResult = null;
});

document.getElementById("tambon-upload-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("tambon-upload-status");
  const province_th = document.getElementById("sel-province").value;
  const amphoe_th = document.getElementById("sel-amphoe").value;
  const tambon_th = document.getElementById("sel-tambon").value;
  if (!province_th || !amphoe_th || !tambon_th) {
    statusEl.textContent = "กรุณาเลือกจังหวัด/อำเภอ/ตำบลให้ครบก่อนอัปโหลดไฟล์";
    e.target.value = "";
    return;
  }
  const officialRow = (lookupTree[province_th]?.[amphoe_th] || []).find((r) => r.tambon_th === tambon_th);
  statusEl.textContent = "กำลังอ่านไฟล์...";
  try {
    const fc = await parseGeoFile(file);
    if (!fc.features.length) throw new Error("ไม่พบขอบเขตในไฟล์");
    // ถ้ามีหลาย feature ในไฟล์ ใช้อันที่พื้นที่ใหญ่สุด (สมมติว่าเป็นขอบเขตตำบลหลัก)
    let best = fc.features[0];
    let bestArea = areaRai(best.geometry);
    for (const f of fc.features.slice(1)) {
      const a = areaRai(f.geometry);
      if (a > bestArea) { best = f; bestArea = a; }
    }
    const coerced = toSinglePolygon(best.geometry);
    if (!coerced.geom) throw new Error(coerced.note);
    const geom = coerced.geom;
    const areaKm2FromFile = (areaRai(geom) * 1600) / 1e6;
    pendingLookupResult = {
      province_th,
      amphoe_th,
      tambon_th,
      name_en: officialRow ? officialRow.tambon_en : null,
      area_km2: Math.round(areaKm2FromFile * 10000) / 10000,
      area_km2_source: "อัปโหลดโดย admin (ไฟล์ " + file.name + ", Phase 3)",
      geom_geojson: geom,
    };
    previewLayerGroup.clearLayers();
    const layer = L.geoJSON(geom, { style: { color: "#c0392b", weight: 2, fillOpacity: 0.15 } });
    previewLayerGroup.addLayer(layer);
    map.fitBounds(layer.getBounds(), { padding: [20, 20] });

    let warningHtml = "";
    if (officialRow && officialRow.area_km2 > 0) {
      const diffPct = (Math.abs(areaKm2FromFile - officialRow.area_km2) / officialRow.area_km2) * 100;
      if (diffPct > 20) {
        warningHtml =
          ' <span class="fail">⚠️ พื้นที่จากไฟล์ (' + areaKm2FromFile.toFixed(2) + " ตร.กม.) ต่างจากค่าทางการ (" +
          officialRow.area_km2.toFixed(2) + " ตร.กม.) ถึง " + diffPct.toFixed(0) +
          "% — ตรวจสอบว่าเลือกตำบลถูกต้องหรือไฟล์ผิด แต่ยังบันทึกต่อได้ถ้ามั่นใจ</span>";
      }
    }
    const coercedNote = coerced.note ? ' <span class="fail">⚠️ ' + coerced.note + "</span>" : "";
    statusEl.innerHTML =
      "พื้นที่จากไฟล์ที่อัปโหลด: <strong>" + areaKm2FromFile.toFixed(2) + " ตร.กม.</strong>" + coercedNote + warningHtml;
    document.getElementById("tambon-preview").textContent = "";
    document.getElementById("btn-confirm-tambon").disabled = false;
  } catch (err) {
    statusEl.textContent = "อ่านไฟล์ไม่สำเร็จ: " + err.message;
  }
});

document.getElementById("btn-load-boundary").addEventListener("click", async () => {
  const province_th = document.getElementById("sel-province").value;
  const amphoe_th = document.getElementById("sel-amphoe").value;
  const tambon_th = document.getElementById("sel-tambon").value;
  const previewEl = document.getElementById("tambon-preview");
  previewEl.textContent = "กำลังโหลดขอบเขตจากฐานข้อมูลกลาง...";
  try {
    const res = await authFetch("/admin/thai-tambon-lookup", {
      method: "POST",
      body: JSON.stringify({ province_th, amphoe_th, tambon_th }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "โหลดขอบเขตไม่สำเร็จ");
    pendingLookupResult = body;
    previewLayerGroup.clearLayers();
    const layer = L.geoJSON(body.geom_geojson, { style: { color: "#1a7f37", weight: 2, fillOpacity: 0.15 } });
    previewLayerGroup.addLayer(layer);
    map.fitBounds(layer.getBounds(), { padding: [20, 20] });
    previewEl.innerHTML =
      "พื้นที่ตามฐานข้อมูลกลาง: <strong>" + body.area_km2.toFixed(2) + " ตร.กม.</strong> (" + body.name_en + ")";
    document.getElementById("btn-confirm-tambon").disabled = false;
  } catch (err) {
    previewEl.textContent = "โหลดขอบเขตไม่สำเร็จ: " + err.message;
  }
});

document.getElementById("btn-confirm-tambon").addEventListener("click", async () => {
  if (!pendingLookupResult) return;
  const statusEl = document.getElementById("tambon-status");
  statusEl.textContent = "กำลังสร้างตำบล...";
  try {
    const res = await authFetch("/tambons", {
      method: "POST",
      body: JSON.stringify({
        name_th: pendingLookupResult.tambon_th,
        name_en: pendingLookupResult.name_en,
        province_th: pendingLookupResult.province_th,
        amphoe_th: pendingLookupResult.amphoe_th,
        area_km2: pendingLookupResult.area_km2,
        area_km2_source: pendingLookupResult.area_km2_source,
        is_pilot: false,
        geom_geojson: pendingLookupResult.geom_geojson,
      }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "สร้างตำบลไม่สำเร็จ");
    currentTambonId = body.tambon_id;
    currentTambonBoundaryGeojson = pendingLookupResult.geom_geojson;
    statusEl.innerHTML = '<span class="ok">สร้างตำบล "' + body.name_th + '" สำเร็จ ✓</span>';
    document.querySelectorAll("#sel-province, #sel-amphoe, #sel-tambon, #btn-load-boundary, #btn-confirm-tambon")
      .forEach((el) => (el.disabled = true));
    document.getElementById("step1").classList.add("done");
    document.getElementById("step2").classList.add("active");
    enableVillageDrawTool();
  } catch (err) {
    statusEl.textContent = "สร้างตำบลไม่สำเร็จ: " + err.message;
  }
});

// ---------- step 2: หมู่บ้าน + ขอบเขต ----------
function renderVillageTable() {
  const table = document.getElementById("village-table");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  if (villages.length === 0) {
    table.style.display = "none";
    return;
  }
  table.style.display = "";
  villages.forEach((v) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + v.moo + "</td><td>" + v.name_th + "</td>" +
      "<td>" + (v.population != null ? v.population : "-") + "</td>" +
      "<td>" + (v.households != null ? v.households : "-") + "</td>" +
      "<td>" + (v.area_rai ? v.area_rai.toFixed(1) : "ยังไม่ได้วาด") + "</td>" +
      '<td class="village-row-actions"></td>';
    const btnDraw = document.createElement("button");
    btnDraw.textContent = "วาดขอบเขต";
    btnDraw.className = "secondary";
    btnDraw.addEventListener("click", () => {
      activeDrawVillageId = v.village_id;
      document.getElementById("draw-target-name").textContent = "หมู่ " + v.moo + " " + v.name_th;
      document.getElementById("draw-hint").style.display = "";
    });
    const btnEdit = document.createElement("button");
    btnEdit.textContent = "แก้ไขข้อมูล";
    btnEdit.className = "secondary";
    btnEdit.addEventListener("click", () => startEditVillage(v));
    tr.querySelector(".village-row-actions").appendChild(btnDraw);
    tr.querySelector(".village-row-actions").appendChild(btnEdit);
    tbody.appendChild(tr);
  });
  // sync ตัวเลือกหมู่บ้านในฟอร์มแหล่งน้ำ (step 3) ด้วย
  const selSourceVillage = document.getElementById("source-village");
  selSourceVillage.innerHTML = '<option value="">-- ระดับตำบล --</option>';
  villages.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.village_id;
    opt.textContent = "หมู่ " + v.moo + " " + v.name_th;
    selSourceVillage.appendChild(opt);
  });
  // รายชื่อหมู่บ้านอาจเพิ่ม/แก้หลังจากสร้างแหล่งน้ำระดับตำบลไปแล้ว — sync ตาราง matrix (step 4) ให้ตรงด้วย
  renderReservoirMatrixSection();
}

// ---------- step 4: จัดสรรอ่างเก็บน้ำระดับตำบลให้หมู่บ้าน ----------

/** วาด/อัปเดตตาราง matrix (อ่างระดับตำบล x หมู่บ้าน) ใหม่ทั้งหมด — เรียกซ้ำได้ปลอดภัยทุกครั้งที่ sources/villages เปลี่ยน
 * ถ้าไม่มีแหล่งน้ำระดับตำบลเลย (ทุกแห่งผูกกับหมู่บ้านเดียวไปแล้วตอนสร้าง) จะแสดงข้อความว่าไม่มีอะไรให้จัดสรร — ข้ามได้ */
async function renderReservoirMatrixSection() {
  const container = document.getElementById("reservoir-matrix-container");
  if (!container) return;
  const tambonSources = sources.filter((s) => !s.village_id);
  if (tambonSources.length === 0) {
    container.innerHTML = '<p class="muted">ยังไม่มีแหล่งน้ำระดับตำบลให้จัดสรร</p>';
    return;
  }
  if (villages.length === 0) {
    container.innerHTML = '<p class="muted">ยังไม่มีหมู่บ้าน (เพิ่มหมู่บ้านในขั้นตอนที่ 2 ก่อน)</p>';
    return;
  }
  container.innerHTML = "";
  for (const src of tambonSources) {
    container.appendChild(await buildReservoirMatrixCard(src));
  }
}

async function buildReservoirMatrixCard(src) {
  const card = document.createElement("div");
  card.className = "res-matrix-card";
  const heading = document.createElement("h3");
  heading.style.marginTop = "0";
  heading.textContent = src.name_th;
  const hint = document.createElement("p");
  hint.className = "muted";
  hint.style.marginTop = "-0.5rem";
  hint.textContent = "เลือกหมู่บ้านที่ใช้น้ำจากแหล่งนี้จริง — เว้นว่างได้ถ้าไม่แน่ใจ ไม่บังคับต้องกรอกให้ครบ";
  card.appendChild(heading);
  card.appendChild(hint);

  let existing = [];
  try {
    const res = await authFetch("/water-sources/" + src.source_id + "/village-usage");
    if (res.ok) existing = await res.json();
  } catch (err) {
    // เงียบไว้ — โหลดของเดิมไม่สำเร็จก็แค่เริ่มจากตารางว่าง ไม่ block การแสดงผล
  }

  const table = document.createElement("table");
  table.className = "res-matrix-table";
  table.innerHTML = "<thead><tr><th>หมู่บ้าน</th><th>เกษตร</th><th>อุปโภคบริโภค</th></tr></thead><tbody></tbody>";
  const tbody = table.querySelector("tbody");

  villages.forEach((v) => {
    const tr = document.createElement("tr");
    const tdName = document.createElement("td");
    tdName.textContent = "หมู่ " + v.moo + " " + v.name_th;
    tr.appendChild(tdName);

    ["agri", "domestic"].forEach((useType) => {
      const td = document.createElement("td");
      const existingRow = existing.find((e) => e.village_id === v.village_id && e.use_type === useType);

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!existingRow;
      cb.dataset.villageId = v.village_id;
      cb.dataset.useType = useType;

      const fields = document.createElement("div");
      fields.className = "cell-fields" + (existingRow ? "" : " hidden");
      const popInput = document.createElement("input");
      popInput.type = "number";
      popInput.min = "0";
      popInput.placeholder = "ประชากร";
      popInput.dataset.field = "population";
      if (existingRow && existingRow.population != null) popInput.value = existingRow.population;
      const hhInput = document.createElement("input");
      hhInput.type = "number";
      hhInput.min = "0";
      hhInput.placeholder = "ครัวเรือน";
      hhInput.dataset.field = "households";
      if (existingRow && existingRow.households != null) hhInput.value = existingRow.households;
      fields.appendChild(popInput);
      fields.appendChild(hhInput);

      cb.addEventListener("change", () => fields.classList.toggle("hidden", !cb.checked));

      td.appendChild(cb);
      td.appendChild(fields);
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "บันทึกการจัดสรร";
  saveBtn.className = "secondary";
  saveBtn.style.marginTop = "0.75rem";
  const statusEl = document.createElement("div");
  statusEl.className = "muted";
  statusEl.style.marginTop = "0.4rem";

  saveBtn.addEventListener("click", async () => {
    const items = [];
    tbody.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      if (!cb.checked) return;
      const td = cb.closest("td");
      const pop = td.querySelector('[data-field="population"]').value;
      const hh = td.querySelector('[data-field="households"]').value;
      items.push({
        village_id: cb.dataset.villageId,
        use_type: cb.dataset.useType,
        population: pop ? parseInt(pop, 10) : null,
        households: hh ? parseInt(hh, 10) : null,
      });
    });
    statusEl.textContent = "กำลังบันทึก...";
    try {
      const res = await authFetch("/water-sources/" + src.source_id + "/village-usage", {
        method: "PUT",
        body: JSON.stringify({ items }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "บันทึกไม่สำเร็จ");
      statusEl.innerHTML = '<span class="ok">บันทึกแล้ว (' + items.length + " รายการ) ✓</span>";
    } catch (err) {
      statusEl.textContent = "บันทึกไม่สำเร็จ: " + err.message;
    }
  });

  card.appendChild(table);
  card.appendChild(saveBtn);
  card.appendChild(statusEl);
  return card;
}

/** อ่านฟิลด์ประชากร/ครัวเรือน/พื้นที่ใช้ที่ดินจากฟอร์ม (ทุกฟิลด์ไม่บังคับ — เว้นว่าง = ไม่ส่งค่า/null) */
function readVillageOptionalFields() {
  const num = (id, isFloat) => {
    const raw = document.getElementById(id).value;
    if (raw === "") return null;
    return isFloat ? parseFloat(raw) : parseInt(raw, 10);
  };
  return {
    population: num("village-population", false),
    households: num("village-households", false),
    residential_rai: num("village-residential-rai", true),
    agri_rai: num("village-agri-rai", true),
    forest_rai: num("village-forest-rai", true),
    other_rai: num("village-other-rai", true),
    data_year_be: num("village-data-year-be", false),
  };
}

function clearVillageForm() {
  document.getElementById("village-moo").value = "";
  document.getElementById("village-name").value = "";
  document.getElementById("village-population").value = "";
  document.getElementById("village-households").value = "";
  document.getElementById("village-residential-rai").value = "";
  document.getElementById("village-agri-rai").value = "";
  document.getElementById("village-forest-rai").value = "";
  document.getElementById("village-other-rai").value = "";
  document.getElementById("village-data-year-be").value = "";
}

/** เริ่มโหมดแก้ไขหมู่บ้านที่มีอยู่แล้ว — เติมค่าเดิมลงฟอร์มเดียวกับฟอร์มเพิ่มหมู่บ้าน แล้วสลับปุ่มเป็น "บันทึกการแก้ไข" */
function startEditVillage(v) {
  editingVillageId = v.village_id;
  document.getElementById("village-moo").value = v.moo;
  document.getElementById("village-name").value = v.name_th;
  document.getElementById("village-population").value = v.population != null ? v.population : "";
  document.getElementById("village-households").value = v.households != null ? v.households : "";
  document.getElementById("village-residential-rai").value = v.residential_rai != null ? v.residential_rai : "";
  document.getElementById("village-agri-rai").value = v.agri_rai != null ? v.agri_rai : "";
  document.getElementById("village-forest-rai").value = v.forest_rai != null ? v.forest_rai : "";
  document.getElementById("village-other-rai").value = v.other_rai != null ? v.other_rai : "";
  document.getElementById("village-data-year-be").value = v.data_year_be != null ? v.data_year_be : "";
  document.getElementById("btn-add-village").textContent = "บันทึกการแก้ไข";
  document.getElementById("btn-cancel-edit-village").style.display = "";
  document.getElementById("village-add-status").innerHTML =
    'กำลังแก้ไข "หมู่ ' + v.moo + " " + v.name_th + '" — แก้ค่าที่ต้องการแล้วกด "บันทึกการแก้ไข"';
}

function endEditVillage() {
  editingVillageId = null;
  clearVillageForm();
  document.getElementById("btn-add-village").textContent = "เพิ่มหมู่บ้าน";
  document.getElementById("btn-cancel-edit-village").style.display = "none";
  document.getElementById("village-add-status").textContent = "";
}

document.getElementById("btn-cancel-edit-village").addEventListener("click", endEditVillage);

// ---------- step 1 (bulk): นำเข้าหมู่บ้านหลายรายการทีเดียวจาก Excel/CSV ----------
let villageBulkRows = []; // [{moo, name_th, population, households, residential_rai, agri_rai, forest_rai, other_rai, data_year_be}]

const VILLAGE_COL_ALIASES = {
  moo: ["หมู่ที่", "หมู่", "moo"],
  name_th: ["ชื่อหมู่บ้าน", "ชื่อ", "name_th", "name"],
  population: ["ประชากร", "population"],
  households: ["ครัวเรือน", "households"],
  residential_rai: ["พื้นที่อยู่อาศัย", "residential_rai"],
  agri_rai: ["พื้นที่เกษตร", "agri_rai"],
  forest_rai: ["พื้นที่ป่า", "forest_rai"],
  other_rai: ["อื่นๆ", "other_rai"],
  data_year_be: ["ปีข้อมูล", "data_year_be"],
};

document.getElementById("village-bulk-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("village-bulk-status");
  statusEl.textContent = "กำลังอ่านไฟล์...";
  try {
    const rows = await parseTabularFile(file);
    const round = (n) => (n == null ? null : Math.round(n));
    villageBulkRows = rows
      .map((r) => ({
        moo: round(getCellNumber(r, VILLAGE_COL_ALIASES.moo)),
        name_th: (getCell(r, VILLAGE_COL_ALIASES.name_th) || "").toString().trim(),
        population: round(getCellNumber(r, VILLAGE_COL_ALIASES.population)),
        households: round(getCellNumber(r, VILLAGE_COL_ALIASES.households)),
        residential_rai: getCellNumber(r, VILLAGE_COL_ALIASES.residential_rai),
        agri_rai: getCellNumber(r, VILLAGE_COL_ALIASES.agri_rai),
        forest_rai: getCellNumber(r, VILLAGE_COL_ALIASES.forest_rai),
        other_rai: getCellNumber(r, VILLAGE_COL_ALIASES.other_rai),
        data_year_be: round(getCellNumber(r, VILLAGE_COL_ALIASES.data_year_be)),
      }))
      .filter((r) => r.moo && r.name_th);
    renderVillageBulkTable();
    const skipped = rows.length - villageBulkRows.length;
    statusEl.textContent =
      "อ่านไฟล์สำเร็จ พบ " + villageBulkRows.length + " แถวที่ใช้ได้ (มีหมู่+ชื่อครบ)" +
      (skipped > 0 ? " — ข้าม " + skipped + " แถวที่ไม่มีหมู่หรือชื่อ" : "") + " — ตรวจสอบก่อนกดยืนยัน";
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

function renderVillageBulkTable() {
  const table = document.getElementById("village-bulk-table");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  const confirmBtn = document.getElementById("btn-confirm-village-bulk");
  if (villageBulkRows.length === 0) {
    table.style.display = "none";
    confirmBtn.style.display = "none";
    return;
  }
  table.style.display = "";
  confirmBtn.style.display = "";
  villageBulkRows.forEach((r) => {
    const existing = villages.find((v) => v.moo === r.moo);
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + r.moo + "</td><td>" + r.name_th + "</td>" +
      "<td>" + (r.population != null ? r.population : "-") + "</td>" +
      "<td>" + (r.households != null ? r.households : "-") + "</td>" +
      "<td>" + (existing ? "จะแก้ไขหมู่ " + r.moo + " ที่มีอยู่แล้ว" : "จะสร้างใหม่") + "</td>";
    tbody.appendChild(tr);
  });
}

document.getElementById("btn-confirm-village-bulk").addEventListener("click", async () => {
  const statusEl = document.getElementById("village-bulk-status");
  let successCount = 0;
  const failed = [];
  for (const r of villageBulkRows) {
    const optionalFields = {
      population: r.population,
      households: r.households,
      residential_rai: r.residential_rai,
      agri_rai: r.agri_rai,
      forest_rai: r.forest_rai,
      other_rai: r.other_rai,
      data_year_be: r.data_year_be,
    };
    const existing = villages.find((v) => v.moo === r.moo);
    try {
      if (existing) {
        const res = await authFetch("/villages/" + existing.village_id, {
          method: "PATCH",
          body: JSON.stringify({ name_th: r.name_th, ...optionalFields }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || "แก้ไขไม่สำเร็จ");
        Object.assign(existing, body);
      } else {
        const res = await authFetch("/villages", {
          method: "POST",
          body: JSON.stringify({
            tambon_id: currentTambonId,
            moo: r.moo,
            name_th: r.name_th,
            name_source: "bulk import (Excel/CSV)",
            ...optionalFields,
          }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || "เพิ่มไม่สำเร็จ");
        villages.push({ ...body, area_rai: 0 });
      }
      successCount++;
    } catch (err) {
      failed.push("หมู่ " + r.moo + " " + r.name_th + ": " + err.message);
    }
  }
  renderVillageTable();
  statusEl.innerHTML =
    '<span class="ok">นำเข้าสำเร็จ ' + successCount + " รายการ</span>" +
    (failed.length ? ' <span class="fail">— ล้มเหลว ' + failed.length + " รายการ: " + failed.join("; ") + "</span>" : "");
  document.getElementById("village-bulk-table").style.display = "none";
  document.getElementById("btn-confirm-village-bulk").style.display = "none";
  document.getElementById("village-bulk-file").value = "";
  villageBulkRows = [];
  document.getElementById("step3").classList.add("active");
});

document.getElementById("btn-add-village").addEventListener("click", async () => {
  const moo = parseInt(document.getElementById("village-moo").value, 10);
  const name_th = document.getElementById("village-name").value.trim();
  const statusEl = document.getElementById("village-add-status");
  if (!moo || !name_th) {
    statusEl.textContent = "กรอกหมู่ที่และชื่อหมู่บ้านให้ครบ";
    return;
  }
  const optionalFields = readVillageOptionalFields();

  if (editingVillageId) {
    statusEl.textContent = "กำลังบันทึกการแก้ไข...";
    try {
      const res = await authFetch("/villages/" + editingVillageId, {
        method: "PATCH",
        body: JSON.stringify({ moo, name_th, ...optionalFields }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "แก้ไขหมู่บ้านไม่สำเร็จ");
      const v = villages.find((x) => x.village_id === editingVillageId);
      Object.assign(v, body);
      renderVillageTable();
      statusEl.innerHTML = '<span class="ok">บันทึกการแก้ไข "' + body.name_th + '" แล้ว</span>';
      endEditVillage();
    } catch (err) {
      statusEl.textContent = "แก้ไขหมู่บ้านไม่สำเร็จ: " + err.message;
    }
    return;
  }

  statusEl.textContent = "กำลังเพิ่ม...";
  try {
    const res = await authFetch("/villages", {
      method: "POST",
      body: JSON.stringify({
        tambon_id: currentTambonId,
        moo,
        name_th,
        name_source: "manual (admin-setup Phase 3)",
        ...optionalFields,
      }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "เพิ่มหมู่บ้านไม่สำเร็จ");
    villages.push({ ...body, area_rai: 0 });
    renderVillageTable();
    clearVillageForm();
    statusEl.innerHTML = '<span class="ok">เพิ่ม "' + body.name_th + '" แล้ว — วาดขอบเขตในตารางด้านล่าง</span>';
    document.getElementById("step3").classList.add("active");
  } catch (err) {
    statusEl.textContent = "เพิ่มหมู่บ้านไม่สำเร็จ: " + err.message;
  }
});

// ---------- step 2b: อัปโหลดขอบเขตหมู่บ้านทั้งตำบลจากไฟล์ ----------
let uploadedVillageFeatures = []; // [{geom, properties, area_rai}]

document.getElementById("village-upload-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("village-upload-status");
  statusEl.textContent = "กำลังอ่านไฟล์...";
  try {
    const fc = await parseGeoFile(file);
    if (!fc.features.length) throw new Error("ไม่พบขอบเขตในไฟล์");
    uploadedVillageFeatures = fc.features.map((f) => ({
      geom: f.geometry,
      properties: f.properties || {},
      area_rai: areaRai(f.geometry),
    }));
    renderVillageMatchTable();
    statusEl.textContent =
      "อ่านไฟล์สำเร็จ พบ " + uploadedVillageFeatures.length + " รายการ — ตรวจสอบการจับคู่ในตารางด้านล่างก่อนยืนยัน";
  } catch (err) {
    statusEl.textContent = "อ่านไฟล์ไม่สำเร็จ: " + err.message;
  }
});

function renderVillageMatchTable() {
  const table = document.getElementById("village-match-table");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  const confirmBtn = document.getElementById("btn-confirm-village-upload");
  if (uploadedVillageFeatures.length === 0) {
    table.style.display = "none";
    confirmBtn.style.display = "none";
    return;
  }
  table.style.display = "";
  confirmBtn.style.display = "";

  uploadedVillageFeatures.forEach((item, idx) => {
    const guessedMoo = guessMoo(item.properties);
    const guessedName = guessName(item.properties);
    const label =
      guessedName || guessedMoo
        ? "หมู่ " + (guessedMoo ?? "?") + " " + (guessedName || "")
        : "รายการที่ " + (idx + 1) + " (เดาชื่อ/หมู่ไม่ได้จากไฟล์)";

    const tr = document.createElement("tr");
    const tdLabel = document.createElement("td");
    tdLabel.textContent = label;
    const tdArea = document.createElement("td");
    tdArea.textContent = item.area_rai.toFixed(1);

    const tdMatch = document.createElement("td");
    const sel = document.createElement("select");
    const optSkip = document.createElement("option");
    optSkip.value = "";
    optSkip.textContent = "-- ข้าม --";
    sel.appendChild(optSkip);
    villages.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.village_id;
      opt.textContent = "หมู่ " + v.moo + " " + v.name_th;
      if ((guessedMoo && guessedMoo === v.moo) || (guessedName && guessedName.trim() === v.name_th.trim())) {
        opt.selected = true;
      }
      sel.appendChild(opt);
    });
    sel.dataset.idx = String(idx);
    tdMatch.appendChild(sel);

    const tdWarn = document.createElement("td");
    tdWarn.className = "muted";

    tr.appendChild(tdLabel);
    tr.appendChild(tdArea);
    tr.appendChild(tdMatch);
    tr.appendChild(tdWarn);
    tbody.appendChild(tr);
  });
}

document.getElementById("btn-confirm-village-upload").addEventListener("click", async () => {
  const statusEl = document.getElementById("village-upload-status");
  const rows = document.querySelectorAll("#village-match-table tbody tr");
  let successCount = 0;
  for (const tr of rows) {
    const sel = tr.querySelector("select");
    const village_id = sel.value;
    const warnTd = tr.children[3];
    if (!village_id) continue;
    const idx = parseInt(sel.dataset.idx, 10);
    const item = uploadedVillageFeatures[idx];
    const coerced = toSinglePolygon(item.geom);
    if (!coerced.geom) {
      warnTd.textContent = "✗ " + coerced.note;
      warnTd.className = "fail";
      continue;
    }
    const geomToSave = coerced.geom;
    const warning = [coerced.note, boundaryWarningText(geomToSave, village_id)].filter(Boolean).join(" — ") || null;
    try {
      const res = await authFetch("/village-boundary-parts", {
        method: "POST",
        body: JSON.stringify({ village_id, part_label: null, geom_geojson: geomToSave }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "บันทึกไม่สำเร็จ");
      recordVillageGeometry(village_id, geomToSave);
      const v = villages.find((x) => x.village_id === village_id);
      v.area_rai = (v.area_rai || 0) + body.area_rai;
      const layer = L.geoJSON(geomToSave, { style: { color: "#1a7f37", weight: 2, fillOpacity: 0.15 } });
      layer.bindPopup(v.name_th + " (" + body.area_rai + " ไร่, นำเข้าจากไฟล์)");
      drawnVillageLayers.addLayer(layer);
      warnTd.textContent = warning ? "⚠️ " + warning : "✓ บันทึกแล้ว";
      warnTd.className = warning ? "fail" : "ok";
      successCount++;
    } catch (err) {
      warnTd.textContent = "✗ " + err.message;
      warnTd.className = "fail";
    }
  }
  renderVillageTable();
  statusEl.textContent = "นำเข้าสำเร็จ " + successCount + " รายการ";
});

// ---------- step 3: แหล่งน้ำ ----------
document.getElementById("btn-pin-mode").addEventListener("click", () => {
  pinMode = !pinMode;
  document.getElementById("btn-pin-mode").textContent = pinMode ? "กำลังปักหมุด (คลิกบนแผนที่)" : "เริ่มปักหมุดบนแผนที่";
  if (!pinMode) {
    document.getElementById("pin-status").textContent = pendingMarker ? "ปักหมุดแล้ว (แก้ตำแหน่งได้ที่ปุ่มด้านบน)" : "ยังไม่ได้ปักหมุด";
  }
});

const SOURCE_TYPE_LABELS = {
  pond: "สระ",
  reservoir: "อ่างเก็บน้ำ",
  groundwater_well: "บ่อบาดาล",
  mountain_spring: "น้ำผุดจากภูเขา",
  weir: "ฝาย",
  small_water_source: "แหล่งน้ำขนาดเล็กอื่นๆ",
  purchased_external: "ซื้อน้ำจากภายนอก",
};
// ฝายไม่มีความจุ (เก็บมิติ/สภาพเป็นข้อความแทน) — ดู 00_docs/future-tambon-onboarding-plan.md ขั้นตอนที่ 3
const SOURCE_TYPES_WITHOUT_CAPACITY = new Set(["weir"]);

document.getElementById("source-type").addEventListener("change", (e) => {
  const noCapacity = SOURCE_TYPES_WITHOUT_CAPACITY.has(e.target.value);
  document.getElementById("source-capacity-group").style.display = noCapacity ? "none" : "";
  document.getElementById("source-dimension-group").style.display = noCapacity ? "" : "none";
});

document.getElementById("btn-save-source").addEventListener("click", async () => {
  if (!pendingMarker) return;
  const statusEl = document.getElementById("pin-status");
  const latlng = pendingMarker.getLatLng();
  const name_th = document.getElementById("source-name").value.trim();
  const source_type = document.getElementById("source-type").value;
  const village_id = document.getElementById("source-village").value || null;
  const capacityRaw = document.getElementById("source-capacity").value;
  const dimensionRaw = document.getElementById("source-dimension").value.trim();
  if (!name_th) {
    statusEl.textContent = "กรอกชื่อแหล่งน้ำก่อน";
    return;
  }
  const isWeir = SOURCE_TYPES_WITHOUT_CAPACITY.has(source_type);
  let capacitySourceNote = null;
  if (isWeir && dimensionRaw) {
    capacitySourceNote = dimensionRaw;
  } else if (!isWeir && capacityRaw) {
    capacitySourceNote = "กรอกโดย admin ตอน setup (Phase 3)";
  }
  try {
    const res = await authFetch("/water-sources", {
      method: "POST",
      body: JSON.stringify({
        tambon_id: currentTambonId,
        village_id,
        source_type,
        name_th,
        lat: latlng.lat,
        lon: latlng.lng,
        stored_capacity_m3: !isWeir && capacityRaw ? parseFloat(capacityRaw) : null,
        capacity_source_note: capacitySourceNote,
      }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกแหล่งน้ำไม่สำเร็จ");
    sourceMarkersGroup.addLayer(L.marker(latlng).bindPopup(body.name_th));
    addSourceRow(body, village_id);
    sources.push({ source_id: body.source_id, name_th: body.name_th, source_type: body.source_type, village_id });
    renderReservoirMatrixSection();
    map.removeLayer(pendingMarker);
    pendingMarker = null;
    pinMode = false;
    document.getElementById("btn-pin-mode").textContent = "เริ่มปักหมุดบนแผนที่";
    document.getElementById("btn-save-source").disabled = true;
    document.getElementById("pin-status").textContent = "บันทึกแล้ว — ปักหมุดจุดถัดไปได้เลย";
    document.getElementById("source-name").value = "";
    document.getElementById("source-capacity").value = "";
    document.getElementById("source-dimension").value = "";
    document.getElementById("step4").classList.add("active");
    document.getElementById("step5").classList.add("active");
  } catch (err) {
    statusEl.textContent = "บันทึกไม่สำเร็จ: " + err.message;
  }
});

function addSourceRow(source, village_id) {
  const table = document.getElementById("source-table");
  table.style.display = "";
  const tbody = table.querySelector("tbody");
  const villageLabel = village_id
    ? (villages.find((v) => v.village_id === village_id) || {}).name_th || "-"
    : "ระดับตำบล";
  const tr = document.createElement("tr");
  tr.innerHTML =
    "<td>" + source.name_th + "</td><td>" + (SOURCE_TYPE_LABELS[source.source_type] || source.source_type) +
    "</td><td>" + villageLabel + "</td>";
  tbody.appendChild(tr);
}

// ---------- step 3b: อัปโหลดแหล่งน้ำจากไฟล์ ----------
let uploadedSourceFeatures = []; // [{lat, lon, name_th, source_type, stored_capacity_m3}]

document.getElementById("source-upload-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("source-upload-status");
  statusEl.textContent = "กำลังอ่านไฟล์...";
  try {
    const fc = await parseGeoFile(file);
    if (!fc.features.length) throw new Error("ไม่พบตำแหน่งในไฟล์");
    uploadedSourceFeatures = fc.features.map((f) => {
      const { lat, lon } = centroidLatLon(f.geometry); // จุด -> ใช้ตรงๆ, polygon (เช่นอ่างเก็บน้ำ) -> ใช้จุดศูนย์กลาง
      return {
        lat,
        lon,
        name_th: guessName(f.properties) || "",
        source_type: guessSourceType(f.properties) || "pond",
        stored_capacity_m3: guessCapacity(f.properties),
      };
    });
    renderSourceMatchTable();
    statusEl.textContent =
      "อ่านไฟล์สำเร็จ พบ " + uploadedSourceFeatures.length + " รายการ — ตรวจสอบ/แก้ไขในตารางก่อนยืนยัน";
  } catch (err) {
    statusEl.textContent = "อ่านไฟล์ไม่สำเร็จ: " + err.message;
  }
});

function renderSourceMatchTable() {
  const table = document.getElementById("source-match-table");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  const confirmBtn = document.getElementById("btn-confirm-source-upload");
  if (uploadedSourceFeatures.length === 0) {
    table.style.display = "none";
    confirmBtn.style.display = "none";
    return;
  }
  table.style.display = "";
  confirmBtn.style.display = "";

  uploadedSourceFeatures.forEach((item, idx) => {
    const tr = document.createElement("tr");
    tr.dataset.idx = String(idx);

    const tdName = document.createElement("td");
    const inputName = document.createElement("input");
    inputName.type = "text";
    inputName.value = item.name_th;
    inputName.dataset.field = "name_th";
    tdName.appendChild(inputName);

    const tdType = document.createElement("td");
    const selType = document.createElement("select");
    Object.keys(SOURCE_TYPE_LABELS).forEach((key) => {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = SOURCE_TYPE_LABELS[key];
      if (key === item.source_type) opt.selected = true;
      selType.appendChild(opt);
    });
    selType.dataset.field = "source_type";
    tdType.appendChild(selType);

    const tdCap = document.createElement("td");
    const inputCap = document.createElement("input");
    inputCap.type = "number";
    inputCap.min = "0";
    if (item.stored_capacity_m3 !== null) inputCap.value = item.stored_capacity_m3;
    inputCap.dataset.field = "stored_capacity_m3";
    tdCap.appendChild(inputCap);

    const tdVillage = document.createElement("td");
    const selVillage = document.createElement("select");
    const optNone = document.createElement("option");
    optNone.value = "";
    optNone.textContent = "-- ระดับตำบล --";
    selVillage.appendChild(optNone);
    villages.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.village_id;
      opt.textContent = "หมู่ " + v.moo + " " + v.name_th;
      selVillage.appendChild(opt);
    });
    selVillage.dataset.field = "village_id";
    tdVillage.appendChild(selVillage);

    tr.appendChild(tdName);
    tr.appendChild(tdType);
    tr.appendChild(tdCap);
    tr.appendChild(tdVillage);
    tbody.appendChild(tr);
  });
}

document.getElementById("btn-confirm-source-upload").addEventListener("click", async () => {
  const statusEl = document.getElementById("source-upload-status");
  const rows = document.querySelectorAll("#source-match-table tbody tr");
  let successCount = 0;
  for (const tr of rows) {
    const idx = parseInt(tr.dataset.idx, 10);
    const item = uploadedSourceFeatures[idx];
    const name_th = tr.querySelector('[data-field="name_th"]').value.trim();
    const source_type = tr.querySelector('[data-field="source_type"]').value;
    const capacityRaw = tr.querySelector('[data-field="stored_capacity_m3"]').value;
    const village_id = tr.querySelector('[data-field="village_id"]').value || null;
    if (!name_th) continue;
    try {
      const res = await authFetch("/water-sources", {
        method: "POST",
        body: JSON.stringify({
          tambon_id: currentTambonId,
          village_id,
          source_type,
          name_th,
          lat: item.lat,
          lon: item.lon,
          stored_capacity_m3: capacityRaw ? parseFloat(capacityRaw) : null,
          capacity_source_note: capacityRaw ? "นำเข้าจากไฟล์อัปโหลด (Phase 3)" : null,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "บันทึกไม่สำเร็จ");
      sourceMarkersGroup.addLayer(L.marker([item.lat, item.lon]).bindPopup(body.name_th));
      addSourceRow(body, village_id);
      sources.push({ source_id: body.source_id, name_th: body.name_th, source_type: body.source_type, village_id });
      successCount++;
    } catch (err) {
      alert('แถว "' + name_th + '" บันทึกไม่สำเร็จ: ' + err.message);
    }
  }
  renderReservoirMatrixSection();
  document.getElementById("step4").classList.add("active");
  document.getElementById("step5").classList.add("active");
  statusEl.textContent = "นำเข้าสำเร็จ " + successCount + " รายการ";
});

loadLookupData();
