# -*- coding: utf-8 -*-
"""
balance_engine.py — Phase 5: คำนวณสมดุลน้ำ 4 หมวด (บริโภค/อุปโภค/เกษตร/ปศุสัตว์) รายเดือนต่อหมู่บ้าน
เขียนผลเข้า crop_water_demand_monthly, livestock_water_demand_monthly, water_balance_monthly โดยตรง —
รูปแบบเดียวกับ pipeline/run_monthly.py (Phase 2): standalone script, direct DB write ผ่าน DATABASE_URL,
ไม่ผ่าน backend API เพราะรันเป็น cron job ไม่ใช่ user request

การใช้งาน:
    python pipeline/balance_engine.py                # ประมวลผลเดือนก่อนหน้า (default)
    python pipeline/balance_engine.py 2026 7          # ประมวลผลเดือน/ปีที่ระบุ (ใช้ตอนรันย้อนหลัง/backfill)

ก่อนรันต้องมี rainfall_monthly/et0_monthly ของเดือนนั้นแล้ว (จาก pipeline/run_monthly.py) — ถ้ายังไม่มี
สคริปต์นี้จะข้ามตำบลนั้นไปพร้อม log เตือน (ไม่ fabricate ค่า ET0/ฝนขึ้นมาเอง)

=============================================================================
พื้นฐานสูตร (ดู 00_docs/00-system-design-reset.md ข้อ 2, 5, 15.5 ประกอบ)
=============================================================================
- น้ำบริโภค (consumption)  = ประชากร × 2  ลิตร/คน/วัน × จำนวนวันในเดือน
- น้ำอุปโภค (domestic)     = ประชากร × 50 ลิตร/คน/วัน × จำนวนวันในเดือน
  (ค่าคงที่ 2 กับ 50 อยู่ใน water_demand_constants — คำนวณย้อนจากไฟล์ V4 ตาม 00-system-design-reset.md ข้อ 2.2)
- น้ำปศุสัตว์ (livestock)  = จำนวนหัวสัตว์ต่อชนิด × ค่าคงที่ ลบ.ม./ตัว/ปี (water_demand_constants) ÷ 12
  (หาร 12 เกลี่ยเท่ากันทุกเดือน — ยังไม่มีข้อมูลฤดูกาลการเลี้ยงจริง ถือเป็นค่าประมาณเบื้องต้น)
- น้ำเกษตร (agri) ต่อแถวพืช = max(0, ETc(มม.) − ฝนใช้ประโยชน์ได้(มม.)) × พื้นที่ปลูก(ไร่) × 1.6
  โดย ETc = ET0(มม.) × Kc(เดือนนั้น)   [FAO-56 Single Crop Coefficient]
  Kc มาจาก crop_kc_reference (กลุ่มพืช, ดูตาราง crop_group_alias สำหรับการจับคู่ชื่อพืชจริง -> กลุ่ม)
  พืชกลุ่ม seasonal ใช้ growth curve (ini/dev/mid/late ตาม planting_month_default)
  พืชกลุ่ม perennial_flat ใช้ Kc คงที่ตัวเดียวทั้งปี (ไม่มีข้อมูลปีที่ปลูก/อายุต้นไม้ยืนต้น)
  "ฝนใช้ประโยชน์ได้" (effective rainfall) คำนวณจาก rainfall_mm ทั้งเดือนของตำบลนั้นด้วยสูตร USDA Soil
  Conservation Service (SCS) ตามที่ FAO Irrigation & Drainage Paper 25 อ้างอิง (ดู effective_rainfall_mm()
  ด้านล่าง) — เพิ่มเข้ามา 2569-08 แทนที่จะคืนค่า ETc ล้วนๆ เหมือนเดิม (ข้อจำกัดเดิมข้อ 4 ที่เคยแจ้งไว้ ตอนนี้
  แก้แล้ว) ถ้า rainfall_mm ของเดือนนั้นไม่มีค่า (None) จะถือว่าฝนใช้ประโยชน์ได้ = 0 (ไม่ fabricate ค่าขึ้นมาเอง
  — เท่ากับพฤติกรรมเดิมก่อนแก้)

- Supply (supply_cum) ต่อหมู่บ้าน = ผลรวม stored_capacity_m3 ของ water_storage_sources ที่ village_id ตรง
  กับหมู่บ้านนั้น (สระ/บ่อระดับหมู่บ้าน) — ใช้ค่าเดียวกัน "ซ้ำ" ทั้ง 4 หมวดต่อแถว เพราะสต็อกน้ำเป็นก้อนเดียว
  ที่แข่งกันใช้ทุกประเภท ไม่ได้แบ่งสัดส่วนตายตัวไว้ล่วงหน้าต่อประเภท (ตาม design doc ข้อ 5.1)
  *** อ่างเก็บน้ำระดับตำบล (water_storage_sources.village_id IS NULL) ไม่ถูกรวมในนี้ — เพราะไม่ผูกกับ
  หมู่บ้านใดหมู่บ้านหนึ่งโดยเฉพาะ จะถูกรวมเฉพาะตอนคำนวณ "ภาพรวมตำบล" ใน backend /balance endpoint แทน
  (ดู routes.py get_balance_tambon()) — เป็นการตัดสินใจด้านสถาปัตยกรรมที่ยังไม่ได้ยืนยันกับผู้ใช้ 100%
  ถ้าต้องการ allocate อ่างเก็บน้ำให้หมู่บ้านเฉพาะ (เช่นตามโซนชลประทาน Zone B ที่ผูกกับอ่างแต่ละแห่งใน
  01_raw_data/zone_เกษตร/zone_b_irrigated.shp) ต้องออกแบบเพิ่มใน Phase 6+

=============================================================================
ข้อจำกัดที่รู้อยู่แล้ว (ไม่ได้ปิดบัง แจ้งไว้ตรงนี้ให้เห็นชัด):
=============================================================================
1. planting_month_default ใน crop_kc_reference เป็นค่า global ตั้งจากข้อมูลจริงของแม่นาเรือ (ปฏิทิน
   เพาะปลูกรายสัปดาห์_แม่นาเรือ.xlsx) ใช้เป็น fallback กลางสำหรับตำบลที่ยังไม่มีข้อมูลเฉพาะของตัวเอง
   (เช่นตำบลใหม่ที่ยังไม่กรอก) — ตำบลที่พฤติกรรมปลูกต่างจากค่ากลาง (เดือนปลูกต่างกัน, ปลูกหลายรอบ/ปี เช่น
   นาปี+นาปรัง, หรือปลูกต่อเนื่องทั้งปีแทนที่จะมีฤดูกาล) ให้เพิ่มแถว override ในตาราง cropping_calendar
   แทน (ดู resolve_kc_for_group ด้านล่าง) ไม่ต้องแก้ค่า global — ยังไม่ผูกกับ Sentinel-1 rice_paddy_monthly
   จริง (มีตารางแล้วแต่ยังไม่มีข้อมูล)
2. Kc ของไม้ผล/ไม้ยืนต้นหลายชนิด (ลำไย ยางพารา สัก ฯลฯ) เป็นค่าประมาณกลุ่ม (ดู crop_kc_reference.note
   ของแต่ละแถว) เพราะสืบค้นวรรณกรรมแล้วไม่พบค่า Kc เฉพาะพันธุ์ที่เชื่อถือได้ในรอบการค้นคว้าตอน Phase 5
3. ปศุสัตว์: แม่นาเรือกรอกครบทุกหมู่บ้านแล้ว (ยืนยัน 0 ตัวจริงทุกหมู่บ้าน) นครป่าหมากเริ่มกรอกแล้วบางส่วน
   (2569-08) หมู่บ้านที่ยังไม่มีแถว livestock_report เลยถือเป็น "ยังไม่ยืนยัน" ไม่ใช่ "ยืนยันว่าไม่มี" —
   ต่างจากแม่นาเรือที่กรอกยืนยัน 0 ไว้ครบทุกหมู่บ้านแล้วจริงๆ
4. (แก้แล้ว 2569-08) เดิมไม่ได้หักฝนที่ตกลงมา (effective rainfall) ออกจาก agri_demand เลย ตอนนี้หักแล้ว
   ด้วยสูตร USDA SCS (ดู effective_rainfall_mm()) — ผลคือ crop_water_demand_monthly.demand_cum ตอนนี้คือ
   "ความต้องการน้ำชลประทานสุทธิ" (net irrigation requirement) ไม่ใช่ ETc ดิบๆ เหมือนก่อนหน้านี้แล้ว ถ้า
   ต้องการดู ETc ดิบ (ก่อนหักฝน) ต้องคำนวณแยกเอง ไม่ได้เก็บไว้ในตารางนี้
5. น้ำท่า/runoff ยังไม่ถูกนับเป็นน้ำต้นทุน (supply_cum) เลย — supply_cum มาจากสต็อกในสระ/บ่อ/อ่างเก็บน้ำ
   เท่านั้น ตั้งใจไม่รวมน้ำท่าเข้าไปตรงๆ เพราะเป็นคนละหน่วย (flow vs stock) และเสี่ยงนับซ้ำกับน้ำที่ไหลเข้า
   สระอยู่แล้ว — เพิ่มตาราง runoff_estimate_monthly แยกต่างหาก (2569-08) ให้ดูขนาดน้ำท่าประมาณการก่อน
   ตัดสินใจว่าจะเอามารวมในสมดุลยังไง (ดู compute_runoff_estimate() ด้านล่าง) — ยังไม่ตัดสินใจ รอดูตัวเลข
   จริงก่อน
"""
import datetime
import sys

