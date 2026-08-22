"""
thai_admin_boundary.py — ค้นหาขอบเขตตำบล (geometry) จากฐานข้อมูลทั้งประเทศ สำหรับ Phase 3
(หน้า admin-setup: เพิ่มตำบลใหม่แบบ "ไม่มีช่องพิมพ์ข้อความอิสระสำหรับตำแหน่ง/พื้นที่เลย")

--- ที่มาของข้อมูล ---
ต้นฉบับ: D:\\AI\\Water_balance\\01_raw_data\\เขตปกครอง\\THA_Tambon.shp (+ .dbf + .shx)
  - shapefile ทั้งประเทศ 8,105 ตำบล, CRS = EPSG:32647 (WGS 84 / UTM zone 47N)
  - field ที่ใช้จาก .dbf: P_NAME_T/A_NAME_T/T_NAME_T (ชื่อจังหวัด/อำเภอ/ตำบลภาษาไทย),
    P_NAME_E/A_NAME_E/T_NAME_E (อังกฤษ), Area_km2
  - ตรวจสอบแล้ว: ทั้ง 8,105 ตำบลเป็น Polygon เดี่ยวล้วน (ไม่มี MultiPolygon/geometry เสีย) และ
    ลำดับแถวตรงกับ pipeline/data/geo/admin_boundary_lookup.json ทุกแถว (สุ่มตรวจ 200 แถว + ตรวจ
    แม่นาเรือ index 5705 ตรงกัน) — ยืนยันว่าทั้งสองไฟล์มาจากต้นฉบับเดียวกัน

--- ทำไมไม่แปลง (shapefile→WGS84) แบบ real-time ตอน request ---
ลองแล้วด้วย pyshp (random access ผ่าน .shx) + pyproj ตอน request จริงทำได้ (<10ms ต่อตำบล) แต่ตัดสินใจ
แปลงล่วงหน้า (offline, ครั้งเดียว) แทน เพราะ:
1. ตัดปัญหาไฟล์ .shp ต้นฉบับ 52.7MB เกินขีดจำกัดไฟล์เดี่ยวของเครื่องมือส่งไฟล์กลับไปเครื่องผู้ใช้ (20MB/ไฟล์)
   — ไฟล์ที่แปลง+simplify+gzip แล้วเหลือ ~11MB
2. backend ที่ deploy จริง (Render free tier) ไม่ต้องพึ่ง pyshp/pyproj/shapely เลย — ใช้ gzip+json
   จาก standard library ล้วนๆ ลด dependency/เวลา build/ความเสี่ยง build fail บน free tier
3. เร็วกว่า (ไม่ต้องเปิด/อ่าน binary shapefile ทุก request)

ขั้นตอนแปลง (ทำครั้งเดียว ไม่ได้รันเป็นส่วนหนึ่งของ backend):
  สำหรับตำบลทุกแถวใน THA_Tambon.shp: อ่าน geometry (UTM47N) → แปลงเป็น WGS84 (pyproj) →
  simplify (shapely, tolerance=0.0003 องศา ≈ 30 เมตร ที่ละติจูดไทย, preserve_topology=True) →
  เก็บเป็น JSON แถวเดียว (key ย่อ: p/pe/a/ae/t/te/area_km2/geom) → gzip ทั้งไฟล์
  ผลลัพธ์: data/thai_admin/thai_tambon_geometry.json.gz (8,105 ตำบล, ~11MB)

**ข้อจำกัดที่ต้องรู้**: geometry ที่ได้ simplify แล้ว (~30m) เหมาะสำหรับแสดงผลแผนที่ + คำนวณ zonal
stats กับข้อมูล remote-sensing ที่ resolution หยาบกว่ามาก (CHIRPS ~5.5km, MODIS ~500m) จึงไม่กระทบ
ความแม่นยำของ pipeline/rainfall_et0.py แต่ **ไม่เหมาะเป็นขอบเขตทางกฎหมาย/ที่ดินระดับแปลง** —
area_km2 ที่คืนมาใช้ค่าจาก Area_km2 ใน .dbf ต้นฉบับตรงๆ (ไม่ได้คำนวณจาก geometry ที่ simplify แล้ว)
เพื่อความแม่นยำของตัวเลขพื้นที่ — ถ้าตำบลไหนต้องการขอบเขตละเอียดกว่านี้ (เช่น จะมาเป็นตำบลนำร่องถัดไป)
ควรตัดออกมาแปลงใหม่จาก .shp ต้นฉบับด้วย tolerance ต่ำกว่านี้ (ดู 04_scripts/extract_landuse_maenaruea.py
เป็นตัวอย่างขั้นตอนแปลงข้อมูล GIS แบบละเอียดที่ทำไว้กับแม่นาเรือ)
"""
import functools
import gzip
import json
from pathlib import Path

GEOMETRY_PATH = Path(__file__).parent / "data" / "thai_admin" / "thai_tambon_geometry.json.gz"


@functools.lru_cache(maxsize=1)
def _load_all() -> list[dict]:
    """โหลดไฟล์ทั้งประเทศครั้งเดียว (cache ในหน่วยความจำ — ไฟล์ ~11MB gzip / ~27MB JSON ดิบ
    ในหน่วยความจำ ไม่หนักสำหรับ Render free tier 512MB)"""
    with gzip.open(GEOMETRY_PATH, "rt", encoding="utf-8") as f:
        return json.load(f)


def find_tambon_geometry(province_th: str, amphoe_th: str, tambon_th: str) -> dict | None:
    """หา geometry ของตำบลจากชื่อจังหวัด/อำเภอ/ตำบลภาษาไทย (match แบบ exact string —
    ค่าที่ส่งเข้ามาต้องมาจาก dropdown ที่ผูกกับ admin_boundary_lookup.json เท่านั้น ไม่ใช่พิมพ์เอง)

    คืน dict: {"geom_geojson", "area_km2", "name_en", "province_en", "amphoe_en"} หรือ None ถ้าไม่เจอ
    """
    for rec in _load_all():
        if rec["p"] == province_th and rec["a"] == amphoe_th and rec["t"] == tambon_th:
            return {
                "geom_geojson": rec["geom"],
                "area_km2": rec["area_km2"],
                "name_en": rec["te"],
                "province_en": rec["pe"],
                "amphoe_en": rec["ae"],
            }
    return None
