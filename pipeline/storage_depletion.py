"""
storage_depletion.py — Phase 6: จำลองสต๊อกน้ำ (storage) รายแหล่งน้ำ/รายเดือน แยกจากสมดุลน้ำหลัก
(water_balance_monthly) โดยเด็ดขาด — เขียนผลเข้า storage_depletion_monthly เท่านั้น เรียกจาก
balance_engine.py::run_for_tambon() ต่อจาก compute_runoff_estimate() เสมอ (ต้องมี runoff_estimate_monthly
และ water_balance_monthly ของเดือนนี้เขียนเสร็จแล้วก่อนเรียกฟังก์ชันนี้)

ที่มา: ผู้ใช้มีข้อมูลระดับน้ำจริงของอ่างเก็บน้ำ 4 แห่ง (RES002/004/005/006, ต.แม่นาเรือ) ยาวเกือบปี ใช้สกัด
เรทการเปลี่ยนแปลง %ความจุ รายเดือนเฉลี่ย (regional_seasonal_storage_factor) มาใช้เป็น fallback default
สำหรับตำบลอื่นที่ไม่มีข้อมูลระดับน้ำของตัวเอง — ดูรายละเอียดเต็มใน runoff-depletion-model-design.html §00-§08

=============================================================================
โมเดล 2 เส้นทาง (model_path) — เลือกตามประเภทแหล่งน้ำ + ที่ตั้ง
=============================================================================
A) "physical" — สระ/ฝาย/small_water_source ทุกจังหวัด + อ่างเก็บน้ำนอกภาคเหนือ
   Storage(t) = clip(Storage(t-1) + Inflow - Outflow - Loss, 0, Capacity)
   Inflow  = ส่วนแบ่งน้ำท่าจาก runoff_estimate_monthly ของหมู่บ้าน (หรือทั้งตำบลถ้าเป็นแหล่งระดับตำบล)
             ถ่วงน้ำหนักตามสัดส่วน catchment_area_km2 เทียบกับแหล่งน้ำอื่นในกลุ่มเดียวกัน คูณ
             capture_efficiency ตามประเภทแหล่งน้ำ (ดู CAPTURE_EFFICIENCY_BY_SOURCE_TYPE)
   Outflow = ส่วนแบ่งความต้องการใช้น้ำรวมของหมู่บ้าน (water_balance_monthly) — ถ้าแหล่งนี้มีแถวใน
             reservoir_village_usage (ตารางที่มีอยู่แล้ว เก็บการใช้จริงต่อคู่แหล่งน้ำ×หมู่บ้าน รองรับแหล่งที่
             ใช้ร่วมกันหลายหมู่บ้านได้) ใช้ households/irrigated_area_rai จริงถ่วงน้ำหนัก ถ้าไม่มีแถวเลย fallback
             ไปถ่วงน้ำหนักตามสัดส่วน stored_capacity_m3 เทียบกับแหล่งน้ำอื่นในหมู่บ้านเดียวกัน (ดูคอมเมนต์
             apportion ด้านล่าง)
   Loss    = 0 เสมอในเวอร์ชันนี้ (ยังไม่มีโมเดลระเหย/ซึม — ข้อจำกัดที่รู้อยู่แล้ว ดูข้อ 2 ท้ายไฟล์)

B) "regional_seasonal_factor" — อ่างเก็บน้ำในภาคเหนือ (บน+ล่าง) เท่านั้น (ยืนยันกับผู้ใช้ 2569-08-25)
   Storage(t) = clip(Storage(t-1) * (1 + avg_pct_full_change/100), 0, Capacity)
   ไม่แยก Inflow/Outflow จริง — บันทึกผลต่างสุทธิลงคอลัมน์ inflow_m3 (ถ้าเพิ่ม) หรือ outflow_m3 (ถ้าลด)
   เพื่อให้ schema เดียวกันใช้ query รวมกับ path A ได้
   unmet_demand_m3 = NULL เสมอ — ยังไม่มีกลไกแบ่งสัดส่วนความต้องการใช้น้ำต่อหมวดสำหรับอ่างที่ใช้ร่วมกันทั้ง
   ตำบล (ดู open question เดิมใน design doc §07 การ์ด 3)

=============================================================================
สมมติฐานเรื่องการแบ่งสัดส่วน inflow/outflow — ยืนยันจากผู้ใช้แล้ว (2569-08-25): "ยืนยันใช้ตามที่ออกแบบ"
(เดิมทำไปตามคำสั่ง "ลงมือทำทั้งหมดได้เลย" โดยยังไม่ fabricate ค่าลอยๆ — เลือกวิธีที่อนุรักษ์นิยม/สมเหตุสมผล
ที่สุดแล้วเสนอให้ตรวจทาน ตอนนี้ตรวจทานผ่านแล้ว บันทึกไว้เป็นสูตรที่ใช้จริง ไม่ใช่สมมติฐานที่รอตรวจสอบอีกต่อไป)
=============================================================================
1. แบ่งสัดส่วน "น้ำท่าเข้า" (inflow) ให้แหล่งน้ำที่อยู่กลุ่มเดียวกัน (หมู่บ้านเดียวกัน หรือทั้งตำบลถ้าเป็น
   แหล่งระดับตำบล) ตามสัดส่วน catchment_area_km2 — ถ้าแหล่งไหนในกลุ่มไม่มี catchment_area_km2 เลย (ยังไม่
   ได้รัน pipeline/catchment.py หรือ MERIT-Hydro หาค่าไม่ได้) ทั้งกลุ่มจะ fallback ไปแบ่งเท่าๆ กันแทน (equal
   split) — ไม่ผสมสองวิธีในกลุ่มเดียวกัน (กันความไม่สมเหตุสมผลที่แหล่งไม่มีข้อมูลได้ 0 ทั้งที่จริงอาจมีพื้นที่
   ลุ่มน้ำมาก)
2. แบ่งสัดส่วน "น้ำที่ถูกดึงไปใช้" (outflow) — ใช้ตาราง reservoir_village_usage (มีอยู่แล้วในฐานข้อมูลจริง —
   13 แถว เก็บ households/irrigated_area_rai ต่อคู่แหล่งน้ำ×หมู่บ้านของอ่างเก็บน้ำ 5 แห่ง) เป็นน้ำหนักหลักก่อน
   เสมอ — households/irrigated_area_rai คนละหน่วยกัน (ครัวเรือน vs ไร่) เอามารวมกันตรงๆ เป็น "น้ำหนักสัมพัทธ์"
   คร่าวๆ ไม่ใช่ค่าจริงเชิงฟิสิกส์ (ยอมรับความหยาบนี้ — ยืนยันแล้ว) เฉพาะแหล่งที่ไม่มีแถวใน reservoir_village_usage
   เลย จึง fallback ไปถ่วงน้ำหนักตามสัดส่วน stored_capacity_m3 ในหมู่บ้านเดียวกันแทน (สมมติฐานเดิม เป็น
   สมมติฐานเดียวกับที่ balance_engine.py ใช้อยู่แล้วตอนรวม pond_stock)
3. แหล่งน้ำระดับตำบล (village_id IS NULL) ที่ไม่มีแถวใน reservoir_village_usage เลย (ไม่ว่าประเภทไหน) — ไม่มี
   ข้อมูล mapping ว่าหมู่บ้านไหนใช้น้ำจากแหล่งนี้บ้าง (ตรงกับข้อจำกัดเดียวกับที่ balance_engine.py หัวไฟล์แจ้งไว้
   เรื่องอ่างเก็บน้ำระดับตำบล) จึงคำนวณได้แค่ inflow (จากผลรวมน้ำท่าทั้งตำบล) แต่ outflow_m3/unmet_demand_m3 =
   NULL เสมอ (ไม่ fabricate) — แหล่งที่มีแถวใน reservoir_village_usage ไม่ติดข้อจำกัดนี้แล้ว (ดูข้อ 2 ด้านบน)
   *** inflow ของแหล่งระดับตำบลใช้ "ผลรวมน้ำท่าทั้งตำบล" ซ้ำกับที่แหล่งระดับหมู่บ้านแต่ละแห่งก็ใช้
   น้ำท่าของหมู่บ้านตัวเองไปแล้ว — เป็นการนับซ้ำบางส่วนโดยเจตนา (ยอมรับความหยาบนี้ เพราะไม่มีข้อมูลแบ่งพื้นที่
   ลุ่มน้ำจริงว่าส่วนไหนไหลเข้าแหล่งระดับตำบลแทนที่จะไหลเข้าแหล่งหมู่บ้าน) ***

=============================================================================
ข้อจำกัดที่รู้อยู่แล้ว
=============================================================================
1. capture_efficiency เป็นค่าคงที่ต่อประเภทแหล่งน้ำ (ไม่ผันตามฤดูกาล/สภาพจริงของแต่ละแหล่ง) — ยืนยันกับ
   ผู้ใช้แล้ว: อ่างเก็บน้ำ > 50% (ใช้ 55%), สระ ≤ 15% (ใช้ 15%), ฝาย = 2% (2569-08-25),
   small_water_source = 5% (2569-08-25)
2. ไม่มีโมเดลการระเหย/ซึมหาย (loss_m3 = 0 เสมอในเส้นทาง physical) — สำหรับ path B (regional_seasonal_factor)
   ผลของการระเหย/ซึมได้ถูกรวมอยู่ใน avg_pct_full_change แล้วโดยอัตโนมัติ (เพราะคำนวณจากระดับน้ำจริงที่วัดได้
   ซึ่งสะท้อนผลสุทธิของทุกปัจจัยอยู่แล้ว) — เฉพาะ path A (physical) เท่านั้นที่ยังขาดโมเดลนี้ไปเลย
3. groundwater_well/mountain_spring/purchased_external: ไม่มีแนวคิด "น้ำท่าไหลเข้า" ที่ใช้ได้ (น้ำบาดาล/
   น้ำพุ/น้ำซื้อจากภายนอก ไม่ได้มาจากน้ำท่าในพื้นที่) จึงไม่มีโมเดลรองรับเลยในฟีเจอร์นี้ ต้องออกแบบแยกต่างหาก
   ถ้าต้องการ
4. stored_capacity_m3 เป็น NULL — ข้ามแหล่งนั้นไปทั้งหมด (ไม่มีทาง bootstrap % หรือคลิป overflow ได้เลย)
5. ฝายทุกแห่งในระบบ (53/53) ไม่มี stored_capacity_m3 เลยสักแห่ง (ตรวจสอบจริงหลังรันครั้งแรก 2569-08-25) —
   ผลคือ storage_depletion_monthly ไม่มีแถวของฝายเลยแม้แต่แถวเดียวในทางปฏิบัติ (0 แถว แม้จะตั้ง
   capture_efficiency=2% ไว้แล้วก็ตาม เพราะติดข้อจำกัดข้อ 4 ด้านบนก่อนถึงจุดที่จะใช้ค่านี้) — ยืนยันจากผู้ใช้
   แล้วว่าถูกต้อง ปล่อยไว้แบบนี้ก่อนโดยตั้งใจ (2569-08-25): ต้องให้ชุมชนช่วยจำแนกประเภทฝายก่อนว่าฝายไหนสร้าง
   เพื่อผันน้ำ (ไม่มีแนวคิด "ความจุเก็บกัก" ที่ใช้ได้จริง) กับฝายไหนที่จริงๆ เก็บน้ำได้ (มีแอ่งเก็บน้ำหลังฝาย) ถึง
   จะกรอก stored_capacity_m3 ที่มีความหมายจริงให้เฉพาะกลุ่มหลังได้ — ไม่ใช่บั๊ก ไม่ต้องแก้โค้ดตรงนี้จนกว่าจะมี
   ข้อมูลจำแนกประเภทนี้เข้ามา
6. small_water_source: capture_efficiency=5% ยืนยันแล้ว (ดูข้อ 1) แต่ 2 แหล่งที่มีอยู่จริงในระบบตอนนี้
   ("อ่างเก็บน้ำห้วยต้นผึ้ง", "อ่างเก็บน้ำห้วยผาจ้อม") ไม่มีทั้ง lat/lon และ stored_capacity_m3 เลยสักช่อง —
   ยังไม่มีแถวใน storage_depletion_monthly จนกว่าจะกรอกข้อมูลทั้งสองอย่างนี้เพิ่ม (คนละสาเหตุกับฝาย — ไม่ใช่
   รอจำแนกประเภท แค่ยังไม่เคยกรอกข้อมูลเท่านั้น)
"""
import datetime