import db

# ---------------------------------------------------------------------------
# 1. ค่าคงที่ทั่วไป
# ---------------------------------------------------------------------------
MM_RAI_TO_CUM = 1.6  # 1 มม. บนพื้นที่ 1 ไร่ = 1.6 ลบ.ม.


def days_in_month(y: int, m: int) -> int:
    nm = datetime.date(y + 1, 1, 1) if m == 12 else datetime.date(y, m + 1, 1)
    return (nm - datetime.date(y, m, 1)).days


def effective_rainfall_mm(total_rainfall_mm) -> float:
    """สูตร USDA Soil Conservation Service (SCS) สำหรับฝนใช้ประโยชน์ได้รายเดือน (ตามที่ FAO Irrigation &
    Drainage Paper 25 อ้างอิง — ใช้กันแพร่หลายใน CROPWAT และงานคำนวณ net irrigation requirement ทั่วไป)
    รับฝนรวมทั้งเดือน (มม.) คืนฝนใช้ประโยชน์ได้ (มม., เป็นสัดส่วนลดหลั่นเมื่อฝนเยอะขึ้น เพราะส่วนเกินไหลทิ้ง/
    ซึมเกินรากพืชไป ไม่ได้ถูกพืชใช้ทั้งหมด) — คืน 0.0 ถ้า total_rainfall_mm เป็น None หรือ ≤ 0 (ไม่ fabricate
    ค่าขึ้นมาเอง ถือว่าไม่รู้ค่าฝน = ไม่ให้เครดิตฝนช่วย เหมือนพฤติกรรมเดิมก่อนแก้)

    Pe = Ptot × (125 − 0.2×Ptot) / 125   เมื่อ Ptot ≤ 250 มม.
    Pe = 125 + 0.1×Ptot                  เมื่อ Ptot > 250 มม.
    """
    if total_rainfall_mm is None or total_rainfall_mm <= 0:
        return 0.0
    p = float(total_rainfall_mm)
    if p <= 250:
        pe = p * (125 - 0.2 * p) / 125
    else:
        pe = 125 + 0.1 * p
    return max(0.0, pe)


