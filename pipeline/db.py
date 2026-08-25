"""
db.py — เชื่อม Postgres (Supabase) ฝั่ง pipeline (แยกจาก backend/db.py เพราะ pipeline รันเป็น
สคริปต์ standalone จาก GitHub Actions ไม่ใช่ FastAPI process — แต่หลักการเดียวกัน)
"""
import os

import psycopg
from psycopg.rows import dict_row


def get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    # prepare_threshold=None: ปิด server-side prepared statement ของ psycopg3 — จำเป็นเพราะเราต่อผ่าน
    # Supabase Transaction pooler (Supavisor) ซึ่งสลับ backend connection ให้ทุก transaction ทำให้ชื่อ
    # prepared statement (เช่น _pg3_0) ที่ psycopg เตรียมไว้บน connection object ไปชนกับสิ่งที่ backend
    # จริงมีอยู่ — เจอจริงตอนรัน backfill 2568-08: psycopg.errors.DuplicatePreparedStatement เพราะสคริปต์นี้
    # เปิด connection เดียวรันซ้ำหลายสิบครั้ง (ทุกหมู่บ้าน x ทุกตำบล) เกิน prepare_threshold ค่าเริ่มต้น (5)
    return psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row, prepare_threshold=None)


def fetch_tambons(conn, only_pilot: bool = False) -> list[dict]:
    """คืนทุกตำบล พร้อม geometry เป็น GeoJSON dict (None ถ้ายังไม่มี geometry)
    province_th เพิ่มเข้ามา 2569-08 ให้ storage_depletion.py ใช้ตัดสินใจว่าอ่างเก็บน้ำของตำบลนี้อยู่ใน
    ขอบเขต "ภาคเหนือ" ที่ regional_seasonal_storage_factor รองรับหรือไม่ (ดู
    storage_depletion.py::NORTHERN_THAILAND_PROVINCES_TH)"""
    sql = "select tambon_id, name_th, province_th, ST_AsGeoJSON(geom)::json as geom_geojson from tambons"
    if only_pilot:
        sql += " where is_pilot = true"
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def fetch_villages(conn, tambon_id: str) -> list[dict]:
    """คืนหมู่บ้านทั้งหมดของตำบล พร้อม geometry รวมของหมู่บ้าน (union ของ
    village_boundary_parts ทุกส่วน — บางหมู่บ้านมี 2 เขตพื้นที่แยกกัน เช่น หมู่ 9/11)"""
    sql = """
        select v.village_id, v.name_th, v.moo,
               ST_AsGeoJSON(ST_Union(p.geom))::json as geom_geojson
        from villages v
        join village_boundary_parts p on p.village_id = v.village_id
        where v.tambon_id = %s
        group by v.village_id, v.name_th, v.moo
    """
    with conn.cursor() as cur:
        cur.execute(sql, (tambon_id,))
        return cur.fetchall()


def upsert_rainfall_monthly(conn, tambon_id: str, month: str, rainfall_mm: float | None):
    if rainfall_mm is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into rainfall_monthly (tambon_id, month, rainfall_mm, source) "
            "values (%s, %s, %s, 'CHIRPS') "
            "on conflict (tambon_id, month) do update set rainfall_mm = excluded.rainfall_mm, source = excluded.source",
            (tambon_id, month, rainfall_mm),
        )


def upsert_et0_monthly(conn, tambon_id: str, month: str, et0_mm: float | None):
    if et0_mm is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into et0_monthly (tambon_id, month, et0_mm, source) "
            "values (%s, %s, %s, 'MODIS') "
            "on conflict (tambon_id, month) do update set et0_mm = excluded.et0_mm, source = excluded.source",
            (tambon_id, month, et0_mm),
        )


