"""
rice_paddy.py — ประมาณพื้นที่นาข้าว (มีน้ำขังจากเตรียมแปลง/ปักดำ) รายเดือน ต่อหมู่บ้าน จาก
Sentinel-1 SAR

ต่อยอดจาก 03_legacy_prototype/gee_pipeline.py (detect_agricultural_area_rai) แต่ตัดส่วน
"ผูกป้ายชนิดพืชจาก village_crop_report" ออก เพราะ schema จริงของเราไม่ได้ออกแบบให้ rice_paddy_monthly
ผูกกับ crop_report — ตาราง rice_paddy_monthly เป็นข้อมูล remote-sensing ล้วนๆ (paddy_area_rai
เฉยๆ ไม่มีชนิดพืช) ใช้เป็น "sanity check" เทียบกับสิ่งที่หมู่บ้านรายงานเอง ไม่ใช่ตัวตัดสินแทนคน
(หลักการเดียวกับที่ไฟล์เดิมอธิบายไว้ในหมายเหตุข้อ 2)

หมายเหตุความซื่อตรงของข้อมูล (คัดลอกจากไฟล์ต้นฉบับ เพราะยังจริงอยู่):
- วิธีนี้ตรวจจับ "สัญญาณน้ำขัง" ไม่ใช่การจำแนกชนิดพืช — ตรวจจับได้ดีเฉพาะนาข้าว (มีน้ำขังชัดเจน
  ช่วงเตรียมแปลง/ปักดำ) พืชไร่ (ข้าวโพด/มันสำปะหลัง/อ้อย) จะไม่ถูกตรวจพบด้วยวิธีนี้
- threshold -18 dB เป็นค่าทั่วไปที่ใช้กันในงาน rice mapping จาก SAR แต่ "ควรปรับตามพื้นที่จริง"
  โดยเทียบกับพื้นที่ที่หมู่บ้านรายงานว่าปลูกข้าวในรอบนั้นก่อนนำไปใช้งานตัดสินใจจริง
"""
import ee

SENTINEL1_COLLECTION = "COPERNICUS/S1_GRD"
SQM_PER_RAI = 1600.0
FLOODED_THRESHOLD_DB = -18


def compute_rice_paddy_area_rai(village_geom: ee.Geometry, year: int, month: int) -> float | None:
    """คืนพื้นที่ที่มีสัญญาณน้ำขัง (ไร่) ภายในขอบเขตหมู่บ้าน หรือ None ถ้าไม่มีภาพ Sentinel-1
    ผ่านพื้นที่นี้ในเดือนนั้น (เกิดได้บ้าง ไม่ใช่ error)"""
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")

    collection = (
        ee.ImageCollection(SENTINEL1_COLLECTION)
        .filterBounds(village_geom)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select("VH")
    )

    count = collection.size().getInfo()
    if count == 0:
        return None

    median_vh = collection.median()
    flooded_mask = median_vh.lt(FLOODED_THRESHOLD_DB)

    area_image = flooded_mask.multiply(ee.Image.pixelArea())
    stats = area_image.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=village_geom, scale=10, maxPixels=1e9,
    )
    sqm = stats.get("VH").getInfo()
    if sqm is None:
        return None
    return round(sqm / SQM_PER_RAI, 1)