# ---------------------------------------------------------------------------
# 2. mapping: "พืชหลัก" (ก่อน '+' หรือ '/' ตัวแรก) -> ชื่อกลุ่มใน crop_kc_reference
#    ย้ายมาเก็บในตาราง crop_group_alias แล้ว (เดิมเป็น PRIMARY_TO_GROUP dict ฝังในไฟล์นี้ — ย้าย 2569-08
#    เพื่อให้ backend/routes.py อ่าน mapping เดียวกันได้ตอน validate ชื่อพืชที่ผู้ใช้กรอกเข้ามา ไม่ต้องพึ่งพา
#    dict ที่ฝังอยู่ใน pipeline/ ซึ่งเป็นคนละ process/deployment กัน — ดู db.fetch_crop_group_alias())
#    เพิ่มพืชชนิดใหม่ที่ crop_report เจอแล้วไม่มี mapping ให้ insert เข้าตาราง crop_group_alias โดยตรง
#    ไม่ต้องแก้ไฟล์นี้อีกต่อไป — พืชที่ไม่มี mapping ในตารางจะถูกข้ามแถวนั้นและ print คำเตือน (ไม่ raise error
#    ทั้ง run เพราะพืชแปลกๆ พื้นที่น้อยไม่ควรบล็อกทั้งตำบล แต่ log ให้เห็นชัดเพื่อไปเพิ่ม mapping ทีหลัง)
# ---------------------------------------------------------------------------


