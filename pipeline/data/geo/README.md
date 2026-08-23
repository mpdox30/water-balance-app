# pipeline/data/geo/

GeoJSON (WGS84 / EPSG:4326) แปลงจาก shapefile ต้นฉบับใน `01_raw_data/` โดย
`04_scripts/convert_shapefiles_to_geojson.py` — สร้างขึ้นใน Phase 0 (2026-08-21)

| ไฟล์ | เนื้อหา | หมายเหตุ |
|---|---|---|
| `tambon_maenaruea.geojson` | ขอบเขตตำบลแม่นาเรือ (97.9 ตร.กม. — ค่าทางการ) | geometry simplify แล้ว (RDP, epsilon≈55m) สำหรับใช้แสดงผลบนแผนที่ — ความละเอียดเต็มอยู่ที่ต้นฉบับ `01_raw_data/ขอบเขตตำบล/` |
| `villages_maenaruea.geojson` | ขอบเขต 18 หมู่บ้าน (20 polygon — หมู่ 9/11 มีเขต1/เขต2) | ชื่อหมู่บ้านมาจาก crosswalk ที่ตรวจสอบแล้ว ไม่ใช่ field เดิมของ shapefile (เสีย encoding กู้ไม่ได้) |
| `zone_a_rainfed.geojson` | โซนเกษตรน้ำฝน | |
| `zone_b_irrigated.geojson` | โซนเกษตรชลประทาน (3 พื้นที่ตามอ่างที่เลี้ยง) | |
| `reservoirs_5.geojson` | อ่างเก็บน้ำหลัก 5 แห่ง พร้อม `telemetry_code` | |
| `admin_boundary_lookup.json` | จังหวัด/อำเภอ/ตำบลทั้งประเทศ (8,105 แถว, attribute เท่านั้น ไม่มี geometry) | สำหรับ cascading dropdown หน้า admin-setup (Phase 3) — geometry ของตำบลอื่นนอกจากแม่นาเรือจะแปลงเฉพาะตัวที่ถูกเลือกจริงตอน setup |
| `landuse_maenaruea_2566.geojson` | ข้อมูลการใช้ที่ดินทางการปี 2566 (1,546 polygon, clip เฉพาะในเขตตำบลแม่นาเรือเท่านั้น — **ไม่ครอบคลุมตำบลอื่น**) — ที่มา `D:\WMB_NEW\00_inputs_frozen\01_raw_data\lulc\merge_landuse_32647@256804.gpkg` (ทั้งประเทศ, ผู้ใช้ชี้ให้ระหว่างทำ Phase 2) | ใช้แทน Sentinel-2 classification ใน `pipeline/landcover.py` เฉพาะแม่นาเรือ — ตรวจสอบไขว้กับพื้นที่ตำบลทางการแล้ว คลาดเคลื่อน 0.06% — ที่มา/สคริปต์สกัดข้อมูลเต็มดูที่ `04_scripts/extract_landuse_maenaruea.py` |

ข้อมูลชุดเดียวกันนี้ (ไฟล์ .geojson 5 ไฟล์ + .json 1 ไฟล์) ยัง seed เข้า Supabase แล้วด้วย
(ดู `../../../04_scripts/002_seed_maenaruea.sql`) — ไฟล์ในโฟลเดอร์นี้คือสำเนาไว้ใช้ฝั่ง frontend/pipeline
โดยตรง (เช่น วาดแผนที่ Leaflet) โดยไม่ต้องยิง query หา DB ทุกครั้ง

## ตำบลอื่นนอกจากแม่นาเรือ (2026-08-23)

`landuse_maenaruea_2566.geojson` ข้างต้นไม่ครอบคลุมตำบลอื่น (พิสูจน์แล้วจริงกับนครป่าหมาก จ.พิษณุโลก —
รัน pipeline ผ่านแล้วแต่ runoff_coefficient ไม่ถูกเขียนเลยเงียบๆ เพราะพื้นที่ไม่ทับกับไฟล์นี้เลย)
แทนที่จะต้อง clip ไฟล์ `merge_landuse_32647@256804.gpkg` (5.8GB) ใหม่ทุกครั้งที่มีตำบลใหม่เข้าระบบ —
`pipeline/landcover.py::compute_landcover_breakdown()` จะตกไปใช้ **ESA WorldCover v200 ผ่าน Earth
Engine โดยอัตโนมัติ** ทันทีที่หมู่บ้านไม่ทับกับไฟล์ในโฟลเดอร์นี้เลย ไม่ต้องแก้โค้ด/เพิ่มไฟล์อะไรเมื่อเพิ่ม
ตำบลใหม่ — ดูรายละเอียด mapping และข้อจำกัดในคอมเมนต์หัวไฟล์ `pipeline/landcover.py`

ถ้าภายหลังต้องการความแม่นยำระดับ LDD ให้ตำบลใดตำบลหนึ่งโดยเฉพาะ (เช่น นครป่าหมาก) ค่อย clip ไฟล์จาก
`D:\WMB_NEW\...\merge_landuse_32647@256804.gpkg` เพิ่มตามแบบ `extract_landuse_maenaruea.py` แล้ววาง
ไฟล์ผลลัพธ์ไว้ในโฟลเดอร์นี้ — ปัจจุบัน `_load_landuse_features()` โหลดแค่ไฟล์แม่นาเรือไฟล์เดียว hardcode
path ไว้ ถ้าจะรองรับไฟล์ทางการหลายตำบลพร้อมกันต้องแก้ให้โหลดทุกไฟล์ในโฟลเดอร์นี้แทน
