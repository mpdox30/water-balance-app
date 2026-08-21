"""
run_monthly.py — orchestrator หลักของ Phase 2 GEE pipeline: รันทุกตำบล x ทุกหมู่บ้าน สำหรับ 1 เดือน
เขียนผลตรงเข้า Supabase ผ่าน DATABASE_URL (direct DB write — เลือกทางนี้แทนเรียกผ่าน backend API
เพราะสคริปต์นี้รันเป็น cron job ใน GitHub Actions ไม่ใช่ user-facing request ไม่จำเป็นต้องผ่าน HTTP
อีกชั้น และ Supavisor pooler รองรับ short-lived script ได้ดีอยู่แล้ว)

การใช้งาน:
    python pipeline/run_monthly.py                  # ประมวลผลเดือนก่อนหน้า (default)
    python pipeline/run_monthly.py 2026 7            # ประมวลผลเดือน/ปีที่ระบุ (ใช้ตอนรันย้อนหลัง)

Environment variables ที่ต้องตั้ง:
    DATABASE_URL          — เหมือนกับ backend (Supabase Transaction pooler)
    EE_SERVICE_ACCOUNT_KEY — เนื้อหา JSON เต็มของ GEE service account (ดู pipeline/gee_init.py)
"""
import datetime
import sys

import db
import gee_init
from landcover import compute_landcover_breakdown
from rainfall_et0 import compute_monthly_et0, compute_monthly_rainfall
from rice_paddy import compute_rice_paddy_area_rai

import ee


def resolve_target_year_month(argv: list[str]) -> tuple[int, int]:
    if len(argv) >= 3:
        return int(argv[1]), int(argv[2])
    today = datetime.date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1  # เดือนก่อนหน้า — ข้อมูลดาวเทียมเดือนปัจจุบันอาจยังไม่ครบ


def run_for_tambon(conn, tambon: dict, year: int, month: int) -> None:
    tambon_id = tambon["tambon_id"]
    month_date = f"{year}-{month:02d}-01"

    if tambon["geom_geojson"] is None:
        print(f"  [ข้าม] {tambon['name_th']}: ยังไม่มี geometry ในฐานข้อมูล")
        return

    tambon_geom = ee.Geometry(tambon["geom_geojson"])

    print(f"  ฝน/ET0 ระดับตำบล ({tambon['name_th']})...")
    rainfall_mm = compute_monthly_rainfall(tambon_geom, year, month)
    et0_mm = compute_monthly_et0(tambon_geom, year, month)
    db.upsert_rainfall_monthly(conn, tambon_id, month_date, rainfall_mm)
    db.upsert_et0_monthly(conn, tambon_id, month_date, et0_mm)
    print(f"    rainfall_mm={rainfall_mm}  et0_mm={et0_mm}")

    villages = db.fetch_villages(conn, tambon_id)
    print(f"  {len(villages)} หมู่บ้าน — land cover + นาข้าว รายหมู่บ้าน...")
    for village in villages:
        village_id = village["village_id"]
        geom_geojson = village["geom_geojson"]
        if geom_geojson is None:
            print(f"    [ข้าม] {village['name_th']}: ไม่มี geometry")
            continue

        landcover = compute_landcover_breakdown(geom_geojson)
        if landcover:
            db.upsert_zone_landcover_monthly(
                conn, village_id, month_date,
                landcover["forest_pct"], landcover["agri_pct"], landcover["residential_pct"],
                landcover["runoff_coefficient"],
            )

        village_geom = ee.Geometry(geom_geojson)
        paddy_rai = compute_rice_paddy_area_rai(village_geom, year, month)
        db.upsert_rice_paddy_monthly(conn, village_id, month_date, paddy_rai)

        print(f"    {village['name_th']}: runoff_c={landcover['runoff_coefficient'] if landcover else None} "
              f"paddy_rai={paddy_rai}")

    conn.commit()


def main():
    year, month = resolve_target_year_month(sys.argv)
    print(f"=== GEE monthly pipeline: {year}-{month:02d} ===")

    gee_init.init_earth_engine()

    conn = db.get_conn()
    try:
        tambons = db.fetch_tambons(conn)
        print(f"พบ {len(tambons)} ตำบลในระบบ")
        for tambon in tambons:
            print(f"--- {tambon['name_th']} ---")
            run_for_tambon(conn, tambon, year, month)
    finally:
        conn.close()

    print("=== เสร็จสิ้น ===")


if __name__ == "__main__":
    main()