def upsert_zone_landcover_monthly(
    conn, village_id: str, month: str,
    forest_pct: float | None, agri_pct: float | None, residential_pct: float | None,
    runoff_coefficient: float | None, source: str,
):
    # 'source' บันทึกที่มาจริงของหมู่บ้านนี้ — 'LDD_landuse_2566' (ข้อมูลทางการ ปัจจุบันมีแค่แม่นาเรือ)
    # หรือ 'ESA_WorldCover_v200' (fallback ผ่าน GEE สำหรับตำบลอื่น — ดู pipeline/landcover.py หัวไฟล์
    # ส่วน 2026-08-23) — รับมาจาก compute_landcover_breakdown() แทนที่จะ hardcode ค่าเดียวเหมือนเดิม
    if runoff_coefficient is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into zone_landcover_monthly "
            "(village_id, month, forest_pct, agri_pct, residential_pct, runoff_coefficient, source) "
            "values (%s, %s, %s, %s, %s, %s, %s) "
            "on conflict (village_id, month) do update set "
            "forest_pct = excluded.forest_pct, agri_pct = excluded.agri_pct, "
            "residential_pct = excluded.residential_pct, runoff_coefficient = excluded.runoff_coefficient, "
            "source = excluded.source",
            (village_id, month, forest_pct, agri_pct, residential_pct, runoff_coefficient, source),
        )


def upsert_rice_paddy_monthly(conn, village_id: str, month: str, paddy_area_rai: float | None):
    if paddy_area_rai is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into rice_paddy_monthly (village_id, month, paddy_area_rai, source) "
            "values (%s, %s, %s, 'Sentinel-1 SAR') "
            "on conflict (village_id, month) do update set paddy_area_rai = excluded.paddy_area_rai, "
            "source = excluded.source",
            (village_id, month, paddy_area_rai),
        )


# =============================================================================
# เพิ่มเติมสำหรับ Phase 5 (balance_engine.py) — ต่อท้ายฟังก์ชันเดิมของ Phase 2 ด้านบน
# =============================================================================

def fetch_climate(conn, tambon_id: str, month: str) -> dict | None:
    """คืน {'rainfall_mm':..., 'et0_mm':..., 'et0_estimated': bool} ของตำบล/เดือนนั้น หรือ None ถ้าไม่มีทาง
    หาค่า et0_mm ได้เลย (rainfall_mm อาจ NULL ได้โดยไม่ block การคำนวณ agri เพราะไม่ได้ใช้หัก effective
    rainfall ในเวอร์ชันนี้ — ดู balance_engine.py ข้อจำกัดข้อ 4)

    ถ้ายังไม่มี et0_mm จริงของเดือนนี้ (เดือนปัจจุบันที่ CHIRPS/MOD16A2 ยังไม่ปิด composite เดือน หรือเดือน
    เก่าที่ยังไม่ backfill) จะ fallback ไปใช้ค่าเฉลี่ยของ "เดือนปฏิทินเดียวกัน" จากปีก่อนหน้าที่มีข้อมูลจริง
    แทนชั่วคราว (climatological average) — ดู 00_docs/future-tambon-onboarding-plan.md ข้อ 7 ส่วนเสริม
    2026-08-22 สำหรับเหตุผลที่เลือกวิธีนี้แทน "เอาเดือนก่อนหน้ามาใช้" — ผลลัพธ์ที่ fallback มี
    et0_estimated=True กำกับไว้เสมอ เพื่อให้ผู้เรียกใช้ (เช่น balance_engine.py) log/แจ้งเตือนได้ว่าเป็น
    ค่าประมาณการ ไม่ใช่ค่าจริงจากดาวเทียม"""
    with conn.cursor() as cur:
        cur.execute(
            "select r.rainfall_mm, e.et0_mm from et0_monthly e "
            "left join rainfall_monthly r on r.tambon_id = e.tambon_id and r.month = e.month "
            "where e.tambon_id = %s and e.month = %s",
            (tambon_id, month),
        )
        row = cur.fetchone()
    if row and row["et0_mm"] is not None:
        return {"rainfall_mm": row["rainfall_mm"], "et0_mm": row["et0_mm"], "et0_estimated": False}
    return fetch_climatological_et0_fallback(conn, tambon_id, month)


def fetch_climatological_et0_fallback(conn, tambon_id: str, month: str) -> dict | None:
    """ค่าเฉลี่ย et0_mm ของ "เดือนปฏิทินเดียวกัน" (เช่น ก.ค. ทุกปี) จากทุกปีก่อนหน้าของตำบลนี้ที่มี et0_mm
    จริงแล้ว (ไม่รวมเดือนเป้าหมายเอง — เผื่อกรณีมีค่า partial/ผิดพลาดติดอยู่) คืน None ถ้าไม่มีข้อมูลปีก่อน
    เลยแม้แต่ปีเดียว (ตำบลใหม่ปีแรกยังไม่มีอะไรให้เฉลี่ย — ต้องรอข้อมูลจริงต่อไป ไม่ fabricate ค่าขึ้นมาลอยๆ)"""
    with conn.cursor() as cur:
        cur.execute(
            "select avg(et0_mm) as avg_et0, count(*) as n from et0_monthly "
            "where tambon_id = %s and month <> %s "
            "and extract(month from month) = extract(month from %s::date) "
            "and et0_mm is not null",
            (tambon_id, month, month),
        )
        row = cur.fetchone()
    if not row or not row["n"] or row["avg_et0"] is None:
        return None
    return {"rainfall_mm": None, "et0_mm": float(row["avg_et0"]), "et0_estimated": True}


