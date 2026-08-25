"""
catchment.py — คำนวณพื้นที่ลุ่มน้ำสะสม (catchment area, ตร.กม.) เหนือจุดที่ตั้งของแหล่งเก็บน้ำแต่ละแห่ง
(water_storage_sources.lat/lon) ผ่าน Google Earth Engine — ใช้เป็นตัวถ่วงน้ำหนักแบ่งสัดส่วนน้ำท่า
(runoff_estimate_monthly ซึ่งคำนวณระดับหมู่บ้านอยู่แล้วใน balance_engine.py::compute_runoff_estimate)
ให้แต่ละแหล่งน้ำที่อยู่ในหมู่บ้าน/ตำบลเดียวกัน — ใช้โดย pipeline/storage_depletion.py
ดูที่มาการตัดสินใจเลือกวิธีนี้เต็มใน runoff-depletion-model-design.html §04

--- วิธีคำนวณ: MERIT-Hydro upa band (ไม่ใช่ iterative flow-direction trace ตามที่ร่างไว้ในเอกสารตอนแรก) ---
ตอนคุยกับผู้ใช้ ออกแบบไว้ว่าจะ trace ทวนน้ำจากจุด pour point ทีละพิกเซลตาม flow direction (dir band)
สะสมพื้นที่พิกเซลที่ไหลเข้ามาเอง (คล้าย D8 algorithm ที่ทำเองฝั่ง client) — แต่พบว่า MERIT-Hydro
(MERIT/Hydro/v1_0_1 ใน GEE) มี band "upa" (upstream drainage area หน่วยตร.กม.) คำนวณสะสมไว้ให้ล่วงหน้า
อยู่แล้วทุกพิกเซล (ความละเอียด ~90m / 3 arc-second) จึงอ่านค่าที่พิกเซลนั้นได้ตรงๆ โดยไม่ต้อง trace เอง —
ง่ายกว่า เร็วกว่ามาก (ไม่ต้อง iterative loop ฝั่ง client เรียก getInfo() ซ้ำหลายรอบ) และผลลัพธ์เทียบเท่ากัน
เพราะ upa ก็คือผลของการ trace แบบเดียวกันที่ทำไว้ล่วงหน้าแล้วตอนสร้าง dataset — เอกสาร design doc จะ
อัปเดตให้ตรงกับโค้ดจริงนี้ (เปลี่ยนแผนระหว่างลงมือทำ ไม่ใช่สิ่งที่ยืนยันกับผู้ใช้ไว้ก่อนหน้า)

--- ปัญหา pour point ไม่ตรงลำน้ำเป๊ะ + วิธีแก้ (snap to max upstream area) ---
พิกัด lat/lon ของแหล่งน้ำใน water_storage_sources มาจากการปักหมุดตำแหน่งจริง/GPS ภาคสนาม ไม่ได้ align
กับกริดพิกเซล 90m ของ MERIT-Hydro เป๊ะๆ ถ้าอ่านค่า upa ตรงพิกัดที่ปักไว้เลย อาจตกไปอยู่พิกเซลข้างลำน้ำ
(ไม่ใช่พิกเซลลำน้ำจริง) ซึ่งจะได้ค่า upa เตี้ยกว่าความจริงมาก (เพราะ upa เพิ่มขึ้นตามลำน้ำเรื่อยๆ พิกเซลข้าง
ลำน้ำที่ไม่ใช่ตัวลำน้ำเองจะมีค่าต่ำกว่าเป็นสิบ/ร้อยเท่า) — วิธีแก้มาตรฐานที่ใช้กันทั่วไปในงาน pour-point
correction คือ "snap to max": หาพิกเซลที่มีค่า upa สูงสุดในรัศมีค้นหารอบจุดที่ปักไว้ (สมมติว่าลำน้ำจริงต้อง
อยู่ใกล้ๆ จุดที่ปักหมุด และพิกเซลบนลำน้ำจะมี upa สูงกว่าพิกเซลข้างเคียงเสมอ) ใช้รัศมีค้นหา 500 ม. เป็นค่า
เริ่มต้น (มากกว่าความคลาดเคลื่อน GPS ทั่วไปพอสมควร แต่ไม่กว้างจนหลุดไปโดนลำน้ำสายอื่น)

--- ข้อจำกัดที่ต้องรู้ (ไม่ได้ปิดบัง แจ้งไว้ตรงนี้ให้เห็นชัด) ---
1. ความละเอียด MERIT-Hydro ~90m — สำหรับแหล่งน้ำขนาดเล็กมาก (สระ/ฝายลำห้วยเล็ก) พื้นที่ลุ่มน้ำจริงอาจเล็ก
   กว่าความละเอียดพิกเซลเดียว ทำให้ค่าที่ได้หยาบ/ไม่แม่นยำระดับวิศวกรรม — ยอมรับความหยาบนี้เพราะเป้าหมาย
   ของฟีเจอร์นี้คือได้ "สัดส่วน" เปรียบเทียบระหว่างแหล่งน้ำในหมู่บ้าน/ตำบลเดียวกัน ไม่ใช่ค่าพื้นที่ลุ่มน้ำที่
   แม่นยำระดับงานชลศาสตร์
2. แหล่งน้ำที่เป็นอ่างเก็บน้ำขนาดใหญ่ (ผิวน้ำกว้างหลายพิกเซล) — จุด lat/lon ที่ปักอาจอยู่กลางอ่าง ไม่ใช่ที่
   จุดออกน้ำ (outlet) จริง ค่า upa ที่อ่านได้จึงอาจเป็นค่า ณ จุดกลางอ่าง ไม่ใช่ค่าสะสมทั้งหมดที่ไหลเข้าอ่าง —
   ยังไม่ได้แก้ปัญหานี้โดยเฉพาะ (ต้องหาตำแหน่ง outlet จริงแยกต่างหากถ้าต้องการความแม่นยำสูงกว่านี้ในอนาคต)
3. คำนวณครั้งเดียวต่อแหล่งน้ำ (ภูมิประเทศไม่เปลี่ยนรายเดือน) — ผู้เรียก (pipeline/run_monthly.py) เช็ค
   water_storage_sources.catchment_area_computed_at ก่อนเรียกฟังก์ชันนี้ ไม่เรียก GEE ซ้ำทุกครั้งที่รัน
   pipeline (ตาม step "run once ไม่ใช่ run ทุกครั้ง" ใน design doc §04)
"""
import ee

