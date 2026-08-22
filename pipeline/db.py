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
    """คืนทุกตำบล พร้อม geometry เป็น GeoJSON dict (None ถ้ายังไม่มี geometry)"""
    sql = "select tambon_id, name_th, ST_AsGeoJSON(geom)::json as geom_geojson from tambons"
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
    runoff_coefficient: float | None,
):
    if runoff_coefficient is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into zone_landcover_monthly "
            "(village_id, month, forest_pct, agri_pct, residential_pct, runoff_coefficient, source) "
            # 'source' บันทึกที่มาจริง (ข้อมูลการใช้ที่ดินทางการปี 2566, ไม่ใช่ Sentinel-2 classification
            # ของเราเอง — ดูเหตุผลการเปลี่ยนใน pipeline/landcover.py หัวไฟล์)
            "values (%s, %s, %s, %s, %s, %s, 'LDD_landuse_2566') "
            "on conflict (village_id, month) do update set "
            "forest_pct = excluded.forest_pct, agri_pct = excluded.agri_pct, "
            "residential_pct = excluded.residential_pct, runoff_coefficient = excluded.runoff_coefficient, "
            "source = excluded.source",
            (village_id, month, forest_pct, agri_pct, residential_pct, runoff_coefficient),
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
    """คืน {'rainfall_mm':..., 'et0_mm':...} ของตำบล/เดือนนั้น หรือ None ถ้ายังไม่มี et0_mm
    (rainfall_mm อาจ NULL ได้โดยไม่ block การคำนวณ agri เพราะไม่ได้ใช้หัก effective rainfall ในเวอร์ชันนี้
    — ดู balance_engine.py ข้อจำกัดข้อ 4)"""
    with conn.cursor() as cur:
        cur.execute(
            "select r.rainfall_mm, e.et0_mm from et0_monthly e "
            "left join rainfall_monthly r on r.tambon_id = e.tambon_id and r.month = e.month "
            "where e.tambon_id = %s and e.month = %s",
            (tambon_id, month),
        )
        return cur.fetchone()


def fetch_kc_reference(conn) -> dict:
    """คืน {crop_name (=ชื่อกลุ่ม Kc): dict_row ทั้งแถว} จาก crop_kc_reference"""
    with conn.cursor() as cur:
        cur.execute(
            "select crop_name, crop_type, kc_ini, kc_mid, kc_end, growth_days, "
            "ini_days, dev_days, mid_days, late_days, planting_month_default, source, note "
            "from crop_kc_reference"
        )
        return {row["crop_name"]: row for row in cur.fetchall()}


def fetch_villages_with_population(conn, tambon_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select village_id, name_th, moo, population from villages where tambon_id = %s order by moo",
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