def fetch_kc_reference(conn) -> dict:
    """คืน {crop_name (=ชื่อกลุ่ม Kc): dict_row ทั้งแถว} จาก crop_kc_reference"""
    with conn.cursor() as cur:
        cur.execute(
            "select crop_name, crop_type, kc_ini, kc_mid, kc_end, growth_days, "
            "ini_days, dev_days, mid_days, late_days, planting_month_default, source, note "
            "from crop_kc_reference"
        )
        return {row["crop_name"]: row for row in cur.fetchall()}


def fetch_crop_group_alias(conn) -> dict:
    """คืน {primary_name: crop_group} จาก crop_group_alias — mapping "พืชหลัก" (ก่อน '+'/'/' ตัวแรกใน
    crop_report.crop_name ตัด primary_crop() แล้ว) -> ชื่อกลุ่ม Kc ใน crop_kc_reference เดิมเป็น
    PRIMARY_TO_GROUP dict ฝังในโค้ดไฟล์นี้เอง ย้ายมาเป็นตาราง (2569-08) เพื่อให้ backend/routes.py อ่าน
    mapping เดียวกันได้ตอน validate ชื่อพืชที่ผู้ใช้กรอกเข้ามา — ดูคอมเมนต์ตาราง crop_group_alias ในฐานข้อมูล"""
    with conn.cursor() as cur:
        cur.execute("select primary_name, crop_group from crop_group_alias")
        return {row["primary_name"]: row["crop_group"] for row in cur.fetchall()}


def fetch_cropping_calendar(conn, tambon_id: str) -> dict:
    """คืน {crop_group: [dict_row, ...]} จาก cropping_calendar เฉพาะตำบลนี้ — ใช้ override ปฏิทินปลูก/
    เส้นโค้ง Kc ของ crop_kc_reference (ค่า global) เมื่อพฤติกรรมการปลูกของตำบลนี้ต่างจากค่าเริ่มต้น (เช่น
    ทำนา 2 รอบ/ปี หรือเดือนปลูกไม่ตรงกับตำบลต้นแบบที่ใช้ตั้งค่า global) — crop_group ไหนไม่มีแถวในนี้เลย จะ
    fallback ไปใช้ค่า global ตามเดิม (ดู pipeline/balance_engine.py::resolve_kc_for_group)"""
    with conn.cursor() as cur:
        cur.execute(
            "select crop_group, cycle_name, is_continuous, planting_month, "
            "kc_ini, kc_mid, kc_end, ini_days, dev_days, mid_days, late_days, source, note "
            "from cropping_calendar where tambon_id = %s",
            (tambon_id,),
        )
        rows = cur.fetchall()
    result: dict = {}
    for row in rows:
        result.setdefault(row["crop_group"], []).append(row)
    return result


def fetch_villages_with_population(conn, tambon_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select village_id, name_th, moo, population, total_rai from villages where tambon_id = %s order by moo",
            (tambon_id,),
        )
        return cur.fetchall()


def fetch_crop_report_latest(conn, tambon_id: str) -> list[dict]:
    """ดึง crop_report แถวล่าสุดต่อหมู่บ้าน (reported_month ล่าสุดที่มีข้อมูลของแต่ละหมู่บ้าน) —
    ปัจจุบันมีแค่เดือนเดียว (2026-07-01) ต่อหมู่บ้านอยู่แล้ว แต่เขียนให้รองรับหลายเดือนในอนาคตด้วย
    distinct on ต่อ (village_id, crop_name) เอาแถวที่ reported_month ใหม่สุด"""
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (cr.village_id, cr.crop_name)
                cr.village_id, cr.crop_name, cr.planted_area_rai, cr.reported_month
            from crop_report cr
            join villages v on v.village_id = cr.village_id
            where v.tambon_id = %s
            order by cr.village_id, cr.crop_name, cr.reported_month desc
            """,
            (tambon_id,),
        )
        return cur.fetchall()


def fetch_livestock_report_latest(conn, tambon_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (lr.village_id, lr.species)
                lr.village_id, lr.species, lr.head_count, lr.reported_month
            from livestock_report lr
            join villages v on v.village_id = lr.village_id
            where v.tambon_id = %s
            order by lr.village_id, lr.species, lr.reported_month desc
            """,
            (tambon_id,),
        )
        return cur.fetchall()


