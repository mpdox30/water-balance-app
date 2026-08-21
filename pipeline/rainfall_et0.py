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
2. CHIRPS v2 จะยุติการผลิตข้อมูลหลังธันวาคม 2569 — ผู้ผลิตแนะนำย้ายไป CHIRPS v3
   (UCSB-CHC/CHIRPS/V3/DAILY_SAT) ในอนาคต — ชื่อ asset แยกเป็นตัวแปรเดียวเพื่อสลับง่าย
"""
import ee

CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_BAND = "precipitation"

MOD16_COLLECTION = "MODIS/061/MOD16A2"
MOD16_ET_BAND = "ET"
MOD16_QC_BAND = "ET_QC"
MOD16_ET_SCALE = 0.1


def compute_monthly_rainfall(tambon_geom: ee.Geometry, year: int, month: int) -> float | None:
    """รวมฝนทั้งเดือน (มม.) เฉลี่ยทั้งพื้นที่ตำบล จาก CHIRPS Daily"""
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")

    monthly_sum_image = (
        ee.ImageCollection(CHIRPS_COLLECTION)
        .filterDate(start, end)
        .select(CHIRPS_BAND)
        .sum()
    )
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