def primary_crop(raw_name: str) -> str:
    """ตัดเอาพืชหลัก (ก่อนตัว '+' หรือ '/' ตัวแรก) — heuristic เดียวกับที่ไฟล์ต้นฉบับ 'สรุปตามหมู่'
    ของ สรุปพื้นที่เพาะปลูกรายหมู่บ้าน_ตำบลแม่นาเรือ.xlsx ใช้เอง (ดู 04_scripts/generate_seed_sql.py
    และ /tmp/maenaruea/005_replace_maenaruea_crop_report_landuse.sql ประกอบ)"""
    name = raw_name.strip()
    for sep in ("+", "/"):
        if sep in name:
            name = name.split(sep, 1)[0].strip()
            break
    return name


# ---------------------------------------------------------------------------
# 3. FAO-56 growth curve (ตรรกะเดียวกับ 03_legacy_prototype/Final/crop_water_demand.py)
# ---------------------------------------------------------------------------

def kc_for_day(stages: dict, day_index: int):
    ini_kc, ini_d = stages["ini"]
    dev_kc, dev_d = stages["dev"]
    mid_kc, mid_d = stages["mid"]
    late_kc, late_d = stages["late"]
    if day_index < ini_d:
        return ini_kc
    day_index -= ini_d
    if day_index < dev_d:
        progress = day_index / dev_d if dev_d > 0 else 1.0
        return ini_kc + (mid_kc - ini_kc) * progress
    day_index -= dev_d
    if day_index < mid_d:
        return mid_kc
    day_index -= mid_d
    if day_index < late_d:
        progress = day_index / late_d if late_d > 0 else 1.0
        return mid_kc + (late_kc - mid_kc) * progress
    return None


def average_kc_for_month(kc_ref_row: dict, target_year: int, target_month: int):
    """kc_ref_row: 1 แถวจาก crop_kc_reference (dict_row) — คืน Kc เฉลี่ยถ่วงน้ำหนักวันของเดือนนั้น
    หรือค่า kc_mid คงที่ถ้าเป็น perennial_flat (planting_month_default IS NULL)"""
    if kc_ref_row["planting_month_default"] is None:
        return float(kc_ref_row["kc_mid"])

    stages = {
        "ini": (float(kc_ref_row["kc_ini"]), kc_ref_row["ini_days"]),
        "dev": (float(kc_ref_row["kc_mid"]), kc_ref_row["dev_days"]),  # ปลาย dev = mid (ไล่ระดับเชิงเส้น)
        "mid": (float(kc_ref_row["kc_mid"]), kc_ref_row["mid_days"]),
        "late": (float(kc_ref_row["kc_end"]), kc_ref_row["late_days"]),
    }
    planting_month = kc_ref_row["planting_month_default"]
    planting_year = target_year if planting_month <= target_month else target_year - 1
    planting_date = datetime.date(planting_year, planting_month, 1)
    month_start = datetime.date(target_year, target_month, 1)
    if month_start < planting_date:
        return None

    days_this_month = days_in_month(target_year, target_month)
    kc_values = []
    for d in range(days_this_month):
        current_date = month_start + datetime.timedelta(days=d)
        day_index = (current_date - planting_date).days
        kc = kc_for_day(stages, day_index)
        if kc is not None:
            kc_values.append(kc)
    if not kc_values:
        return None
    return sum(kc_values) / days_this_month