def fetch_livestock_constants(conn) -> dict:
    """คืน {'วัว': 15.0, 'ควาย': 18.0} จาก water_demand_constants (category='livestock')"""
    with conn.cursor() as cur:
        cur.execute("select constant_key, value from water_demand_constants where category = 'livestock'")
        rows = cur.fetchall()
    result = {}
    for row in rows:
        if "cattle" in row["constant_key"]:
            result["วัว"] = float(row["value"])
        elif "buffalo" in row["constant_key"]:
            result["ควาย"] = float(row["value"])
    return result


def fetch_consumption_domestic_constants(conn) -> tuple[float, float]:
    """คืน (consumption_lpcd, domestic_lpcd) จาก water_demand_constants"""
    with conn.cursor() as cur:
        cur.execute(
            "select constant_key, value from water_demand_constants "
            "where constant_key in ('consumption_lpcd', 'domestic_lpcd')"
        )
        rows = {r["constant_key"]: float(r["value"]) for r in cur.fetchall()}
    return rows.get("consumption_lpcd", 2.0), rows.get("domestic_lpcd", 50.0)


def fetch_village_pond_stock(conn, tambon_id: str) -> dict:
    """คืน {village_id: sum(stored_capacity_m3)} เฉพาะแหล่งน้ำที่ผูก village_id (สระ/บ่อระดับหมู่บ้าน)
    *** ไม่รวมอ่างเก็บน้ำระดับตำบล (village_id IS NULL) — ดู balance_engine.py หัวไฟล์ ***"""
    with conn.cursor() as cur:
        cur.execute(
            "select village_id, sum(stored_capacity_m3) as total_m3 "
            "from water_storage_sources "
            "where tambon_id = %s and village_id is not null and stored_capacity_m3 is not null "
            "group by village_id",
            (tambon_id,),
        )
        return {row["village_id"]: float(row["total_m3"]) for row in cur.fetchall()}


def fetch_village_runoff_coefficients(conn, tambon_id: str, month: str) -> dict:
    """คืน {village_id: runoff_coefficient} จาก zone_landcover_monthly ของเดือนนั้น — มาจาก land cover
    classification ใน pipeline/run_monthly.py (Phase 2) อยู่ก่อนแล้ว ยังไม่เคยถูกใช้ในสมดุลน้ำ (Phase 5)
    เลยจนกระทั่ง compute_runoff_estimate() ใน balance_engine.py (2569-08) — หมู่บ้านไหนไม่มีแถวของเดือนนั้น
    (เช่น land cover ยังไม่เคยรันของเดือนนั้น) จะไม่มีคีย์ใน dict นี้เลย"""
    with conn.cursor() as cur:
        cur.execute(
            "select z.village_id, z.runoff_coefficient from zone_landcover_monthly z "
            "join villages v on v.village_id = z.village_id "
            "where v.tambon_id = %s and z.month = %s and z.runoff_coefficient is not null",
            (tambon_id, month),
        )
        return {row["village_id"]: float(row["runoff_coefficient"]) for row in cur.fetchall()}