CAPTURE_EFFICIENCY_BY_SOURCE_TYPE = {
    "reservoir": 0.55,          # > 50% ตามที่ผู้ใช้ยืนยัน — ใช้เฉพาะอ่างนอกภาคเหนือ (path A); อ่างในภาคเหนือใช้ path B แทน
    "pond": 0.15,               # ≤ 15%
    "weir": 0.02,               # 2% (แก้จาก ≤10% เดิม ตามที่ผู้ใช้ยืนยันล่าสุด 2569-08-25)
    "small_water_source": 0.05,  # 5% ตามที่ผู้ใช้ยืนยัน 2569-08-25 (เดิมไม่มีค่านี้ ถูกข้ามไปเงียบๆ)
}

NORTHERN_THAILAND_PROVINCES_TH = {
    # ภาคเหนือตอนบน (8 จังหวัด)
    "เชียงใหม่", "เชียงราย", "แม่ฮ่องสอน", "ลำปาง", "ลำพูน", "พะเยา", "แพร่", "น่าน",
    # ภาคเหนือตอนล่าง (9 จังหวัด) — ยืนยันกับผู้ใช้แล้วว่านับรวมด้วย 2569-08-25 (เช่น พิษณุโลก)
    "พิษณุโลก", "สุโขทัย", "เพชรบูรณ์", "พิจิตร", "กำแพงเพชร", "ตาก", "อุตรดิตถ์", "นครสวรรค์", "อุทัยธานี",
}
# รายชื่อ 17 จังหวัดนี้อ้างอิงการแบ่งกลุ่ม "ภาคเหนือ" แบบราชการ/ชลประทาน (บน+ล่าง) ทั่วไป — ยังไม่เคยถูก
# ตรวจสอบทีละจังหวัดกับผู้ใช้ (ยืนยันแค่ 2 จังหวัดที่มีในระบบจริงตอนนี้คือพะเยา/พิษณุโลก) ถ้าเพิ่มตำบลใน
# จังหวัดอื่นเข้าระบบทีหลัง ควรตรวจสอบรายชื่อนี้อีกครั้งก่อนเชื่อผลลัพธ์