# ---------------------------------------------------------------------------
# 3.5 cropping_calendar — override ปฏิทินปลูก/เส้นโค้ง Kc เฉพาะตำบล (เพิ่ม 2569-08 หลังพบว่าตำบลต่างกัน
#     พฤติกรรมปลูกต่างกันมาก เช่น นครป่าหมากทำนา 2 รอบ/ปี (นาปี+นาปรัง) ขณะที่แม่นาเรือทำ 1 รอบ — ค่า
#     planting_month_default ใน crop_kc_reference เดิมเป็น global ค่าเดียวใช้ทั้งระบบไม่พอแล้ว
# ---------------------------------------------------------------------------

def kc_for_calendar_row(row: dict, target_year: int, target_month: int):
    """row: 1 แถวจาก cropping_calendar (dict_row) — คืน Kc ของเดือนนั้นถ้ารอบปลูกนี้ active, หรือ None ถ้าไม่
    (is_continuous=True คืนค่า kc_mid คงที่เสมอไม่ว่าจะเดือนไหน — ปลูกต่อเนื่องทั้งปี ไม่มีฤดูกาล)"""
    if row["is_continuous"]:
        return float(row["kc_mid"])
    # ใช้ตรรกะเดียวกับ average_kc_for_month โดย alias คีย์ planting_month -> planting_month_default
    # เพื่อไม่ต้องเขียนตรรกะ growth-curve ซ้ำสองที่
    fake_ref_row = {
        "planting_month_default": row["planting_month"],
        "kc_ini": row["kc_ini"], "kc_mid": row["kc_mid"], "kc_end": row["kc_end"],
        "ini_days": row["ini_days"], "dev_days": row["dev_days"],
        "mid_days": row["mid_days"], "late_days": row["late_days"],
    }
    return average_kc_for_month(fake_ref_row, target_year, target_month)


def resolve_kc_for_group(group_name: str, calendar_rows_by_group: dict, kc_reference: dict,
                          target_year: int, target_month: int):
    """คืน Kc ของกลุ่มพืชนี้ในเดือนนี้สำหรับตำบลปัจจุบัน — เช็ค cropping_calendar เฉพาะตำบลก่อนเสมอ ถ้ามี
    อย่างน้อย 1 แถวของ (ตำบลนี้, กลุ่มนี้) ถือว่า override เต็มชุด (ไม่ผสมกับค่า global) วนดูว่ารอบปลูกไหน
    active เดือนนี้บ้าง (ปกติมีรอบเดียว active ต่อเดือน เพราะรอบปลูกไม่ควรเหลื่อมกัน) ถ้าไม่มีแถว
    cropping_calendar เลยสำหรับกลุ่มนี้ fallback ไปใช้ค่า global ใน crop_kc_reference ตามเดิม"""
    calendar_rows = calendar_rows_by_group.get(group_name)
    if calendar_rows:
        for row in calendar_rows:
            kc = kc_for_calendar_row(row, target_year, target_month)
            if kc is not None:
                return kc
        return None  # มีปฏิทินเฉพาะตำบลของกลุ่มนี้ แต่ไม่มีรอบไหน active เดือนนี้เลย (ช่วงพักแปลง)
    kc_ref_row = kc_reference.get(group_name)
    if kc_ref_row is None:
        return None
    return average_kc_for_month(kc_ref_row, target_year, target_month)


# ---------------------------------------------------------------------------
# 4. คำนวณต่อตำบล
# ---------------------------------------------------------------------------

