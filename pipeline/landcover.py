"""
landcover.py — สัดส่วนการใช้ที่ดิน + ค่าสัมประสิทธิ์น้ำท่าถ่วงน้ำหนัก ต่อหมู่บ้าน (village_id)

**ไม่มีในโค้ดเดิม (03_legacy_prototype/) — เขียนใหม่ทั้งหมดสำหรับ Phase 2**
ตาม 00-system-design-reset.md ข้อ 2.1/ข้อ 4: แทนค่าคงที่ 0.3 เดี่ยวเดิม (ที่ใช้กับทุกพื้นที่
เหมือนกันหมดในไฟล์ Excel เก่า) ด้วยค่าถ่วงน้ำหนักจริงตามสัดส่วนการใช้ที่ดินของแต่ละหมู่บ้าน

--- ที่มาของข้อมูลการใช้ที่ดิน: ใช้ข้อมูลทางการ ไม่ใช่ Sentinel-2 classification ของเราเอง ---
แผนตั้งต้นคือจำแนกจาก Sentinel-2 ด้วย ESA WorldCover (global product) แต่ระหว่างทำ Phase 2 พบว่า
มีไฟล์ข้อมูลการใช้ที่ดินทางการ (ปี พ.ศ. 2566) อยู่แล้วใน D:\\WMB_NEW (ผู้ใช้ชี้ให้) ทดสอบ clip กับ
ขอบเขตตำบลแม่นาเรือแล้วได้พื้นที่ 61,149 ไร่ ตรงกับพื้นที่ทางการ 61,188 ไร่ (คลาดเคลื่อน 0.06%) —
แม่นยำกว่าและละเอียดกว่า WorldCover มาก (แยกชนิดพืชจริง เช่น นาข้าว/ข้าวโพด/ลำไย/ยางพารา ไม่ใช่แค่
"cropland" รวมๆ) จึงใช้ไฟล์นี้แทน — ดูที่มา/ขั้นตอนสกัดข้อมูลเต็มใน 04_scripts/extract_landuse_maenaruea.py

ผลคือโมดูลนี้เป็น**การคำนวณ geometry ล้วนๆ (shapely) ไม่ต้องเรียก Earth Engine เลย** — ต่างจากไฟล์
rainfall_et0.py/rice_paddy.py ที่ยังต้องพึ่ง GEE จริง (CHIRPS/MOD16A2/Sentinel-1 เป็น time series
รายเดือนจริง ไม่มีข้อมูลทางการทดแทนได้)

**ข้อจำกัดที่ต้องรู้**: ข้อมูลนี้เป็นภาพนิ่งปี 2566 (ไม่ใช่ time series รายเดือน) ดังนั้นค่าที่เขียนเข้า
zone_landcover_monthly จะ**เหมือนกันทุกเดือน**จนกว่าจะมีข้อมูลปีใหม่กว่านี้มาแทน — ตาราง _monthly
เก็บค่านี้ทุกเดือนเพราะ pipeline รันทุกเดือนอยู่แล้ว (ต้นทุนต่ำ) ไม่ใช่เพราะที่ดินเปลี่ยนรายเดือนจริง

--- ที่มาของค่าสัมประสิทธิ์น้ำท่า (runoff coefficient C) ---
ใช้ค่ามาตรฐานจากวิธี Rational Method (C-value) ที่ใช้กันทั่วไปในงานวิศวกรรมระบายน้ำ (เช่น ASCE
Manual of Practice No. 37 และตำรา hydrology ทั่วไป) ถ่วงน้ำหนักตาม 5 หมวดหลัก (LUL1_CODE) ของ
ข้อมูลการใช้ที่ดิน — **ไม่ได้ calibrate กับพื้นที่ลุ่มน้ำแม่นาเรือจริง** ถ้าต้องการความแม่นยำสูงกว่านี้
ควรเทียบกับวิธี DEM-based (D8/DTM) ที่ WMB_NEW กำลังทำอยู่ (00-system-design-reset.md ข้อ 15.2)
"""
import functools
from pathlib import Path

import shapely
from shapely.geometry import shape

# path อิงตำแหน่งไฟล์นี้เอง (ไม่ใช่ cwd ตอนรัน) กัน error ถ้ารันจากโฟลเดอร์อื่นที่ไม่ใช่ repo root
LANDUSE_GEOJSON_PATH = Path(__file__).parent / "data" / "geo" / "landuse_maenaruea_2566.geojson"

