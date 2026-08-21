# pipeline/

โค้ด GEE pipeline รายเดือน (ฝน CHIRPS / ET0 MODIS / land cover / นาข้าว Sentinel-1 SAR) — **Phase 2
เขียนเสร็จแล้ว** ตาม `00_docs/01-phased-work-plan.md` ยังไม่ได้ทดสอบกับ GEE credential จริง (รอ
`EE_SERVICE_ACCOUNT_KEY` — ดู README หลักของ repo)

## โครงสร้าง

```
db.py              เชื่อม Supabase (fetch tambon/village geometry, upsert ผลลัพธ์)
gee_init.py         เริ่ม Earth Engine session จาก service account credential
rainfall_et0.py      ฝน (CHIRPS) + ET0 (MOD16A2) ระดับตำบล — ต่อยอดจาก 03_legacy_prototype/gee_pipeline.py
landcover.py         สัดส่วนการใช้ที่ดิน + runoff coefficient ระดับหมู่บ้าน — ใหม่ทั้งหมด (ดูรายละเอียดในไฟล์)
rice_paddy.py        พื้นที่นาข้าว (สัญญาณน้ำขัง Sentinel-1) ระดับหมู่บ้าน — ต่อยอดจาก gee_pipeline.py
run_monthly.py        orchestrator หลัก — รันทุกตำบล x ทุกหมู่บ้าน เขียนผลเข้า Supabase
data/geo/             ไฟล์ GeoJSON อ้างอิง (ขอบเขต/โซนเกษตร/อ่างเก็บน้ำ/การใช้ที่ดิน) — ดู data/geo/README.md
```

**ที่มา/ของเดิมที่ต่อยอด:**
- `03_legacy_prototype/gee_pipeline.py` — โครง CHIRPS/MOD16A2/Sentinel-1 เดิม (ปรับจาก
  "ต่อหมู่บ้าน" เป็น "ต่อตำบล" สำหรับฝน/ET0 ให้ตรงกับ schema จริง — ดู rainfall_et0.py หัวไฟล์)
- `03_legacy_prototype/Final/crop_water_demand.py` — FAO-56 (ET0 × Kc) **ยังไม่ได้ใช้ใน Phase 2**
  เพราะเป็นงานของ Phase 5 (Balance engine) ไม่ใช่ pipeline remote-sensing — ดู
  `00_docs/01-phased-work-plan.md` การแบ่งเฟส
- `01_raw_data/อ่างเก็บน้ำ/reference/` — สูตร inflow, weir constants (สำหรับคำนวณ `stored_capacity_m3`
  ของอ่างเก็บน้ำ 5 แห่งที่ seed ไว้แบบ NULL ใน Phase 0 — ยังไม่ได้ใช้)

**สิ่งที่เพิ่มใหม่ใน Phase 2 (ไม่มีในของเดิม):**
- `landcover.py` — คำนวณ runoff coefficient ถ่วงน้ำหนักจากข้อมูลการใช้ที่ดินจริงต่อหมู่บ้าน
  (`data/geo/landuse_maenaruea_2566.geojson`) แทนค่าคงที่ 0.3 เดิม — **ใช้ shapely คำนวณ geometry
  ล้วนๆ ไม่ได้เรียก Earth Engine** เพราะข้อมูลการใช้ที่ดินทางการที่พบระหว่างทำ (จาก D:\WMB_NEW)
  แม่นยำกว่า Sentinel-2 classification ที่วางแผนไว้ตอนแรกมาก (ตรวจสอบไขว้กับพื้นที่ตำบลทางการแล้ว
  คลาดเคลื่อนแค่ 0.06%) — ดูรายละเอียดเต็มใน `landcover.py` หัวไฟล์ และที่มาข้อมูลใน
  `04_scripts/extract_landuse_maenaruea.py`
- `run_monthly.py` — wiring เขียนผลลัพธ์เข้า Supabase โดยตรง (ไม่ผ่าน backend API เพราะรันเป็น
  cron job ไม่ใช่ user request)

ผลลัพธ์ GeoJSON ที่แปลงไว้แล้วจาก Phase 0 (ขอบเขตตำบล/หมู่บ้าน/โซนเกษตร/อ่างเก็บน้ำ) + ข้อมูลการใช้ที่ดิน
ใหม่จาก Phase 2 อยู่ที่ `pipeline/data/geo/` — ดู `data/geo/README.md`

## ทดสอบ manual ก่อนเปิด cron

ยังไม่มี GEE credential ให้ทดสอบจริง (รอ `EE_SERVICE_ACCOUNT_KEY`) — ทดสอบ logic ทั้งหมดที่ไม่พึ่ง
Earth Engine (DB read/write, land cover computation) ผ่าน mock แล้วก่อนส่งมอบ เมื่อมี credential แล้ว
รันทดสอบจริงได้ผ่าน GitHub Actions → gee-pipeline.yml → Run workflow (workflow_dispatch) ก่อนเปิด
`schedule:` ในไฟล์นั้น
