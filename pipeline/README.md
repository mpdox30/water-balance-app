# pipeline/

โค้ด GEE pipeline รายเดือน (ฝน CHIRPS / ET0 MODIS / land cover Sentinel-2 / นาข้าว Sentinel-1 SAR)
— งานของ **Phase 2** ตาม `00_docs/01-phased-work-plan.md` ยังไม่เริ่มเขียน ณ ตอนนี้ (Phase 0)

ของเดิมที่มีอยู่แล้วและควรต่อยอด (อย่าเริ่มใหม่จากศูนย์):

- `03_legacy_prototype/gee_pipeline.py` — GEE data extraction เดิม
- `03_legacy_prototype/Final/crop_water_demand.py` — FAO-56 (ET0 × Kc) ที่ใช้อยู่แล้ว
- `01_raw_data/อ่างเก็บน้ำ/reference/` — สูตร inflow, weir constants, monthly evap norm (สำหรับคำนวณ
  `stored_capacity_m3` ของอ่างเก็บน้ำ 5 แห่งที่ seed ไว้แบบ NULL ใน Phase 0 — ดู `capacity_source_note`
  ของแต่ละแถวใน `water_storage_sources`)

สิ่งที่ต้องเพิ่มใหม่ใน Phase 2 (ยังไม่มีในของเดิม):

- Sentinel-2 land cover classification → runoff coefficient ถ่วงน้ำหนัก (เขียนเข้า `zone_landcover_monthly`)
  แทนค่าคงที่ 0.3 เดิม (ดู `00_docs/00-system-design-reset.md` ข้อ 2.1)
- Wiring เขียนผลลัพธ์เข้า Supabase (ผ่าน backend API หรือ direct DB write — ตัดสินใจตอน Phase 2)

ผลลัพธ์ GeoJSON ที่แปลงไว้แล้วจาก Phase 0 (ขอบเขตตำบล/หมู่บ้าน/โซนเกษตร/อ่างเก็บน้ำ) อยู่ที่
`pipeline/data/geo/` — ดู `data/geo/README.md`
