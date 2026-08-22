// geo-upload.js — parse ไฟล์ขอบเขต/ตำแหน่งที่ admin อัปโหลด (Shapefile .zip / GeoJSON / KML)
// ทั้งหมด parse ฝั่ง client (browser) ไม่ผ่าน backend เลย เพราะ:
// 1. backend endpoint เดิม (/tambons, /village-boundary-parts, /water-sources) รับ geometry/lat-lon
//    ที่แปลงเป็น WGS84 GeoJSON แล้วอยู่แล้ว ไม่ต้องเพิ่ม dependency (GDAL/pyshp/pyproj) ฝั่ง backend เลย
// 2. shpjs แปลง CRS ให้อัตโนมัติ (อ่าน .prj ในไฟล์ zip) ไม่ต้องรู้ CRS ต้นฉบับล่วงหน้า
//
// ไลบรารีที่ใช้ (โหลดจาก CDN ใน admin-setup.html ก่อนไฟล์นี้):
//   shpjs      — https://github.com/calvinmetcalf/shapefile-js (แปลง shapefile .zip -> GeoJSON)
//   @tmcw/togeojson — แปลง KML -> GeoJSON
//   @turf/turf v6   — คำนวณพื้นที่/intersect สำหรับเตือน (ไม่ block) กรณีขอบเขตไม่แนบสนิท

/** อ่านไฟล์ที่ admin เลือก (.zip / .geojson / .json / .kml) แล้วคืนเป็น GeoJSON FeatureCollection เสมอ */
async function parseGeoFile(file) {
  const name = file.name.toLowerCase();
  let raw;
  if (name.endsWith(".zip")) {
    const buf = await file.arrayBuffer();
    raw = await shp(buf); // shpjs แปลง CRS -> WGS84 ให้อัตโนมัติจาก .prj ในไฟล์
  } else if (name.endsWith(".kml")) {
    const text = await file.text();
    const dom = new DOMParser().parseFromString(text, "text/xml");
    raw = toGeoJSON.kml(dom); // KML เป็น WGS84 อยู่แล้วตาม spec เสมอ
  } else if (name.endsWith(".geojson") || name.endsWith(".json")) {
    raw = JSON.parse(await file.text());
  } else {
    throw new Error("รองรับเฉพาะไฟล์ .zip (shapefile), .geojson/.json, หรือ .kml");
  }
  return normalizeToFeatureCollection(raw);
}

function normalizeToFeatureCollection(geojson) {
  // shpjs อาจคืน array ของ FeatureCollection ถ้า zip มีหลาย layer -> รวมเป็นอันเดียว
  if (Array.isArray(geojson)) {
    const features = geojson.flatMap((fc) => fc.features || []);
    return { type: "FeatureCollection", features };
  }
  if (geojson.type === "FeatureCollection") return geojson;
  if (geojson.type === "Feature") return { type: "FeatureCollection", features: [geojson] };
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: geojson }] };
}

/** % พื้นที่ของ geom ที่อยู่ "นอก" containerGeom (0 = อยู่ในสนิท, 100 = อยู่นอกทั้งหมด)
 * คืน null ถ้าคำนวณไม่ได้ (geometry ซับซ้อน/ผิดปกติเกินไป) — เรียกใช้แล้วต้องเช็ค null ก่อนแสดงผล
 * เตือนเฉยๆ ไม่ block การบันทึก (ตามที่ตกลงกันไว้ — ข้อมูล GIS จริงมักมีส่วนต่างเล็กน้อยตามธรรมชาติ) */
function percentOutside(geom, containerGeom) {
  try {
    const totalArea = turf.area(turf.feature(geom));
    if (totalArea === 0) return 0;
    const inter = turf.intersect(turf.feature(geom), turf.feature(containerGeom));
    const insideArea = inter ? turf.area(inter) : 0;
    return Math.max(0, Math.min(100, ((totalArea - insideArea) / totalArea) * 100));
  } catch (e) {
    return null;
  }
}

/** % พื้นที่ของ geom ที่ทับซ้อนกับ geometry อื่นๆ ใน otherGeoms (รวมกัน, นับซ้ำถ้าทับหลายอัน) */
function percentOverlap(geom, otherGeoms) {
  try {
    const totalArea = turf.area(turf.feature(geom));
    if (totalArea === 0 || !otherGeoms || otherGeoms.length === 0) return 0;
    let overlapArea = 0;
    for (const other of otherGeoms) {
      try {
        const inter = turf.intersect(turf.feature(geom), turf.feature(other));
        if (inter) overlapArea += turf.area(inter);
      } catch (e) {
        // geometry คู่นี้คำนวณไม่ได้ — ข้ามไปเฉยๆ ไม่ทำให้ทั้งฟังก์ชัน fail
      }
    }
    return Math.max(0, Math.min(100, (overlapArea / totalArea) * 100));
  } catch (e) {
    return null;
  }
}

