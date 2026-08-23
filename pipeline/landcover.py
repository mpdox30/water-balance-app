"""
landcover.py — สัดส่วนการใช้ที่ดิน + ค่าสัมประสิทธิ์น้ำท่าถ่วงน้ำหนัก ต่อหมู่บ้าน (village_id)

**ไม่มีในโค้ดเดิม (03_legacy_prototype/) — เขียนใหม่ทั้งหมดสำหรับ Phase 2**
ตาม 00-system-design-reset.md ข้อ 2.1/ข้อ 4: แทนค่าคงที่ 0.3 เดี่ยวเดิม (ที่ใช้กับทุกพื้นที่
เหมือนกันหมดในไฟล์ Excel เก่า) ด้วยค่าถ่วงน้ำหนักจริงตามสัดส่วนการใช้ที่ดินของแต่ละหมู่บ้าน

--- ที่มาของข้อมูลการใช้ที่ดิน: ใช้ข้อมูลทางการ ไม่ใช่ Sentinel-2 classification ของเราเอง (เฉพาะแม่นาเรือ) ---
แผนตั้งต้นคือจำแนกจาก Sentinel-2 ด้วย ESA WorldCover (global product) แต่ระหว่างทำ Phase 2 พบว่า
มีไฟล์ข้อมูลการใช้ที่ดินทางการ (ปี พ.ศ. 2566) อยู่แล้วใน D:\\WMB_NEW (ผู้ใช้ชี้ให้) ทดสอบ clip กับ
ขอบเขตตำบลแม่นาเรือแล้วได้พื้นที่ 61,149 ไร่ ตรงกับพื้นที่ทางการ 61,188 ไร่ (คลาดเคลื่อน 0.06%) —
แม่นยำกว่าและละเอียดกว่า WorldCover มาก (แยกชนิดพืชจริง เช่น นาข้าว/ข้าวโพด/ลำไย/ยางพารา ไม่ใช่แค่
"cropland" รวมๆ) จึงใช้ไฟล์นี้แทนสำหรับแม่นาเรือ — ดูที่มา/ขั้นตอนสกัดข้อมูลเต็มใน
04_scripts/extract_landuse_maenaruea.py

**2026-08-23 — เพิ่ม fallback ESA WorldCover ผ่าน GEE สำหรับตำบลอื่นที่ไม่มีไฟล์ทางการ clip ไว้**:
ไฟล์ landuse_maenaruea_2566.geojson ด้านบน clip ไว้เฉพาะเขตตำบลแม่นาเรือเท่านั้น (จ.พะเยา) — ตำบล
อื่น (เช่น นครป่าหมาก จ.พิษณุโลก) จะไม่ทับกับไฟล์นี้เลย ทำให้ total_area == 0.0 คำนวณ runoff_coefficient
ไม่ได้ (คืน None เงียบๆ ไม่มี error — พบปัญหานี้จริงตอนนครป่าหมากไม่มีข้อมูลน้ำท่าแม้รัน pipeline ผ่านแล้ว)
วิธีแก้ที่ต้นตอ (แทนที่จะ clip ไฟล์ทางการใหม่ทุกครั้งที่เพิ่มตำบล ซึ่งต้องมีคนไป clip
merge_landuse_32647@256804.gpkg (5.8GB, ทั้งประเทศ) ด้วยมือทุกรอบ): ถ้าหมู่บ้านไม่ทับกับไฟล์ทางการเลย
ให้ตกไปใช้ ESA WorldCover v200 (10m, ปี 2021, ครอบคลุมทั้งโลก) ผ่าน Earth Engine แทนโดยอัตโนมัติ —
ความละเอียดชนิดพืชต่ำกว่า (11 กลุ่มกว้างๆ ไม่แยกนาข้าว/ข้าวโพด/ลำไยแบบ LDD) แต่ไม่ต้องเตรียมไฟล์อะไร
ล่วงหน้าเลย ใช้ได้ทันทีกับตำบลใหม่ที่จะเพิ่มเข้าระบบทีหลัง — ดู `source` ในผลลัพธ์เพื่อรู้ว่าหมู่บ้านไหนใช้
แหล่งข้อมูลไหน (LDD_landuse_2566 = ทางการ แม่นยำกว่า / ESA_WorldCover_v200 = fallback)

ผลคือโมดูลนี้**เรียก Earth Engine เฉพาะตอน fallback เท่านั้น** (แม่นาเรือไม่โดนเรียกเลย เพราะไฟล์ทางการ
ครอบคลุมอยู่แล้ว) — ต่างจากไฟล์ rainfall_et0.py/rice_paddy.py ที่พึ่ง GEE เสมอ (CHIRPS/MOD16A2/
Sentinel-1 เป็น time series รายเดือนจริง ไม่มีข้อมูลทางการทดแทนได้)

**ข้อจำกัดที่ต้องรู้**: ข้อมูลนี้เป็นภาพนิ่ง (LDD ปี 2566 / ESA WorldCover ปี 2021) ไม่ใช่ time series
รายเดือน ดังนั้นค่าที่เขียนเข้า zone_landcover_monthly จะ**เหมือนกันทุกเดือน**จนกว่าจะมีข้อมูลปีใหม่กว่านี้
มาแทน — ตาราง _monthly เก็บค่านี้ทุกเดือนเพราะ pipeline รันทุกเดือนอยู่แล้ว (ต้นทุนต่ำ) ไม่ใช่เพราะที่ดิน
เปลี่ยนรายเดือนจริง — ผลลัพธ์ของ fallback ถูก cache ไว้ในหน่วยความจำต่อ village_id ระหว่างรันครั้งเดียว
(เช่น ตอน backfill หลายเดือนติดกัน) กันเรียก GEE ซ้ำโดยไม่จำเป็นเพราะรู้อยู่แล้วว่าค่าจะเหมือนเดิมทุกเดือน

--- ที่มาของค่าสัมประสิทธิ์น้ำท่า (runoff coefficient C) ---
ใช้ค่ามาตรฐานจากวิธี Rational Method (C-value) ที่ใช้กันทั่วไปในงานวิศวกรรมระบายน้ำ (เช่น ASCE
Manual of Practice No. 37 และตำรา hydrology ทั่วไป) ถ่วงน้ำหนักตาม 5 หมวดหลัก (LUL1_CODE) ของ
ข้อมูลการใช้ที่ดิน — **ไม่ได้ calibrate กับพื้นที่ลุ่มน้ำแม่นาเรือจริง** ถ้าต้องการความแม่นยำสูงกว่านี้
ควรเทียบกับวิธี DEM-based (D8/DTM) ที่ WMB_NEW กำลังทำอยู่ (00-system-design-reset.md ข้อ 15.2)
ใช้ mapping เดียวกันนี้กับทั้งสองแหล่งข้อมูล (LDD และ ESA WorldCover) เพื่อให้ค่า C เทียบกันข้ามตำบลได้
"""
import functools
from pathlib import Path

