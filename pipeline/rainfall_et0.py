"""
rainfall_et0.py — ฝน (CHIRPS) และ ET0 (MOD16A2) รายเดือน ระดับ "ตำบล" ทั้งก้อน

ต่อยอดจาก 03_legacy_prototype/gee_pipeline.py (compute_monthly_rainfall/compute_monthly_et0)
แต่เปลี่ยนหน่วยจาก "ต่อหมู่บ้าน (zone)" เป็น "ต่อตำบลทั้งก้อน" ให้ตรงกับ schema จริงที่ออกแบบไว้
(ตาราง rainfall_monthly/et0_monthly มี PK (tambon_id, month) ไม่ใช่ (village_id, month)) —
สมเหตุสมผลเพราะ CHIRPS (~5.5 กม./pixel) และ MOD16A2 (500 ม./pixel) หยาบกว่าขนาดหมู่บ้านมาก
การแยกรายหมู่บ้านจะได้ค่าซ้ำๆ กันเกือบทั้งหมดอยู่ดี ไม่คุ้มความซับซ้อน

หมายเหตุความซื่อตรงของข้อมูล (คัดลอกจากไฟล์ต้นฉบับ เพราะยังจริงอยู่):
1. MOD16A2 (v6.1) มีข้อมูลตั้งแต่ปี 2021 เท่านั้น ถ้าต้องคำนวณย้อนหลังก่อนปี 2021
   ต้องเปลี่ยนเป็น MOD16A2GF (gap-filled) แทน
2. ฝนใช้ CHIRPS v3 (ย้ายจาก v2 เมื่อ 2569-10 เพราะ v2 ยุติการผลิตหลังธันวาคม 2569 และ asset v2 ใน
   Earth Engine ออกข้อมูล final ช้ามาก — ทำให้ backfill เดือนกันยายน 2569 ล้มตอนกลางเดือนตุลาคม)
   - ค่าเริ่มต้น = UCSB-CHC/CHIRPS/V3/DAILY_SAT (ฐาน IMERG-Late, ออกข้อมูลเร็ว ~2 วันหลังจบแต่ละ pentad)
   - ทางเลือก = UCSB-CHC/CHIRPS/V3/DAILY_RNL (ฐาน ERA5, final ช้ากว่าแต่ต่อเนื่องยาวกว่า)
     สลับได้ด้วย env CHIRPS_COLLECTION โดยไม่ต้องแก้โค้ด
   - v3 ใช้สถานีวัดฝนมากกว่าและแก้ undercatch → ค่ารายเดือนไม่เท่า v2 ที่เคยบันทึกไว้ ถ้าจะเทียบ
     ข้ามเดือนต้อง backfill ย้อนหลังด้วย v3 ให้ครบ (แถวใน rainfall_monthly มี source บอกเวอร์ชัน)
   - ข้อมูลของ DAILY_SAT เป็น "ชั่วคราว" (preliminary) ได้ถูกปรับค่าภายหลังเมื่อ final ออก
     ถ้าต้องการค่าที่นิ่งแล้วให้รันซ้ำเดือนนั้นภายหลัง (upsert ทับได้)
"""
import calendar
import os

import ee

CHIRPS_COLLECTION = os.environ.get("CHIRPS_COLLECTION", "UCSB-CHC/CHIRPS/V3/DAILY_SAT")
CHIRPS_BAND = "precipitation"
# ค่านี้ถูกเขียนลง rainfall_monthly.source (ดู db.upsert_rainfall_monthly) — ไม่มี CHECK constraint
CHIRPS_SOURCE_TAG = "CHIRPS-v3"

MOD16_COLLECTION = "MODIS/061/MOD16A2"
MOD16_ET_BAND = "ET"
MOD16_QC_BAND = "ET_QC"
MOD16_ET_SCALE = 0.1


def compute_monthly_rainfall(tambon_geom: ee.Geometry, year: int, month: int) -> float | None:
    """รวมฝนทั้งเดือน (มม.) เฉลี่ยทั้งพื้นที่ตำบล จาก CHIRPS v3 Daily

    ถ้าข้อมูลของเดือนนั้นยังออกไม่ครบทุกวัน จะ raise RuntimeError พร้อมบอกวันล่าสุดที่มีใน asset
    (แทนที่จะรวมฝนไม่ครบเดือนแล้วบันทึกเป็นค่าจริงเงียบๆ หรือพังด้วย EEException ที่อ่านไม่รู้เรื่อง
    แบบที่เกิดกับ v2 เมื่อ collection ว่าง)"""
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")

    collection = ee.ImageCollection(CHIRPS_COLLECTION).filterDate(start, end).select(CHIRPS_BAND)

    expected_days = calendar.monthrange(year, month)[1]
    available_days = collection.size().getInfo()
    if available_days < expected_days:
        latest_ms = (
            ee.ImageCollection(CHIRPS_COLLECTION).aggregate_max("system:time_start").getInfo()
        )
        latest = (
            ee.Date(latest_ms).format("YYYY-MM-dd").getInfo() if latest_ms is not None else "ไม่พบข้อมูลเลย"
        )
        raise RuntimeError(
            f"ข้อมูลฝน {CHIRPS_COLLECTION} ของ {year}-{month:02d} ยังไม่ครบ: มี {available_days}/{expected_days} วัน "
            f"(วันล่าสุดใน asset = {latest}) — รอให้ข้อมูลออกครบแล้วรันซ้ำเดือนนี้"
        )

    monthly_sum_image = collection.sum()
    stats = monthly_sum_image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=tambon_geom, scale=5566, maxPixels=1e9,
    )
    value = stats.get(CHIRPS_BAND).getInfo()
    return round(value, 1) if value is not None else None


def compute_monthly_et0(tambon_geom: ee.Geometry, year: int, month: int) -> float | None:
    """รวม ET รายเดือน (มม.) เฉลี่ยทั้งพื้นที่ตำบล จาก MOD16A2 — มาส์กพิกเซลคุณภาพต่ำออกด้วย
    ET_QC bit 0 (0=คุณภาพดี, 1=คุณภาพรอง/ฟิล -> ตัดออก)"""
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")

    collection = ee.ImageCollection(MOD16_COLLECTION).filterDate(start, end)

    def mask_and_scale(img):
        qc = img.select(MOD16_QC_BAND)
        good_quality = qc.bitwiseAnd(1).eq(0)
        et_scaled = img.select(MOD16_ET_BAND).multiply(MOD16_ET_SCALE)
        return et_scaled.updateMask(good_quality)

    monthly_sum_image = collection.map(mask_and_scale).sum()
    stats = monthly_sum_image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=tambon_geom, scale=500, maxPixels=1e9,
    )
    value = stats.get(MOD16_ET_BAND).getInfo()
    return round(value, 1) if value is not None else None