/** พื้นที่ของ geometry ในหน่วยไร่ */
function areaRai(geom) {
  try {
    return turf.area(turf.feature(geom)) / 1600.0;
  } catch (e) {
    return 0;
  }
}

/** จุดศูนย์กลางของ geometry ใดๆ (ใช้แปลง polygon เป็น lat/lon จุดเดียวสำหรับแหล่งน้ำ) */
function centroidLatLon(geom) {
  const c = turf.centroid(turf.feature(geom));
  return { lat: c.geometry.coordinates[1], lon: c.geometry.coordinates[0] };
}

/** แปลง geometry ให้เป็น Polygon เดี่ยวเสมอ (ตาราง tambons/village_boundary_parts บังคับ
 * geometry(Polygon, 4326) เท่านั้น ไม่รับ MultiPolygon) — shapefile หลายตัวห่อ polygon เดี่ยวเป็น
 * MultiPolygon (1 ส่วน) ตามธรรมเนียม GDAL/shapefile ซึ่งกรณีนี้แปลงตรงๆ ได้ไม่เสียอะไร
 * ถ้ามีหลายส่วนจริง (เช่น ตำบล/หมู่บ้านมีเกาะ) จะเอาเฉพาะส่วนที่พื้นที่ใหญ่สุด + คืน note เตือนไว้
 * คืน {geom, note} — geom เป็น null ถ้าไม่ใช่ Polygon/MultiPolygon เลย (เช่น อัปโหลดไฟล์จุดผิดที่) */
function toSinglePolygon(geom) {
  if (geom.type === "Polygon") return { geom, note: null };
  if (geom.type === "MultiPolygon") {
    if (geom.coordinates.length === 1) {
      return { geom: { type: "Polygon", coordinates: geom.coordinates[0] }, note: null };
    }
    let bestIdx = 0;
    let bestArea = 0;
    geom.coordinates.forEach((rings, i) => {
      let a = 0;
      try {
        a = turf.area(turf.polygon(rings));
      } catch (e) {
        a = 0;
      }
      if (a > bestArea) {
        bestArea = a;
        bestIdx = i;
      }
    });
    return {
      geom: { type: "Polygon", coordinates: geom.coordinates[bestIdx] },
      note:
        "ไฟล์นี้มีขอบเขตแยกกัน " + geom.coordinates.length + " ส่วน (เช่น เกาะ/พื้นที่ไม่ต่อเนื่อง) — " +
        "ใช้เฉพาะส่วนที่ใหญ่ที่สุด ส่วนอื่นถูกตัดออกจากขอบเขตนี้",
    };
  }
  return { geom: null, note: "ประเภท geometry ในไฟล์ (" + geom.type + ") ไม่ใช่ Polygon/MultiPolygon — ใช้ไม่ได้กับช่องนี้" };
}

// เดา field ที่น่าจะเก็บ "หมู่ที่"/"ชื่อ"/"ประเภทแหล่งน้ำ"/"ความจุ" จาก properties ของ feature ที่อัปโหลด
// (ไฟล์จริงมีชื่อ field ไม่เหมือนกันแต่ละที่มา — เดาแบบ best-effort แล้วให้ admin ยืนยัน/แก้เองในตาราง)
function guessField(properties, candidates) {
  for (const c of candidates) {
    if (properties[c] !== undefined && properties[c] !== null && properties[c] !== "") return properties[c];
  }
  // ลองแบบไม่สนตัวพิมพ์เล็ก-ใหญ่
  const lowerMap = {};
  for (const k of Object.keys(properties)) lowerMap[k.toLowerCase()] = properties[k];
  for (const c of candidates) {
    const v = lowerMap[c.toLowerCase()];
    if (v !== undefined && v !== null && v !== "") return v;
  }
  return null;
}

function guessMoo(properties) {
  const v = guessField(properties, ["moo", "MOO", "หมู่", "หมู่ที่", "MOO_ID", "village_no", "VILL_NO", "MOOBAAN"]);
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}

function guessName(properties) {
  return guessField(properties, ["name_th", "name", "NAME", "ชื่อ", "ชื่อหมู่บ้าน", "VILL_NAME", "TB_NAME", "Name"]);
}

function guessSourceType(properties) {
  const v = guessField(properties, ["type", "source_type", "ประเภท", "TYPE"]);
  if (!v) return null;
  const s = String(v).toLowerCase();
  if (s.includes("อ่าง") || s.includes("reservoir")) return "reservoir";
  if (s.includes("สระ") || s.includes("pond")) return "pond";
  if (s.includes("บาดาล") || s.includes("well") || s.includes("groundwater")) return "groundwater_well";
  if (s.includes("ภูเขา") || s.includes("spring")) return "mountain_spring";
  return null;
}

function guessCapacity(properties) {
  const v = guessField(properties, ["capacity", "stored_capacity_m3", "ความจุ", "CAPACITY", "vol_m3"]);
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}