import ee
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

# แม็ปคลาสของ ESA WorldCover v200 (11 กลุ่ม, รหัสมาตรฐานของ product) เข้าหมวด LUL1_CODE เดียวกับ
# ข้อมูลทางการ — อ้างอิงคำอธิบายคลาสจาก ESA WorldCover User Manual v2.0.0
ESA_WORLDCOVER_TO_LUL1 = {
    10: "F",  # Tree cover
    20: "M",  # Shrubland
    30: "M",  # Grassland
    40: "A",  # Cropland
    50: "U",  # Built-up
    60: "M",  # Bare / sparse vegetation
    70: "M",  # Snow and ice (ไม่น่าเจอในพื้นที่ไทย แต่ใส่ครบไว้กันพลาด)
    80: "W",  # Permanent water bodies
    90: "W",  # Herbaceous wetland
    95: "F",  # Mangroves (ลักษณะเป็นป่าไม้ยืนต้น)
    100: "M",  # Moss and lichen
}

# cache ผลลัพธ์ ESA WorldCover ต่อหมู่บ้าน (keyed ด้วย village_id) — กัน reduceRegion ซ้ำโดยไม่จำเป็น
# ตอนรันหลายเดือนติดกัน (backfill) เพราะรู้อยู่แล้วว่าที่ดินเป็นภาพนิ่ง ค่าจะเหมือนเดิมทุกเดือน
_esa_fallback_cache: dict[str, dict | None] = {}


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


