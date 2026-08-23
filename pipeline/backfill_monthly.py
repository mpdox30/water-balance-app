# -*- coding: utf-8 -*-
"""
backfill_monthly.py — รัน pipeline/run_monthly.py ย้อนหลังหลายเดือนติดกันในคำสั่งเดียว

ใช้ตอน backfill ข้อมูลภูมิอากาศ/land cover/นาข้าวของเดือนเก่าที่ยังไม่เคยรัน — ข้อมูลดาวเทียม (CHIRPS/
MOD16A2/Sentinel-1) มีอยู่แล้วในโลกสำหรับเดือนเหล่านี้ แค่ยังไม่เคยถูกดึงเข้า Supabase เท่านั้น ไม่ใช่การ
ประมาณ/สมมติค่าใดๆ ทั้งสิ้น — เป็นแค่ wrapper ที่เรียก pipeline/run_monthly.py::run_for_tambon() ซ้ำ
หลายรอบต่อกัน โดย init Earth Engine + เปิด DB connection แค่ครั้งเดียวตลอดทั้งชุด (เร็วกว่าเรียก
`python pipeline/run_monthly.py <ปี> <เดือน>` แยกทีละคำสั่ง ที่ต้อง init ใหม่ทุกครั้ง)

วางไฟล์นี้ไว้ในโฟลเดอร์ pipeline/ (เดียวกับ run_monthly.py, db.py, gee_init.py) ก่อนรัน เพราะใช้ import
แบบ same-directory เหมือนไฟล์อื่นๆ ในนั้น

--- การเตรียมเครื่องก่อนรัน (ทำครั้งเดียว) ---
1. ติดตั้ง dependency: pip install -r pipeline/requirements.txt
2. ตั้ง environment variable 2 ตัว (ดูค่าได้จาก Render/GitHub Secrets เดิม หรือ backend/.env.example
   สำหรับ DATABASE_URL — ต้องเป็นตัวเดียวกับที่ backend/pipeline อื่นๆ ใช้อยู่ ไม่ใช่คนละ project):
   - DATABASE_URL                  = connection string ของ Supabase (Transaction pooler)
   - GOOGLE_APPLICATION_CREDENTIALS = path ไปยังไฟล์ JSON ของ GEE service account บนเครื่องนี้
     (ถ้ายังไม่มีไฟล์นี้ในเครื่อง ต้อง export credential เดิมออกมาจากที่เก็บไว้ตอน Phase 0 ก่อน —
     ห้ามสร้าง service account ใหม่เอง เพราะต้องผูกกับ GCP project เดิมที่เปิด Earth Engine API ไว้แล้ว)

ตัวอย่าง (PowerShell, รันจากโฟลเดอร์ D:\\AI\\Water_balance\\water-balance-app):
    $env:DATABASE_URL = "postgresql://...."
    $env:GOOGLE_APPLICATION_CREDENTIALS = "D:\\AI\\Water_balance\\gee-service-account.json"
    python pipeline\\backfill_monthly.py 2025 6 2026 6

ตัวอย่าง (cmd.exe):
    set DATABASE_URL=postgresql://....
    set GOOGLE_APPLICATION_CREDENTIALS=D:\\AI\\Water_balance\\gee-service-account.json
    python pipeline\\backfill_monthly.py 2025 6 2026 6

การใช้งาน:
    python pipeline/backfill_monthly.py <ปีเริ่ม> <เดือนเริ่ม> <ปีสิ้นสุด> <เดือนสิ้นสุด>
    เช่น python pipeline/backfill_monthly.py 2025 6 2026 6   # มิ.ย. 2568 (2025) ถึง มิ.ย. 2569 (2026) รวม 13 เดือน

ถ้าเดือน/ตำบลไหนรันพลาด (เช่น GEE timeout ชั่วคราว, quota ชั่วคราว) จะ log คำเตือนแล้วรันรายการถัดไปต่อ
ไม่ทำให้ทั้งชุดหยุด — สรุปท้ายสุดจะบอกว่าเดือน/ตำบลไหนพลาดบ้าง ให้รันคำสั่งเดิมซ้ำได้อีกครั้งภายหลัง
(การ upsert ในทุกตารางเป็น idempotent อยู่แล้ว รันซ้ำเดือนเดิมไม่ทำให้ข้อมูลซ้ำซ้อน)
"""
import sys

import db
import gee_init
from run_monthly import run_for_tambon


def month_range(start_year: int, start_month: int, end_year: int, end_month: int):
    """คืน (ปี, เดือน) ไล่ทีละเดือนตั้งแต่เดือนเริ่มถึงเดือนสิ้นสุด (รวมทั้งสองปลาย)"""
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    if len(sys.argv) != 5:
        print("การใช้งาน: python pipeline/backfill_monthly.py <ปีเริ่ม> <เดือนเริ่ม> <ปีสิ้นสุด> <เดือนสิ้นสุด>")
        print("ตัวอย่าง:   python pipeline/backfill_monthly.py 2025 6 2026 6")
        sys.exit(1)

    start_year, start_month, end_year, end_month = (int(x) for x in sys.argv[1:5])
    months = list(month_range(start_year, start_month, end_year, end_month))
    if not months:
        print("ช่วงเดือนที่ระบุไม่ถูกต้อง (เดือนสิ้นสุดต้องไม่มาก่อนเดือนเริ่ม)")
        sys.exit(1)

    print(f"=== Backfill ย้อนหลัง {len(months)} เดือน: "
          f"{start_year}-{start_month:02d} ถึง {end_year}-{end_month:02d} ===")

    gee_init.init_earth_engine()
    print("เชื่อมต่อ Earth Engine สำเร็จ")

    conn = db.get_conn()
    failed = []
    try:
        tambons = db.fetch_tambons(conn)
        print(f"พบ {len(tambons)} ตำบลในระบบ\n")

        for year, month in months:
            print(f"--- เดือน {year}-{month:02d} ---")
            for tambon in tambons:
                print(f"  {tambon['name_th']}...")
                try:
                    run_for_tambon(conn, tambon, year, month)
                except Exception as exc:  # noqa: BLE001 — ตั้งใจกันไม่ให้ 1 ตำบล/เดือนพัง ทำให้ทั้งชุดหยุด
                    print(f"  !!! พลาด: {tambon['name_th']} เดือน {year}-{month:02d} — {exc}")
                    failed.append((tambon["name_th"], year, month))
            print()
    finally:
        conn.close()

    print("=== Backfill เสร็จสิ้น ===")
    if failed:
        print(f"มี {len(failed)} รายการที่พลาด — รันคำสั่งเดิมซ้ำได้ภายหลัง (idempotent) "
              f"หรือรันเฉพาะเดือนที่พลาดผ่าน pipeline/run_monthly.py <ปี> <เดือน> ทีละรายการ:")
        for name, y, m in failed:
            print(f"  - {name} {y}-{m:02d}")
        sys.exit(1)
    else:
        print("ทุกเดือน/ทุกตำบลสำเร็จหมด — เช็คผลได้ที่ dashboard หรือ SELECT จากตาราง rainfall_monthly/"
              "et0_monthly/water_balance_monthly")


if __name__ == "__main__":
    main()
