# backend/data/thai_admin/

ข้อมูลขอบเขตตำบลทั้งประเทศ (แปลงล่วงหน้าแล้ว) สำหรับหน้า admin-setup (Phase 3) — ใช้ตอนแอดมิน
เพิ่มตำบลใหม่ (นอกเหนือจากแม่นาเรือ) โดยไม่ต้องพิมพ์พิกัด/วาดขอบเขตเอง

| ไฟล์ | เนื้อหา |
|---|---|
| `thai_tambon_geometry.json.gz` | ขอบเขตตำบลทั้งประเทศ 8,105 ตำบล (WGS84/EPSG:4326, simplified ~30m) + พื้นที่ทางการ (`area_km2`) ต่อตำบล |

**ที่มา**: `D:\AI\Water_balance\01_raw_data\เขตปกครอง\THA_Tambon.shp` (ฐานข้อมูลทั้งประเทศ,
EPSG:32647) — แปลง/simplify/gzip ด้วย `04_scripts/extract_thai_tambon_geometry.py` (ทำครั้งเดียว
ตอนพัฒนา Phase 3, ดูเหตุผลและรายละเอียดขั้นตอนเต็มในหัวไฟล์นั้นและใน `backend/thai_admin_boundary.py`)

**อ่านไฟล์นี้ยังไงในโค้ด**: ดู `backend/thai_admin_boundary.py::find_tambon_geometry()` — โหลดครั้งเดียว
(cache ในหน่วยความจำ) แล้ว match ด้วยชื่อจังหวัด/อำเภอ/ตำบลภาษาไทยแบบตรงตัว (exact match) ไม่ใช่ fuzzy
search — ค่าที่ใช้ค้นต้องมาจาก dropdown ที่ผูกกับ `frontend/data/admin_boundary_lookup.json` เท่านั้น

**ทำไม backend ไม่ต้องพึ่ง pyshp/pyproj/shapely**: ไฟล์นี้แปลง CRS (UTM47N→WGS84) และ simplify
เรียบร้อยแล้วตั้งแต่ตอนสร้าง — runtime อ่านแค่ gzip+json (standard library) แล้วส่ง geometry ตรงๆ
เข้า `ST_GeomFromGeoJSON()` ของ PostGIS ผ่าน parameterized query

**ข้อจำกัด**: geometry simplified ~30m — เหมาะสำหรับแสดงผลแผนที่และคำนวณ zonal stats กับข้อมูล
remote-sensing (CHIRPS ~5.5km, MODIS ~500m) แต่ไม่เหมาะเป็นขอบเขตทางกฎหมาย/ที่ดินระดับแปลง —
`area_km2` ที่ endpoint คืนมาใช้ค่าจาก `.dbf` ต้นฉบับตรงๆ ไม่ได้คำนวณจาก geometry ที่ simplify แล้ว