def _weighted_breakdown(area_by_lul1: dict[str, float], total_area: float, source: str) -> dict:
    """คำนวณ %, ค่าถ่วงน้ำหนัก C จาก area_by_lul1/total_area — ใช้ร่วมกันทั้งสองแหล่งข้อมูล (LDD/ESA)"""
    pct_by_lul1 = {code: (a / total_area) * 100.0 for code, a in area_by_lul1.items()}
    weighted_c = sum(
        (pct_by_lul1.get(code, 0.0) / 100.0) * c for code, c in RUNOFF_C_BY_LUL1.items()
    )
    return {
        "forest_pct": round(pct_by_lul1.get("F", 0.0), 1),
        "agri_pct": round(pct_by_lul1.get("A", 0.0), 1),
        "residential_pct": round(pct_by_lul1.get("U", 0.0), 1),
        "runoff_coefficient": round(weighted_c, 3),
        "source": source,
    }


def _compute_via_esa_worldcover(village_geom_geojson: dict) -> dict | None:
    """Fallback สำหรับหมู่บ้านที่ไม่ทับกับไฟล์ข้อมูลการใช้ที่ดินทางการเลย (ตำบลอื่นนอกจากแม่นาเรือ) —
    ใช้ ESA WorldCover v200 ผ่าน Earth Engine แทน ดูเหตุผล/ข้อจำกัดในคอมเมนต์หัวไฟล์ 2026-08-23

    คืน None ถ้า reduceRegion ไม่ได้ผลลัพธ์เลย (เช่น หมู่บ้านอยู่นอกขอบเขตที่ ESA WorldCover ครอบคลุม —
    ไม่ควรเกิดในทางปฏิบัติเพราะ ESA WorldCover ครอบคลุมทั้งโลก)"""
    geom = ee.Geometry(village_geom_geojson)
    image = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    histogram = image.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geom,
        scale=10,
        maxPixels=1e9,
    ).get("Map")
    histogram = ee.Dictionary(histogram).getInfo()
    if not histogram:
        return None

    area_by_lul1: dict[str, float] = {}
    total_area = 0.0
    for class_code_str, pixel_count in histogram.items():
        lul1_code = ESA_WORLDCOVER_TO_LUL1.get(int(class_code_str))
        if lul1_code is None:
            continue
        area_by_lul1[lul1_code] = area_by_lul1.get(lul1_code, 0.0) + pixel_count
        total_area += pixel_count

    if total_area == 0.0:
        return None

    return _weighted_breakdown(area_by_lul1, total_area, source="ESA_WorldCover_v200")


def compute_landcover_breakdown(village_geom_geojson: dict, cache_key: str | None = None) -> dict | None:
    """
    village_geom_geojson: GeoJSON geometry dict ของขอบเขตหมู่บ้าน (WGS84, จาก
    ST_AsGeoJSON(ST_Union(village_boundary_parts.geom)) — ดู pipeline/db.py::fetch_villages)
    cache_key: ปกติส่ง village_id เข้ามา — ใช้ cache ผล ESA WorldCover fallback ข้ามเดือนตอน backfill
    (ไม่บังคับ — ถ้าไม่ส่งจะไม่ cache แค่คำนวณสดทุกครั้ง)

    คืน dict: {"forest_pct", "agri_pct", "residential_pct", "runoff_coefficient", "source"} หรือ None
    ถ้าหมู่บ้านไม่มี geometry หรือ ESA WorldCover fallback ก็ยังหาข้อมูลไม่ได้ (ไม่ควรเกิดในทางปฏิบัติ)
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

    if total_area > 0.0:
        return _weighted_breakdown(area_by_lul1, total_area, source="LDD_landuse_2566")

    # ไม่ทับกับไฟล์ทางการเลย (ตำบลนอกแม่นาเรือ) — ตกไปใช้ ESA WorldCover ผ่าน GEE แทนโดยอัตโนมัติ
    if cache_key is not None and cache_key in _esa_fallback_cache:
        return _esa_fallback_cache[cache_key]
    result = _compute_via_esa_worldcover(village_geom_geojson)
    if cache_key is not None:
        _esa_fallback_cache[cache_key] = result
    return result