def run_for_tambon(conn, tambon: dict, year: int, month: int) -> None:
    tambon_id = tambon["tambon_id"]
    month_date = f"{year}-{month:02d}-01"

    climate = db.fetch_climate(conn, tambon_id, month_date)
    if climate is None or climate["et0_mm"] is None:
        print(f"  [ข้าม] {tambon['name_th']}: ยังไม่มี et0_mm ของเดือน {month_date} เลย "
              f"(ต้องรัน pipeline/run_monthly.py ก่อน และไม่มีข้อมูลปีก่อนหน้าให้ประมาณการ) — ไม่ fabricate ค่าขึ้นเอง")
        return
    et0_mm = float(climate["et0_mm"])
    if climate.get("et0_estimated"):
        print(f"  [ประมาณการ] {tambon['name_th']}: ยังไม่มี et0_mm จริงของเดือน {month_date} — ใช้ค่าเฉลี่ย "
              f"et0_mm ของเดือนปฏิทินเดียวกันจากปีก่อนหน้า = {et0_mm:.1f} มม. แทนชั่วคราว "
              f"(จะคำนวณซ้ำอัตโนมัติด้วยค่าจริงเมื่อ pipeline/run_monthly.py รันของเดือนนี้สำเร็จ)")

    eff_rain_mm = effective_rainfall_mm(climate.get("rainfall_mm"))
    if climate.get("rainfall_mm") is None:
        print(f"  [ไม่มีข้อมูลฝน] {tambon['name_th']}: ไม่มี rainfall_mm ของเดือน {month_date} — ถือว่าฝนใช้ "
              f"ประโยชน์ได้ = 0 มม. (ไม่หักออกจาก ETc เลยเดือนนี้)")
    else:
        print(f"  ฝนรวม={float(climate['rainfall_mm']):.1f} มม. → ฝนใช้ประโยชน์ได้ (SCS)={eff_rain_mm:.1f} มม.")

    kc_reference = db.fetch_kc_reference(conn)  # {group_name: dict_row} — ค่า global (fallback)
    calendar_rows_by_group = db.fetch_cropping_calendar(conn, tambon_id)  # {group_name: [row, ...]} เฉพาะตำบลนี้
    kc_cache: dict = {}

    def kc_for_group(group_name: str):
        if group_name not in kc_cache:
            kc_cache[group_name] = resolve_kc_for_group(
                group_name, calendar_rows_by_group, kc_reference, year, month
            )
        return kc_cache[group_name]

    crop_group_alias = db.fetch_crop_group_alias(conn)  # {primary_name: crop_group} — single source of truth
    villages = db.fetch_villages_with_population(conn, tambon_id)
    crop_rows = db.fetch_crop_report_latest(conn, tambon_id)
    livestock_rows = db.fetch_livestock_report_latest(conn, tambon_id)
    livestock_constants = db.fetch_livestock_constants(conn)
    consumption_lpcd, domestic_lpcd = db.fetch_consumption_domestic_constants(conn)
    pond_stock = db.fetch_village_pond_stock(conn, tambon_id)  # {village_id: total m3}
    days_this_month = days_in_month(year, month)

    village_agri_demand: dict = {}
    crop_demand_out = []
    unmapped = set()
    for row in crop_rows:
        vid = row["village_id"]
        raw = row["crop_name"]
        area = float(row["planted_area_rai"])
        p = primary_crop(raw)
        group = crop_group_alias.get(p)
        if group is None:
            unmapped.add((raw, p))
            continue
        kc = kc_for_group(group)
        demand = 0.0
        if kc is not None and area > 0:
            etc_mm = et0_mm * kc
            net_mm = max(0.0, etc_mm - eff_rain_mm)  # หักฝนใช้ประโยชน์ได้ออกก่อน ไม่ให้ติดลบ
            demand = round(net_mm * area * MM_RAI_TO_CUM, 2)
        crop_demand_out.append((vid, month_date, raw, demand))
        village_agri_demand[vid] = village_agri_demand.get(vid, 0.0) + demand

    if unmapped:
        print(f"  !!! พืชที่ไม่มี mapping ในตาราง crop_group_alias (ข้ามการคำนวณ agri สำหรับแถวนี้):")
        for raw, p in sorted(unmapped):
            print(f"      raw={raw!r} primary={p!r} — ต้อง insert เข้าตาราง crop_group_alias ก่อนรันรอบถัดไป")

    livestock_demand_out = []
    village_livestock_demand: dict = {}
    for row in livestock_rows:
        vid = row["village_id"]
        species = row["species"]
        head_count = row["head_count"] or 0
        per_head_year = livestock_constants.get(species)
        demand = round(head_count * per_head_year / 12.0, 2) if per_head_year else 0.0
        livestock_demand_out.append((vid, month_date, species, demand))
        village_livestock_demand[vid] = village_livestock_demand.get(vid, 0.0) + demand

    balance_out = []
    for v in villages:
        vid = v["village_id"]
        pop = v["population"] or 0
        consumption_demand = round(pop * consumption_lpcd * days_this_month / 1000.0, 2)
        domestic_demand = round(pop * domestic_lpcd * days_this_month / 1000.0, 2)
        agri_demand = round(village_agri_demand.get(vid, 0.0), 2)
        livestock_demand = round(village_livestock_demand.get(vid, 0.0), 2)
        supply = round(pond_stock.get(vid, 0.0), 2)

        for category, demand in [
            ("consumption", consumption_demand),
            ("domestic", domestic_demand),
            ("agri", agri_demand),
            ("livestock", livestock_demand),
        ]:
            balance = round(supply - demand, 2)
            status = "surplus" if (demand <= 0 or supply >= demand) else "deficit"
            balance_out.append((vid, month_date, category, supply, demand, balance, status))

    db.write_balance_results(conn, tambon_id, month_date, crop_demand_out, livestock_demand_out, balance_out)
    conn.commit()
    print(f"  {tambon['name_th']}: เขียน crop_demand={len(crop_demand_out)} แถว, "
          f"livestock_demand={len(livestock_demand_out)} แถว, balance={len(balance_out)} แถว")

    n_runoff = compute_runoff_estimate(conn, tambon_id, month_date, villages, climate.get("rainfall_mm"))
    print(f"  {tambon['name_th']}: เขียน runoff_estimate={n_runoff} หมู่บ้าน "
          f"(ตาราง runoff_estimate_monthly แยกต่างหาก — ไม่ถูกรวมใน supply_cum ของสมดุลน้ำ)")