def upsert_runoff_estimate_monthly(
    conn, village_id: str, month: str,
    rainfall_mm: float | None, runoff_coefficient: float | None, total_rai: float | None,
    runoff_volume_m3: float | None,
):
    """เขียนประมาณการน้ำท่าลงตาราง runoff_estimate_monthly — ตารางนี้แยกจาก water_balance_monthly โดยเด็ดขาด
    ไม่ถูกรวมเข้า supply_cum ของสมดุลน้ำเลย (ดูคอมเมนต์ตารางในฐานข้อมูล) ใช้แค่ดูขนาดน้ำท่าประมาณการก่อน
    ตัดสินใจว่าจะเอามารวมยังไง"""
    with conn.cursor() as cur:
        cur.execute(
            "insert into runoff_estimate_monthly "
            "(village_id, month, rainfall_mm, runoff_coefficient, total_rai, runoff_volume_m3, computed_at) "
            "values (%s, %s, %s, %s, %s, %s, now()) "
            "on conflict (village_id, month) do update set "
            "rainfall_mm = excluded.rainfall_mm, runoff_coefficient = excluded.runoff_coefficient, "
            "total_rai = excluded.total_rai, runoff_volume_m3 = excluded.runoff_volume_m3, "
            "computed_at = excluded.computed_at",
            (village_id, month, rainfall_mm, runoff_coefficient, total_rai, runoff_volume_m3),
        )


def write_balance_results(conn, tambon_id, month, crop_demand_rows, livestock_demand_rows, balance_rows):
    """เขียนผลทั้ง 3 ตาราง — ลบของเดือน/ตำบลนั้นทิ้งก่อนแล้วค่อย insert ใหม่ทั้งชุด (idempotent ต่อการรันซ้ำ)"""
    village_ids_subq = "select village_id from villages where tambon_id = %s"
    with conn.cursor() as cur:
        cur.execute(f"delete from crop_water_demand_monthly where month = %s and village_id in ({village_ids_subq})",
                    (month, tambon_id))
        cur.execute(f"delete from livestock_water_demand_monthly where month = %s and village_id in ({village_ids_subq})",
                    (month, tambon_id))
        cur.execute(f"delete from water_balance_monthly where month = %s and village_id in ({village_ids_subq})",
                    (month, tambon_id))

        cur.executemany(
            "insert into crop_water_demand_monthly (village_id, month, crop_name, demand_cum) "
            "values (%s, %s, %s, %s)",
            crop_demand_rows,
        )
        cur.executemany(
            "insert into livestock_water_demand_monthly (village_id, month, species, demand_cum) "
            "values (%s, %s, %s, %s)",
            livestock_demand_rows,
        )
        cur.executemany(
            "insert into water_balance_monthly "
            "(village_id, month, category, supply_cum, demand_cum, balance_cum, status, computed_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, now())",
            balance_rows,
        )


# =============================================================================
# เพิ่มเติมสำหรับ storage_depletion (สต๊อกน้ำรายแหล่ง/รายเดือน) — 2569-08
# ใช้ทั้งฝั่ง pipeline/catchment.py (GEE, เรียกจาก run_monthly.py) และ
# pipeline/storage_depletion.py (DB-only, เรียกจาก balance_engine.py) — ดู
# runoff-depletion-model-design.html §04/§05 สำหรับที่มาของการออกแบบ
# =============================================================================

def fetch_sources_missing_catchment_area(conn) -> list[dict]:
    """คืนแหล่งน้ำ (ทุกตำบล) ที่มีพิกัด lat/lon แต่ยังไม่เคยคำนวณ catchment_area_km2 เลย — ใช้จาก
    pipeline/run_monthly.py ตอนเริ่มรัน (ก่อน loop ตำบล) เพราะเป็นงานคำนวณครั้งเดียวไม่ผูกกับเดือนไหน
    (ภูมิประเทศไม่เปลี่ยน) ต่างจาก rainfall/ET0/landcover ที่ต้องคำนวณใหม่ทุกเดือน — เช็ค
    catchment_area_computed_at IS NULL เป็นตัวกันไม่ให้เรียก GEE ซ้ำโดยไม่จำเป็น"""
    with conn.cursor() as cur:
        cur.execute(
            "select source_id, name_th, lat, lon from water_storage_sources "
            "where lat is not null and lon is not null and catchment_area_computed_at is null"
        )
        return cur.fetchall()


def upsert_source_catchment_area(conn, source_id: str, catchment_area_km2: float):
    with conn.cursor() as cur:
        cur.execute(
            "update water_storage_sources set catchment_area_km2 = %s, catchment_area_computed_at = now() "
            "where source_id = %s",
            (catchment_area_km2, source_id),
        )