MERIT_HYDRO_ASSET = "MERIT/Hydro/v1_0_1"
DEFAULT_SEARCH_RADIUS_M = 500


def compute_source_catchment_area_km2(
    lat: float, lon: float, search_radius_m: float = DEFAULT_SEARCH_RADIUS_M
) -> float | None:
    """คืนพื้นที่ลุ่มน้ำสะสม (ตร.กม.) ณ พิกเซลที่มีค่า upa (upstream drainage area) สูงสุดในรัศมี
    search_radius_m รอบจุด (lat, lon) — ดูเหตุผลวิธี "snap to max" ในคอมเมนต์หัวไฟล์

    คืน None ถ้า reduceRegion ไม่ได้ผลลัพธ์เลย (เช่น พิกัดอยู่นอกขอบเขตที่ MERIT-Hydro ครอบคลุม — ไม่ควร
    เกิดในทางปฏิบัติเพราะ dataset นี้ครอบคลุมเกือบทั้งโลกยกเว้นบริเวณขั้วโลก)"""
    point = ee.Geometry.Point([lon, lat])
    search_area = point.buffer(search_radius_m)

    upa = ee.Image(MERIT_HYDRO_ASSET).select("upa")
    result = upa.reduceRegion(
        reducer=ee.Reducer.max(),
        geometry=search_area,
        scale=90,
        maxPixels=1e9,
    ).get("upa")
    value = result.getInfo()
    if value is None:
        return None
    return round(float(value), 4)


def compute_missing_catchment_areas(conn, db) -> int:
    """วนคำนวณ catchment_area_km2 ให้ทุกแหล่งน้ำที่ยังไม่เคยคำนวณ (catchment_area_computed_at IS NULL)
    และมีพิกัด lat/lon — เรียกจาก pipeline/run_monthly.py (สคริปต์ฝั่ง GEE) หลัง gee_init.init_earth_engine()
    แล้วเท่านั้น รับ db module เข้ามาเป็นพารามิเตอร์แทนการ import ตรงๆ กัน circular import (db.py ไม่ควรรู้จัก
    โมดูลนี้) คืนจำนวนแหล่งน้ำที่คำนวณสำเร็จ (ไว้ print สรุป)"""
    sources = db.fetch_sources_missing_catchment_area(conn)
    n_done = 0
    for src in sources:
        area_km2 = compute_source_catchment_area_km2(src["lat"], src["lon"])
        if area_km2 is None:
            print(f"    [ข้าม] {src['name_th']}: MERIT-Hydro ไม่คืนค่า upa ที่พิกัดนี้เลย")
            continue
        db.upsert_source_catchment_area(conn, src["source_id"], area_km2)
        n_done += 1
        print(f"    {src['name_th']}: catchment_area_km2={area_km2}")
    if n_done:
        conn.commit()
    return n_done
