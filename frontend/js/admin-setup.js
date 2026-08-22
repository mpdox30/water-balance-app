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
let villages = []; // [{village_id, moo, name_th, area_rai}]
let activeDrawVillageId = null;
let pinMode = false;
let pendingMarker = null;

// ---------- map setup ----------
const map = L.map("map").setView([13.75, 100.5], 6); // เริ่มที่ตำแหน่งกลางประเทศไทย
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap",
  maxZoom: 19,
}).addTo(map);

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
  try {
    const res = await authFetch("/village-boundary-parts", {
      method: "POST",
      body: JSON.stringify({ village_id: activeDrawVillageId, part_label: null, geom_geojson: geojson }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกขอบเขตไม่สำเร็จ");
    layer.bindPopup(villages.find((v) => v.village_id === activeDrawVillageId).name_th + " (" + body.area_rai + " ไร่)");
    drawnVillageLayers.addLayer(layer);
    const v = villages.find((x) => x.village_id === activeDrawVillageId);
    v.area_rai = (v.area_rai || 0) + body.area_rai;
    renderVillageTable();
    document.getElementById("draw-hint").style.display = "none";
    activeDrawVillageId = null;
  } catch (err) {
    alert("บันทึกขอบเขตไม่สำเร็จ: " + err.message);
  }
});

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
  previewLayerGroup.clearLayers();
  pendingLookupResult = null;
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
      "<td>" + (v.area_rai ? v.area_rai.toFixed(1) : "ยังไม่ได้วาด") + "</td>" +
      '<td class="village-row-actions"></td>';
    const btn = document.createElement("button");
    btn.textContent = "วาดขอบเขต";
    btn.className = "secondary";
    btn.addEventListener("click", () => {
      activeDrawVillageId = v.village_id;
      document.getElementById("draw-target-name").textContent = "หมู่ " + v.moo + " " + v.name_th;
      document.getElementById("draw-hint").style.display = "";
    });
    tr.querySelector(".village-row-actions").appendChild(btn);
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
}

document.getElementById("btn-add-village").addEventListener("click", async () => {
  const moo = parseInt(document.getElementById("village-moo").value, 10);
  const name_th = document.getElementById("village-name").value.trim();
  const statusEl = document.getElementById("village-add-status");
  if (!moo || !name_th) {
    statusEl.textContent = "กรอกหมู่ที่และชื่อหมู่บ้านให้ครบ";
    return;
  }
  statusEl.textContent = "กำลังเพิ่ม...";
  try {
    const res = await authFetch("/villages", {
      method: "POST",
      body: JSON.stringify({ tambon_id: currentTambonId, moo, name_th, name_source: "manual (admin-setup Phase 3)" }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "เพิ่มหมู่บ้านไม่สำเร็จ");
    villages.push({ village_id: body.village_id, moo: body.moo, name_th: body.name_th, area_rai: 0 });
    renderVillageTable();
    document.getElementById("village-moo").value = "";
    document.getElementById("village-name").value = "";
    statusEl.innerHTML = '<span class="ok">เพิ่ม "' + body.name_th + '" แล้ว — วาดขอบเขตในตารางด้านล่าง</span>';
    document.getElementById("step3").classList.add("active");
  } catch (err) {
    statusEl.textContent = "เพิ่มหมู่บ้านไม่สำเร็จ: " + err.message;
  }
});

// ---------- step 3: แหล่งน้ำ ----------
document.getElementById("btn-pin-mode").addEventListener("click", () => {
  pinMode = !pinMode;
  document.getElementById("btn-pin-mode").textContent = pinMode ? "กำลังปักหมุด (คลิกบนแผนที่)" : "เริ่มปักหมุดบนแผนที่";
  if (!pinMode) {
    document.getElementById("pin-status").textContent = pendingMarker ? "ปักหมุดแล้ว (แก้ตำแหน่งได้ที่ปุ่มด้านบน)" : "ยังไม่ได้ปักหมุด";
  }
});

document.getElementById("btn-save-source").addEventListener("click", async () => {
  if (!pendingMarker) return;
  const statusEl = document.getElementById("pin-status");
  const latlng = pendingMarker.getLatLng();
  const name_th = document.getElementById("source-name").value.trim();
  const source_type = document.getElementById("source-type").value;
  const village_id = document.getElementById("source-village").value || null;
  const capacityRaw = document.getElementById("source-capacity").value;
  if (!name_th) {
    statusEl.textContent = "กรอกชื่อแหล่งน้ำก่อน";
    return;
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
        stored_capacity_m3: capacityRaw ? parseFloat(capacityRaw) : null,
        capacity_source_note: capacityRaw ? "กรอกโดย admin ตอน setup (Phase 3)" : null,
      }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "บันทึกแหล่งน้ำไม่สำเร็จ");
    sourceMarkersGroup.addLayer(L.marker(latlng).bindPopup(body.name_th));
    addSourceRow(body, village_id);
    map.removeLayer(pendingMarker);
    pendingMarker = null;
    pinMode = false;
    document.getElementById("btn-pin-mode").textContent = "เริ่มปักหมุดบนแผนที่";
    document.getElementById("btn-save-source").disabled = true;
    document.getElementById("pin-status").textContent = "บันทึกแล้ว — ปักหมุดจุดถัดไปได้เลย";
    document.getElementById("source-name").value = "";
    document.getElementById("source-capacity").value = "";
    document.getElementById("step4").classList.add("active");
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
  const typeLabels = {
    pond: "สระ",
    reservoir: "อ่างเก็บน้ำ",
    groundwater_well: "บ่อบาดาล",
    mountain_spring: "น้ำผุดจากภูเขา",
    purchased_external: "ซื้อน้ำจากภายนอก",
  };
  const tr = document.createElement("tr");
  tr.innerHTML =
    "<td>" + source.name_th + "</td><td>" + (typeLabels[source.source_type] || source.source_type) +
    "</td><td>" + villageLabel + "</td>";
  tbody.appendChild(tr);
}

loadLookupData();