def fetch_water_storage_sources(conn, tambon_id: str) -> list[dict]:
    """คืนแหล่งน้ำทั้งหมดของตำบล พร้อมฟิลด์ที่ pipeline/storage_depletion.py ต้องใช้ — ทุกประเภท (ไม่กรอง
    source_type ตรงนี้ ให้ compute_storage_depletion() เป็นคนตัดสินใจว่าประเภทไหนมีโมเดลรองรับแล้วบ้าง
    ตาม CAPTURE_EFFICIENCY_BY_SOURCE_TYPE — สอดคล้องกับคอมเมนต์ตาราง storage_depletion_monthly ในฐานข้อมูล
    ที่ระบุไว้ชัดว่า groundwater_well/mountain_spring/purchased_external/small_water_source ยังไม่มีโมเดล)"""
    with conn.cursor() as cur:
        cur.execute(
            "select source_id, tambon_id, village_id, source_type, name_th, "
            "stored_capacity_m3, initial_level_pct, catchment_area_km2 "
            "from water_storage_sources where tambon_id = %s",
            (tambon_id,),
        )
        return cur.fetchall()


def fetch_previous_storage_end(conn, source_ids: list[str], prev_month: str) -> dict:
    """คืน {source_id: storage_end_m3} ของเดือนก่อนหน้า (prev_month) — ใช้เป็น storage_start_m3 ของเดือนนี้
    (ต่อเนื่องกันเป็น chain เดือนต่อเดือน) แหล่งน้ำไหนไม่มีแถวของเดือนก่อน (เพิ่งเริ่มมีข้อมูล หรือเดือนก่อน
    ไม่ได้รัน pipeline) จะไม่มีคีย์ใน dict นี้ — ผู้เรียกต้อง bootstrap จาก initial_level_pct แทน (ดู
    storage_depletion.py::compute_storage_depletion, is_assumed_start=True กรณีนี้)"""
    if not source_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "select source_id, storage_end_m3 from storage_depletion_monthly "
            "where source_id = any(%s) and month = %s and storage_end_m3 is not null",
            (source_ids, prev_month),
        )
        return {row["source_id"]: float(row["storage_end_m3"]) for row in cur.fetchall()}


def fetch_regional_seasonal_factor(conn, source_type: str = "reservoir") -> dict:
    """คืน {month(int 1-12): avg_pct_full_change(float)} จาก regional_seasonal_storage_factor —
    ปัจจุบันมี region_key เดียวคือ 'phayao_upper_ing' (จากข้อมูลจริง 4 อ่างที่ตำบลแม่นาเรือเท่านั้น) แต่
    ตามคอมเมนต์ตาราง เรทนี้ถูกอนุมัติให้ใช้เป็น fallback ของ "อ่างเก็บน้ำในภาคเหนือ (บน+ล่าง) ทุกตำบล" ไม่ใช่
    เฉพาะลุ่มน้ำอิงตอนบนเท่านั้น — จึงยังไม่กรองด้วย region_key ตรงนี้ (ถ้าอนาคตมีข้อมูลจริงของภูมิภาคอื่นเพิ่ม
    เข้ามาจะต้องแก้ฟังก์ชันนี้ให้เลือก region_key ตาม tambon ที่เหมาะสมแทนการใช้ตัวเดียวทั้งหมด)"""
    with conn.cursor() as cur:
        cur.execute(
            "select month, avg_pct_full_change from regional_seasonal_storage_factor where source_type = %s",
            (source_type,),
        )
        return {int(row["month"]): float(row["avg_pct_full_change"]) for row in cur.fetchall()}


def fetch_runoff_estimate_by_village(conn, tambon_id: str, month: str) -> dict:
    """คืน {village_id: runoff_volume_m3} ของเดือนนั้น จาก runoff_estimate_monthly — ต้องเรียกหลัง
    balance_engine.py::compute_runoff_estimate() เขียนของเดือนนี้เสร็จแล้วในรันเดียวกันเสมอ (ดูลำดับเรียกใน
    run_for_tambon()) หมู่บ้านที่ไม่มีแถว (ขาดข้อมูล runoff_coefficient/total_rai/rainfall_mm เดือนนั้น) จะ
    ไม่มีคีย์ใน dict นี้"""
    with conn.cursor() as cur:
        cur.execute(
            "select r.village_id, r.runoff_volume_m3 from runoff_estimate_monthly r "
            "join villages v on v.village_id = r.village_id "
            "where v.tambon_id = %s and r.month = %s and r.runoff_volume_m3 is not null",
            (tambon_id, month),
        )
        return {row["village_id"]: float(row["runoff_volume_m3"]) for row in cur.fetchall()}


