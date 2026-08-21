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
    return psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row)


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