def _apportion(weights_by_id: dict, total_amount: float, ids: list) -> dict:
    """แบ่ง total_amount ให้ ids ตามสัดส่วน weights_by_id (float หรือ None) — ถ้า ids ตัวไหนไม่มีน้ำหนัก
    (หรือผลรวมน้ำหนักทั้งกลุ่ม = 0) จะ fallback แบ่งเท่าๆ กันทุกตัวแทนทั้งกลุ่ม (ดูสมมติฐานข้อ 1/2 ในหัวไฟล์)"""
    if not ids:
        return {}
    total_weight = sum(weights_by_id.get(i) or 0.0 for i in ids)
    if total_weight <= 0:
        share = total_amount / len(ids)
        return {i: share for i in ids}
    return {i: total_amount * (weights_by_id.get(i) or 0.0) / total_weight for i in ids}


def _bootstrap_storage_start(source: dict) -> float:
    """สต๊อกเริ่มต้นเดือนแรกที่ยังไม่มีแถวเดือนก่อนหน้าเลย — ใช้ initial_level_pct x stored_capacity_m3 ถ้ามี
    ทั้งคู่ ถ้าไม่ทราบ initial_level_pct ให้สมมติว่าเต็มความจุ (100%) — สอดคล้องกับ convention เดียวกับที่ใช้ใน
    ชุดเตรียมข้อมูลตำบลใหม่.xlsx (sheet 03: "ถ้าไม่ทราบเปอร์เซ็นต์ปัจจุบัน เว้นว่างได้ ระบบจะสมมติว่าเต็มความจุแทน")"""
    capacity = float(source["stored_capacity_m3"])
    pct = source.get("initial_level_pct")
    pct = float(pct) if pct is not None else 100.0
    return capacity * pct / 100.0