# LUL1_CODE = หมวดใหญ่ 5 หมวดของข้อมูลการใช้ที่ดิน (F=ป่า, A=เกษตร, U=ชุมชน/สิ่งปลูกสร้าง,
# M=อื่นๆ เช่น ทุ่งหญ้า/ดินโล่ง/เหมือง, W=แหล่งน้ำ) — ตรวจสอบความหมายจริงจาก LU_DES_TH ของแต่ละ
# หมวดแล้วตอนสกัดข้อมูล (ดู extract_landuse_maenaruea.py)
RUNOFF_C_BY_LUL1 = {
    "F": 0.15,  # ป่า
    "A": 0.35,  # เกษตร (ใกล้เคียงค่าคงที่ 0.3 เดิม แต่แยกตามพื้นที่จริงต่อหมู่บ้าน)
    "U": 0.65,  # ชุมชน/สิ่งปลูกสร้าง (หมู่บ้าน/ราชการ/ถนน — ชนบท ไม่ใช่เมืองหนาแน่น)
    "M": 0.30,  # ทุ่งหญ้า/ดินโล่ง/เหมือง/พื้นที่ถม (กึ่งธรรมชาติ)
    "W": 1.00,  # แหล่งน้ำผิวดิน (อ่าง/ลำห้วย/บ่อน้ำ) — ฝนที่ตกบนผิวน้ำนับเป็นน้ำท่าเต็มโดยนิยาม
}


@functools.lru_cache(maxsize=1)
def _load_landuse_features():
    """โหลดไฟล์ landuse_maenaruea_2566.geojson ครั้งเดียว (cache) — ใช้ซ้ำได้ทุกหมู่บ้านในรันเดียวกัน"""
    import json
    with open(LANDUSE_GEOJSON_PATH, encoding="utf-8") as f:
        fc = json.load(f)
    features = []
    for feat in fc["features"]:
        geom = shape(feat["geometry"])
        if geom.is_valid and not geom.is_empty:
            features.append((geom, feat["properties"]["LUL1_CODE"]))
    return features


def compute_landcover_breakdown(village_geom_geojson: dict) -> dict | None:
    """
    village_geom_geojson: GeoJSON geometry dict ของขอบเขตหมู่บ้าน (WGS84, จาก
    ST_AsGeoJSON(ST_Union(village_boundary_parts.geom)) — ดู pipeline/db.py::fetch_villages)

    คืน dict: {"forest_pct", "agri_pct", "residential_pct", "runoff_coefficient"} หรือ None
    ถ้าหมู่บ้านไม่มี geometry หรือไม่ทับกับข้อมูลการใช้ที่ดินเลย (ไม่ควรเกิดถ้าอยู่ในตำบลแม่นาเรือจริง)
    """
    if village_geom_geojson is None:
        return None

    village_geom = shape(village_geom_geojson)
    if not village_geom.is_valid:
        village_geom = shapely.make_valid(village_geom)

    area_by_lul1: dict[str, float] = {}
    total_area = 0.0

    for landuse_geom, lul1_code in _load_landuse_features():
        if not landuse_geom.intersects(village_geom):
            continue
        overlap = landuse_geom.intersection(village_geom)
        if overlap.is_empty:
            continue
        # ใช้พื้นที่เชิงมุม (องศา^2) เป็นตัวถ่วงน้ำหนักสัดส่วน — พอสำหรับหาสัดส่วน % เพราะ
        # เทียบเป็นอัตราส่วนกับพื้นที่รวมของหมู่บ้านเดียวกัน (การบิดเบือนจาก map projection
        # หักล้างกันเองในอัตราส่วน ไม่กระทบ % ที่ได้ ต่างจากถ้าต้องการค่าพื้นที่สัมบูรณ์จริง)
        a = overlap.area
        area_by_lul1[lul1_code] = area_by_lul1.get(lul1_code, 0.0) + a
        total_area += a

    if total_area == 0.0:
        return None

    pct_by_lul1 = {code: (a / total_area) * 100.0 for code, a in area_by_lul1.items()}
    weighted_c = sum(
        (pct_by_lul1.get(code, 0.0) / 100.0) * c for code, c in RUNOFF_C_BY_LUL1.items()
    )

    return {
        "forest_pct": round(pct_by_lul1.get("F", 0.0), 1),
        "agri_pct": round(pct_by_lul1.get("A", 0.0), 1),
        "residential_pct": round(pct_by_lul1.get("U", 0.0), 1),
        "runoff_coefficient": round(weighted_c, 3),
    }
