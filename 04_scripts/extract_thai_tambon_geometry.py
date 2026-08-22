"""
extract_thai_tambon_geometry.py — สร้าง backend/data/thai_admin/thai_tambon_geometry.json.gz
(ทำครั้งเดียวตอนพัฒนา Phase 3 — ไม่ใช่ส่วนหนึ่งของ backend/pipeline ที่ deploy จริง)

ที่มา: D:\\AI\\Water_balance\\01_raw_data\\เขตปกครอง\\THA_Tambon.shp (+ .dbf + .shx)
  - shapefile ทั้งประเทศ 8,105 ตำบล, CRS ต้นฉบับ = EPSG:32647 (WGS 84 / UTM zone 47N)
  - ตรวจสอบแล้วว่าลำดับแถวตรงกับ pipeline/data/geo/admin_boundary_lookup.json ทุกแถว (สุ่มตรวจ 200
    แถว + ตรวจแม่นาเรือ index 5705 ตรงกัน) — สองไฟล์นี้มาจากต้นฉบับเดียวกัน แต่ endpoint จริง
    (backend/thai_admin_boundary.py) match ด้วยชื่อจังหวัด/อำเภอ/ตำบล ไม่ใช่ index ตำแหน่ง เพื่อไม่ผูก
    กับลำดับแถวที่อาจเปลี่ยนถ้ามีคนแก้ admin_boundary_lookup.json ทีหลัง (เช่น เรียงตามตัวอักษรใหม่)
  - ตรวจสอบแล้วว่าทั้ง 8,105 ตำบลเป็น Polygon เดี่ยวล้วน (ไม่มี MultiPolygon) และ geometry ทุกอันถูกต้อง
    (is_valid=True) — จึงไม่ต้องมี logic แยกกรณี MultiPolygon (เช่น เลือกเอาแค่ชิ้นใหญ่สุด)

ขั้นตอน:
1. อ่านทุกแถวจาก THA_Tambon.shp/.dbf ด้วย pyshp (random access ผ่าน .shx — เร็ว ไม่ต้องโหลดทั้งไฟล์)
2. แปลง geometry จาก UTM47N → WGS84 ด้วย pyproj.Transformer
3. Simplify ด้วย shapely (tolerance=0.0003 องศา ≈ 30 เมตรที่ละติจูดไทย, preserve_topology=True) —
   ลดขนาดไฟล์ลงมาก (52.7MB shapefile ต้นฉบับ → ~27MB JSON ดิบ → ~11MB gzip) โดยความคลาดเคลื่อนเชิงพื้นที่
   เล็กน้อยกว่า resolution ของข้อมูล remote-sensing ที่ใช้คำนวณสมดุลน้ำอยู่แล้วมาก (CHIRPS ~5.5km,
   MODIS ~500m) จึงไม่กระทบความแม่นยำของ pipeline/rainfall_et0.py
4. เก็บเป็น JSON array (key ย่อ p/pe/a/ae/t/te/area_km2/geom) แล้ว gzip (compresslevel=9)
5. บันทึก area_km2 จาก .dbf ตรงๆ (ไม่ได้คำนวณจาก geometry ที่ simplify แล้ว) เพื่อความแม่นยำของตัวเลขพื้นที่

ทำไมแปลงล่วงหน้าแทนที่จะให้ backend อ่าน shapefile สดตอน request — ดูเหตุผนเต็มใน
backend/thai_admin_boundary.py หัวไฟล์ (ไฟล์ .shp ต้นฉบับ 52.7MB เกินขีดจำกัดการส่งไฟล์กลับเครื่อง
ผู้ใช้ทีละไฟล์ + backend ที่ deploy จริงไม่ต้องพึ่ง pyshp/pyproj/shapely เลยถ้าแปลงไว้ล่วงหน้าแล้ว)

รันใหม่เฉพาะถ้า:
- THA_Tambon.shp ต้นฉบับอัปเดต (เช่น กรมการปกครองออกเขตแดนใหม่)
- ต้องการปรับ tolerance การ simplify (เช่น ตำบลที่จะเป็นนำร่องถัดไปต้องการความละเอียดสูงกว่านี้ —
  แนะนำให้แยกไปทำแบบ extract_landuse_maenaruea.py คือตัดเฉพาะตำบลนั้นด้วย tolerance ต่ำกว่านี้แทน
  ไม่ต้องลด tolerance รวมทั้งไฟล์ เพราะจะทำให้ไฟล์ใหญ่ขึ้นทั้งประเทศโดยไม่จำเป็น)

Dependencies (ใช้เฉพาะตอนรันสคริปต์นี้ ไม่ใช่ requirements.txt ของ backend จริง):
    pip install pyshp pyproj shapely
"""
import gzip
import json
import os

import pyproj
import shapefile
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

SOURCE_SHP_BASE = r"D:\AI\Water_balance\01_raw_data\เขตปกครอง\THA_Tambon"  # ปรับ path ตามเครื่องที่รัน
OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "backend", "data", "thai_admin", "thai_tambon_geometry.json.gz"
)
SIMPLIFY_TOLERANCE_DEG = 0.0003  # ~30 เมตรที่ละติจูดไทย


def main():
    reader = shapefile.Reader(
        shp=SOURCE_SHP_BASE + ".shp",
        shx=SOURCE_SHP_BASE + ".shx",
        dbf=SOURCE_SHP_BASE + ".dbf",
        encoding="utf-8",
    )
    transformer = pyproj.Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)

    out = []
    for i in range(len(reader)):
        sr = reader.shapeRecord(i)
        geom_utm = shape(sr.shape.__geo_interface__)
        geom_wgs = shp_transform(transformer.transform, geom_utm)
        geom_simplified = geom_wgs.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        rec = sr.record.as_dict()
        out.append(
            {
                "p": rec["P_NAME_T"],
                "pe": rec["P_NAME_E"],
                "a": rec["A_NAME_T"],
                "ae": rec["A_NAME_E"],
                "t": rec["T_NAME_T"],
                "te": rec["T_NAME_E"],
                "area_km2": round(rec["Area_km2"], 4),
                "geom": mapping(geom_simplified),
            }
        )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with gzip.open(OUTPUT_PATH, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"เขียน {len(out)} ตำบล -> {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