def _prev_month_str(year: int, month: int) -> str:
    prev = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    return f"{prev.year}-{prev.month:02d}-01"


def compute_storage_depletion(conn, db, tambon: dict, year: int, month: int, month_date: str) -> int:
    """คำนวณ+เขียนสต๊อกน้ำรายแหล่งของเดือนนี้ ลงตาราง storage_depletion_monthly — ต้องเรียกหลัง
    compute_runoff_estimate() และ db.write_balance_results() ของเดือนนี้เขียนเสร็จแล้วในรันเดียวกันเสมอ
    (ต้องการ runoff_estimate_monthly + water_balance_monthly ของเดือนนี้) รับ db module เข้ามาเป็นพารามิเตอร์
    (แทน import ตรงๆ) ให้เรียกจาก balance_engine.py ได้โดยตรง คืนจำนวนแหล่งน้ำที่เขียนสำเร็จ (ไว้ print สรุป)"""
    tambon_id = tambon["tambon_id"]
    province_th = tambon.get("province_th")
    sources = db.fetch_water_storage_sources(conn, tambon_id)
    if not sources:
        return 0

    source_ids = [s["source_id"] for s in sources]
    prev_month = _prev_month_str(year, month)
    prev_storage = db.fetch_previous_storage_end(conn, source_ids, prev_month)
    regional_factor = db.fetch_regional_seasonal_factor(conn, source_type="reservoir")
    runoff_by_village = db.fetch_runoff_estimate_by_village(conn, tambon_id, month_date)
    tambon_total_runoff = sum(runoff_by_village.values())
    demand_by_village = db.fetch_village_total_demand(conn, tambon_id, month_date)
    usage_rows = db.fetch_reservoir_village_usage(conn, tambon_id)

    # cast เป็น float ตั้งแต่ตอนนี้ (numeric column จาก psycopg คืนเป็น decimal.Decimal — คูณ/หารกับ float
    # ตรงๆ ไม่ได้ ต้อง cast ก่อนเสมอ เหมือน convention ที่ใช้ทั่วทั้ง db.py/balance_engine.py)
    catchment_weights = {
        s["source_id"]: (float(s["catchment_area_km2"]) if s.get("catchment_area_km2") is not None else None)
        for s in sources
    }
    capacity_weights = {
        s["source_id"]: (float(s["stored_capacity_m3"]) if s.get("stored_capacity_m3") is not None else None)
        for s in sources
    }

    # แหล่งไหนใช้ path B (regional_seasonal_factor) บ้าง — ต้องรู้ก่อน group เพราะแหล่งที่ใช้ path B ไม่ควร
    # เข้าไปแย่งส่วนแบ่งน้ำท่า/ความต้องการใช้น้ำ (inflow/outflow apportion pool) กับแหล่งที่ใช้ path A เลย —
    # path B คำนวณ storage เปลี่ยนแปลงจากเรทจริงที่วัดได้ ไม่ได้ใช้ inflow_share/outflow_share ตรงนี้แม้แต่
    # นิดเดียว ถ้าปล่อยให้เข้ากลุ่มด้วยจะทำให้แหล่งอื่นในกลุ่มเดียวกันได้รับส่วนแบ่งน้อยกว่าที่ควรเปล่าๆ (bug ที่
    # พบตอนทดสอบด้วย fixture จำลอง — แก้แล้ว 2569-08-25)
    def _uses_regional_factor(src: dict) -> bool:
        return src["source_type"] == "reservoir" and province_th in NORTHERN_THAILAND_PROVINCES_TH

    path_a_sources = [s for s in sources if not _uses_regional_factor(s)]

    # group แหล่งน้ำ (เฉพาะที่ใช้ path A) ตาม scope ที่ใช้แบ่งสัดส่วนน้ำท่า/ความต้องการใช้น้ำ: หมู่บ้านเดียวกัน
    # หรือทั้งตำบลถ้า village_id IS NULL
    village_groups: dict = {}
    tambon_wide_ids: list = []
    for s in path_a_sources:
        if s["village_id"] is not None:
            village_groups.setdefault(s["village_id"], []).append(s["source_id"])
        else:
            tambon_wide_ids.append(s["source_id"])

    inflow_share_m3: dict = {}
    for vid, ids in village_groups.items():
        runoff_m3 = runoff_by_village.get(vid, 0.0)
        inflow_share_m3.update(_apportion(catchment_weights, runoff_m3, ids))
    if tambon_wide_ids:
        inflow_share_m3.update(_apportion(catchment_weights, tambon_total_runoff, tambon_wide_ids))

    # ส่วนแบ่งความต้องการใช้น้ำ (outflow) — ใช้ reservoir_village_usage จริงก่อนเสมอถ้ามี (ตารางนี้มีอยู่แล้ว
    # ในฐานข้อมูล เก็บคู่ (source_id, village_id) พร้อม households/irrigated_area_rai จริง รองรับแหล่งน้ำที่
    # ใช้ร่วมกันหลายหมู่บ้านได้ รวมถึงแหล่งระดับตำบล village_id IS NULL ด้วย) แหล่งไหนไม่มีแถวในตารางนี้เลย แต่
    # ผูก village_id เดียวไว้ตรงๆ ให้ fallback ไปแบ่งตามสัดส่วน stored_capacity_m3 ในหมู่บ้านเดียวกัน (สมมติฐาน
    # เดิม — ดูข้อ 2 ในหัวไฟล์) แหล่งระดับตำบลที่ไม่มีแถวใน reservoir_village_usage เลย ไม่มีทาง map ได้ ปล่อยให้
    # outflow_m3 = None ต่อไป (ดูข้อ 3 ในหัวไฟล์)
    usage_weight_by_pair: dict = {}
    sources_with_usage_rows: set = set()
    for row in usage_rows:
        key = (row["source_id"], row["village_id"])
        # households/irrigated_area_rai คนละหน่วยกัน (ครัวเรือน vs ไร่) รวมกันตรงๆ ไม่ได้ถูกต้องเชิงฟิสิกส์ —
        # ใช้เป็น "น้ำหนักสัมพัทธ์" คร่าวๆ พอเทียบสัดส่วนระหว่างหมู่บ้าน/แหล่งน้ำในกลุ่มเดียวกันได้ (แนวทางเดียว
        # กับ weighted_c ใน landcover.py ที่ใช้ค่าประมาณเชิงสัดส่วนแทนค่าจริงเชิงฟิสิกส์ทุกจุด)
        w = float(row["households"] or 0) + float(row["irrigated_area_rai"] or 0)
        usage_weight_by_pair[key] = usage_weight_by_pair.get(key, 0.0) + w
        sources_with_usage_rows.add(row["source_id"])

    outflow_pairs: list = []
    outflow_pair_weight: dict = {}
    for s in path_a_sources:
        sid = s["source_id"]
        if sid in sources_with_usage_rows:
            for (usid, vid), w in usage_weight_by_pair.items():
                if usid == sid:
                    outflow_pairs.append((sid, vid))
                    outflow_pair_weight[(sid, vid)] = w
        elif s["village_id"] is not None:
            outflow_pairs.append((sid, s["village_id"]))
            outflow_pair_weight[(sid, s["village_id"])] = capacity_weights.get(sid) or 0.0

    outflow_share_m3: dict = {}
    villages_in_outflow_pairs = {vid for (_, vid) in outflow_pairs}
    for vid in villages_in_outflow_pairs:
        ids_for_village = [sid for (sid, v) in outflow_pairs if v == vid]
        weights_for_village = {sid: outflow_pair_weight[(sid, vid)] for sid in ids_for_village}
        demand_m3 = demand_by_village.get(vid, 0.0)
        share = _apportion(weights_for_village, demand_m3, ids_for_village)
        for sid, amt in share.items():
            outflow_share_m3[sid] = outflow_share_m3.get(sid, 0.0) + amt

    n_written = 0
    for s in sources:
        source_id = s["source_id"]
        source_type = s["source_type"]
        capacity = s.get("stored_capacity_m3")
        if capacity is None:
            continue  # ไม่ทราบความจุ = ไม่มีทางคลิป overflow/bootstrap % ได้เลย ข้ามแหล่งนี้ไป ไม่ fabricate

        capacity = float(capacity)
        is_assumed_start = source_id not in prev_storage
        storage_start = prev_storage.get(source_id)
        if storage_start is None:
            storage_start = _bootstrap_storage_start(s)

        use_regional_factor = _uses_regional_factor(s)

        if use_regional_factor:
            factor_pct = regional_factor.get(month)
            if factor_pct is None:
                continue  # ไม่มีเรทของเดือนนี้ (ไม่ควรเกิด เพราะมีครบ 12 เดือนแล้ว แต่กันไว้ ไม่ fabricate)
            raw_end = storage_start * (1 + factor_pct / 100.0)
            storage_end = max(0.0, min(raw_end, capacity))
            net_change = storage_end - storage_start
            inflow_m3 = round(max(0.0, net_change), 2)
            outflow_m3 = round(max(0.0, -net_change), 2)
            loss_m3 = 0.0
            overflow_m3 = round(max(0.0, raw_end - capacity), 2)
            unmet_demand_m3 = None  # ยังไม่มีกลไกแบ่งสัดส่วนความต้องการต่อหมวดสำหรับอ่างที่ใช้ร่วมกันทั้งตำบล
            capture_efficiency_used = None
            model_path = "regional_seasonal_factor"
        else:
            if source_type not in CAPTURE_EFFICIENCY_BY_SOURCE_TYPE:
                continue  # small_water_source/groundwater_well/mountain_spring/purchased_external — ยังไม่มีโมเดล
            capture_efficiency_used = CAPTURE_EFFICIENCY_BY_SOURCE_TYPE[source_type]
            inflow_m3 = round(inflow_share_m3.get(source_id, 0.0) * capture_efficiency_used, 2)
            raw_outflow = outflow_share_m3.get(source_id)  # None ถ้าเป็นแหล่งระดับตำบล (ดูสมมติฐานข้อ 3)
            loss_m3 = 0.0
            available = storage_start + inflow_m3 - loss_m3
            if raw_outflow is None:
                outflow_m3 = None
                unmet_demand_m3 = None
                raw_end = available
            else:
                outflow_m3 = round(min(raw_outflow, available), 2)
                unmet_demand_m3 = round(max(0.0, raw_outflow - available), 2)
                raw_end = available - outflow_m3
            storage_end = max(0.0, min(raw_end, capacity))
            overflow_m3 = round(max(0.0, raw_end - capacity), 2)
            model_path = "physical"

        db.upsert_storage_depletion_monthly(
            conn, source_id, month_date,
            round(storage_start, 2), inflow_m3, outflow_m3, loss_m3, overflow_m3,
            round(storage_end, 2), unmet_demand_m3, capture_efficiency_used, model_path, is_assumed_start,
        )
        n_written += 1

    if n_written:
        conn.commit()
    return n_written