def fetch_reservoir_village_usage(conn, tambon_id: str) -> list[dict]:
    """คืนแถว reservoir_village_usage ของแหล่งน้ำทุกแห่งในตำบลนี้ (join ผ่าน water_storage_sources.tambon_id
    เพราะตาราง reservoir_village_usage เองไม่มีคอลัมน์ tambon_id) — ตารางนี้มีอยู่แล้วในฐานข้อมูล เก็บการ
    ใช้น้ำจริงต่อคู่ (แหล่งน้ำ, หมู่บ้าน) ใช้แบ่งสัดส่วน Outflow ให้แหล่งน้ำที่ใช้ร่วมกันหลายหมู่บ้าน (เช่น
    อ่างเก็บน้ำแม่นาเรือ ที่ 3 หมู่บ้านใช้ร่วมกัน) แทนสมมติฐาน capacity-share ล้วนๆ เมื่อมีข้อมูลการใช้จริง
    (households/population/irrigated_area_rai) อยู่แล้ว — ดู pipeline/storage_depletion.py"""
    with conn.cursor() as cur:
        cur.execute(
            "select ru.source_id, ru.village_id, ru.use_type, ru.households, ru.population, "
            "ru.irrigated_area_rai "
            "from reservoir_village_usage ru "
            "join water_storage_sources ws on ws.source_id = ru.source_id "
            "where ws.tambon_id = %s",
            (tambon_id,),
        )
        return cur.fetchall()


def fetch_village_total_demand(conn, tambon_id: str, month: str) -> dict:
    """คืน {village_id: sum(demand_cum) ทั้ง 4 หมวด} ของเดือนนั้น จาก water_balance_monthly — ใช้ประมาณ
    "ความต้องการใช้น้ำรวม" ของหมู่บ้านนั้น เพื่อคำนวณ outflow_m3 ของแหล่งน้ำที่ผูกกับหมู่บ้านนี้ (ต้องเรียกหลัง
    balance_engine.py::run_for_tambon() เขียน water_balance_monthly ของเดือนนี้เสร็จแล้วในรันเดียวกันเสมอ)
    *** เป็นค่าประมาณระดับหมู่บ้าน ไม่ได้แยกว่าแต่ละหมวดดึงน้ำจากแหล่งไหนบ้างจริงๆ (ไม่มีข้อมูลระดับนั้น) ***"""
    with conn.cursor() as cur:
        cur.execute(
            "select village_id, sum(demand_cum) as total_demand from water_balance_monthly "
            "where village_id in (select village_id from villages where tambon_id = %s) and month = %s "
            "group by village_id",
            (tambon_id, month),
        )
        return {row["village_id"]: float(row["total_demand"]) for row in cur.fetchall()}


def upsert_storage_depletion_monthly(
    conn, source_id: str, month: str,
    storage_start_m3, inflow_m3, outflow_m3, loss_m3, overflow_m3, storage_end_m3,
    unmet_demand_m3, capture_efficiency_used, model_path: str, is_assumed_start: bool,
):
    with conn.cursor() as cur:
        cur.execute(
            "insert into storage_depletion_monthly "
            "(source_id, month, storage_start_m3, inflow_m3, outflow_m3, loss_m3, overflow_m3, "
            "storage_end_m3, unmet_demand_m3, capture_efficiency_used, model_path, is_assumed_start, computed_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
            "on conflict (source_id, month) do update set "
            "storage_start_m3 = excluded.storage_start_m3, inflow_m3 = excluded.inflow_m3, "
            "outflow_m3 = excluded.outflow_m3, loss_m3 = excluded.loss_m3, "
            "overflow_m3 = excluded.overflow_m3, storage_end_m3 = excluded.storage_end_m3, "
            "unmet_demand_m3 = excluded.unmet_demand_m3, "
            "capture_efficiency_used = excluded.capture_efficiency_used, "
            "model_path = excluded.model_path, is_assumed_start = excluded.is_assumed_start, "
            "computed_at = excluded.computed_at",
            (source_id, month, storage_start_m3, inflow_m3, outflow_m3, loss_m3, overflow_m3,
             storage_end_m3, unmet_demand_m3, capture_efficiency_used, model_path, is_assumed_start),
        )