def compute_runoff_estimate(conn, tambon_id: str, month_date: str, villages: list[dict], rainfall_mm) -> int:
    """คำนวณ+เขียนประมาณการน้ำท่า (runoff) ลงตาราง runoff_estimate_monthly — แยกจากการคำนวณสมดุลน้ำโดยเด็ดขาด
    ไม่มีผลต่อ supply_cum/demand_cum/balance_cum ของ water_balance_monthly เลยแม้แต่นิดเดียว (เพิ่ม 2569-08
    ให้ดูขนาดน้ำท่าประมาณการก่อนตัดสินใจว่าจะเอามารวมยังไง — ดูข้อจำกัดข้อ 5 ในหัวไฟล์ และคอมเมนต์ตารางใน
    ฐานข้อมูล) สูตร: runoff_volume_m3 = rainfall_mm(ตำบล) x runoff_coefficient(หมู่บ้าน) x total_rai(หมู่บ้าน)
    x 1.6 — เป็น "ศักยภาพน้ำท่ารวม" ไม่ใช่น้ำที่ดักเก็บใช้ได้จริง คืนจำนวนหมู่บ้านที่คำนวณได้สำเร็จ (ไว้ print สรุป)
    หมู่บ้านที่ขาดข้อมูล (ไม่มี runoff_coefficient ของเดือนนั้น, ไม่มี total_rai, หรือไม่มี rainfall_mm) จะถูก
    ข้ามไปเงียบๆ ไม่ fabricate ค่าขึ้นมาเอง"""
    runoff_coefficients = db.fetch_village_runoff_coefficients(conn, tambon_id, month_date)
    n_written = 0
    for v in villages:
        vid = v["village_id"]
        coeff = runoff_coefficients.get(vid)
        total_rai = v.get("total_rai")
        if coeff is None or total_rai is None or rainfall_mm is None:
            continue
        runoff_volume_m3 = round(float(rainfall_mm) * coeff * float(total_rai) * MM_RAI_TO_CUM, 2)
        db.upsert_runoff_estimate_monthly(
            conn, vid, month_date, float(rainfall_mm), coeff, float(total_rai), runoff_volume_m3
        )
        n_written += 1
    conn.commit()
    return n_written


def resolve_target_year_month(argv: list[str]) -> tuple[int, int]:
    if len(argv) >= 3:
        return int(argv[1]), int(argv[2])
    today = datetime.date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def main():
    year, month = resolve_target_year_month(sys.argv)
    print(f"=== Phase 5 balance engine: {year}-{month:02d} ===")
    conn = db.get_conn()
    try:
        tambons = db.fetch_tambons(conn)
        for tambon in tambons:
            print(f"--- {tambon['name_th']} ---")
            run_for_tambon(conn, tambon, year, month)
    finally:
        conn.close()
    print("=== เสร็จสิ้น ===")


if __name__ == "__main__":
    main()
