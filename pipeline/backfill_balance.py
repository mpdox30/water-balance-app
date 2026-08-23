# -*- coding: utf-8 -*-
"""
backfill_balance.py — รัน pipeline/balance_engine.py ย้อนหลังหลายเดือนติดกันในคำสั่งเดียว

คู่กับ pipeline/backfill_monthly.py (Phase 2 — ฝน/ET0/land cover/นาข้าว) แต่เป็นคนละ stage: ไฟล์นี้
"คำนวณสมดุลน้ำ" (Phase 5) จากข้อมูลที่มีอยู่แล้วในฐานข้อมูล (rainfall_monthly/et0_monthly ต้องมีอยู่ก่อน
— รันจาก pipeline/backfill_monthly.py หรือ pipeline/run_monthly.py ก่อนเสมอ) — ไม่เรียก Earth Engine
เลย จึงไม่ต้องตั้ง GOOGLE_APPLICATION_CREDENTIALS/EE_SERVICE_ACCOUNT_KEY เหมือน backfill_monthly.py
ต้องการแค่ DATABASE_URL ตัวเดียว

ข้อควรรู้ก่อนรัน (สำคัญ — ไม่ใช่ข้อจำกัดของสคริปต์นี้ แต่เป็นข้อจำกัดของ balance_engine.py เอง):
crop_report/livestock_report ที่ใช้คำนวณ "น้ำเกษตร"/"น้ำปศุสัตว์" ดึงมาจากแถว "ล่าสุด" ต่อหมู่บ้าน
(db.fetch_crop_report_latest — distinct on village_id, crop_name เรียงตาม reported_month ล่าสุด) ไม่ใช่
แถวของเดือนนั้นๆ โดยเฉพาะ เพราะระบบยังไม่มีข้อมูลพืชแยกรายเดือนย้อนหลังจริง (มีแค่ snapshot ล่าสุดที่กรอก/
import ไว้) ผลคือ: พื้นที่ปลูกพืชที่ใช้คำนวณจะเป็น "พื้นที่ปลูกปัจจุบัน" เท่ากันทุกเดือนที่ backfill ย้อนหลัง
มีแค่ ET0 (จาก climate จริงของเดือนนั้น) และ Kc (จาก growth curve ตามเดือนนั้น) เท่านั้นที่ต่างกันไปตามเดือน
— ตัวเลข agri_demand ย้อนหลังจึงเป็น "ถ้าปลูกพื้นที่เท่าปัจจุบันในเดือนนั้นจะใช้น้ำเท่าไหร่" ไม่ใช่ประวัติจริง
ว่าเดือนนั้นปลูกอะไรอยู่จริง — ต้องเข้าใจข้อจำกัดนี้ก่อนอ่านผลย้อนหลังเป็น "ประวัติศาสตร์จริง"

--- การเตรียมเครื่องก่อนรัน (ทำครั้งเดียว ถ้ารันจากเครื่องตัวเอง ไม่ผ่าน GitHub Actions) ---
1. ติดตั้ง dependency: pip install -r pipeline/requirements.txt
2. ตั้ง environment variable ตัวเดียว: DATABASE_URL (ดูค่าได้จาก Render/GitHub Secrets เดิม)

ตัวอย่าง (PowerShell, รันจากโฟลเดอร์ D:\\AI\\Water_balance\\water-balance-app):
    $env:DATABASE_URL = "postgresql://...."
    python pipeline\\backfill_balance.py 2025 6 2026 7

ตัวอย่าง (cmd.exe):
    set DATABASE_URL=postgresql://....
    python pipeline\\backfill_balance.py 2025 6 2026 7

หรือรันผ่าน GitHub Actions workflow "Balance engine (Phase 5)" (.github/workflows/balance-engine.yml)
โดยกรอกช่อง backfill_start/backfill_end แบบเดียวกับที่ใช้กับ "GEE monthly pipeline" — ไม่ต้องตั้งอะไรบน
เครื่องตัวเองเลย เพราะรันบน GitHub-hosted runner ทั้งหมด

การใช้งาน (แบบ CLI ตรง):
    python pipeline/backfill_balance.py <ปีเริ่ม> <เดือนเริ่ม> <ปีสิ้นสุด> <เดือนสิ้นสุด>
    เช่น python pipeline/backfill_balance.py 2025 6 2026 7   # มิ.ย. 2568 ถึง ก.ค. 2569 รวม 14 เดือน

ถ้าเดือน/ตำบลไหนรันพลาด (เช่นยังไม่มี et0_mm ของเดือนนั้นเลยแม้แต่ค่าประมาณการ) จะ log คำเตือนแล้วรันรายการ
ถัดไปต่อ ไม่ทำให้ทั้งชุดหยุด — สรุปท้ายสุดจะบอกว่าเดือน/ตำบลไหนพลาดบ้าง ให้รันคำสั่งเดิมซ้ำได้อีกครั้งภายหลัง
(การเขียนผลเป็น idempotent อยู่แล้ว รันซ้ำเดือนเดิมไม่ทำให้ข้อมูลซ้ำซ้อน — ดู db.write_balance_results)
"""
import sys

import db
from balance_engine import run_for_tambon


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
        print("การใช้งาน: python pipeline/backfill_balance.py <ปีเริ่ม> <เดือนเริ่ม> <ปีสิ้นสุด> <เดือนสิ้นสุด>")
        print("ตัวอย่าง:   python pipeline/backfill_balance.py 2025 6 2026 7")
        sys.exit(1)

    start_year, start_month, end_year, end_month = (int(x) for x in sys.argv[1:5])
    months = list(month_range(start_year, start_month, end_year, end_month))
    if not months:
        print("ช่วงเดือนที่ระบุไม่ถูกต้อง (เดือนสิ้นสุดต้องไม่มาก่อนเดือนเริ่ม)")
        sys.exit(1)

    print(f"=== Backfill สมดุลน้ำย้อนหลัง {len(months)} เดือน: "
          f"{start_year}-{start_month:02d} ถึง {end_year}-{end_month:02d} ===")

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
                except Exception as exc:  # noqa: BLE001 — กันไม่ให้ 1 ตำบล/เดือนพัง ทำให้ทั้งชุดหยุด
                    print(f"  !!! พลาด: {tambon['name_th']} เดือน {year}-{month:02d} — {exc}")
                    failed.append((tambon["name_th"], year, month))
            print()
    finally:
        conn.close()

    print("=== Backfill สมดุลน้ำเสร็จสิ้น ===")
    if failed:
        print(f"มี {len(failed)} รายการที่พลาด — รันคำสั่งเดิมซ้ำได้ภายหลัง (idempotent) "
              f"หรือรันเฉพาะเดือนที่พลาดผ่าน pipeline/balance_engine.py <ปี> <เดือน> ทีละรายการ:")
        for name, y, m in failed:
            print(f"  - {name} {y}-{m:02d}")
        sys.exit(1)
    else:
        print("ทุกเดือน/ทุกตำบลสำเร็จหมด — เช็คผลได้ที่ dashboard หรือ SELECT จากตาราง water_balance_monthly")


if __name__ == "__main__":
    main()
