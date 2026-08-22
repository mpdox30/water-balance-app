# water-balance-app

ระบบสมดุลน้ำชุมชนระดับตำบล — พื้นที่นำร่อง ต.แม่นาเรือ อ.เมืองพะเยา จ.พะเยา

เอกสารออกแบบเต็ม/แผนงานแยกเฟส อยู่ที่ `00_docs/` ในโฟลเดอร์ทำงานหลัก (`D:\AI\Water_balance\00_docs\`)
ไม่ได้อยู่ใน repo นี้ — repo นี้มีเฉพาะโค้ด production ตามข้อกำหนดโปรเจกต์ (ดู
`00-system-design-reset.md` ข้อ 9)

## โครงสร้าง

```
backend/     FastAPI — deploy บน Render Free Web Service (root directory = backend)
             + data/thai_admin/ (ขอบเขตตำบลทั้งประเทศ, แปลงล่วงหน้าแล้ว — ดู Phase 3)
frontend/    Static site — deploy บน GitHub Pages (source = GitHub Actions)
             login.html / admin-setup.html (Phase 3) / report.html (Phase 4) + js/, css/, data/
             (admin_boundary_lookup.json)
pipeline/    GEE pipeline รายเดือน (Phase 2 — เขียนเสร็จแล้ว) + data/geo/ (GeoJSON อ้างอิงทั้งหมด)
.github/workflows/   deploy-pages.yml (auto), gee-pipeline.yml (manual + cron รายเดือน — เปิดแล้ว)
```

## สถานะปัจจุบัน: Phase 4

**Phase 4 — ฟอร์มรายงานพืช/ปศุสัตว์รายเดือน (โค้ดเขียนเสร็จ ยังไม่ได้ทดสอบผ่านเบราว์เซอร์จริง):**
- [x] `frontend/report.html` + `frontend/js/report.js` — ฟอร์มมือถือสั้นให้ตัวแทนหมู่บ้านกรอกพืชที่ปลูก
      + จำนวนปศุสัตว์รายเดือน ไม่มี dropdown เลือกพื้นที่ (ผูก village_id อัตโนมัติจาก JWT ตอน login)
- [x] `auth.js`: เพิ่ม `requireAuth()` (login แล้วใช้ได้ทั้ง admin/village_rep ต่างจาก `requireAdmin()`
      เดิมที่ใช้เฉพาะ admin-setup.html) — admin login เข้าหน้านี้ได้เหมือนกัน (backend อนุญาตอยู่แล้ว)
      จึงเปิดช่องเลือกตำบล/หมู่บ้านให้ admin ทดสอบฟอร์มเองได้ทันที **โดยยังไม่ต้องสร้างบัญชี village_rep จริง**
      (ตามที่ตกลงกันไว้ — เรื่องบัญชีตัวแทนหมู่บ้านจริงค่อยว่ากันทีหลัง)
- [x] Validation กันข้อมูลซ้ำ: backend ยังไม่มี endpoint แก้ไข/ลบรายงาน (มีแค่สร้างใหม่) จึง **block**
      ไม่ให้ส่งพืช/ปศุสัตว์ชนิดเดียวกันซ้ำในเดือนเดียวกัน (ต้องติดต่อ admin ถ้ากรอกผิดจริง) — ต่างจาก Phase 3
      ที่ validation ขอบเขต geometry เป็นแค่ soft-warning เพราะอันนั้นวัดพื้นที่คลาดเคลื่อนได้เองตามธรรมชาติ
      แต่พื้นที่ปลูกรวมต้องไม่เกินพื้นที่เกษตรทั้งหมู่บ้าน (`agri_rai`) เป็นกฎเลขคณิตตรงไปตรงมา จึง block จริง
- [ ] **ต้องทำเอง:** ยังไม่ได้ทดสอบฟอร์มนี้ผ่านเบราว์เซอร์จริง — ลอง login ด้วยบัญชี admin เข้า `report.html`
      แล้วเลือกตำบล/หมู่บ้าน (เช่น นครป่าหมาก หรือแม่นาเรือ) กรอกพืช/ปศุสัตว์สักหมู่บ้านก่อน แล้วตรวจสอบใน
      Supabase ว่าค่าถูกต้อง — เมื่อพร้อมสร้างบัญชี village_rep จริงค่อยแจ้งเพื่อสร้างบัญชีให้ตัวแทนแต่ละหมู่บ้าน
      (ดูตัวอย่างคำสั่งสร้างบัญชีใน "ทดสอบ API ผ่าน curl" ด้านล่าง)

## สถานะเดิม: Phase 3

**Phase 3 — เพิ่มใหม่ (โค้ดเขียนเสร็จ ทดสอบ backend end-to-end กับ Postgres+PostGIS จริง (local)
ด้วย "ตำบลสมมติ" (ด่านคล้า อ.โนนสูง จ.นครราชสีมา — ไม่ใช่แม่นาเรือ) ผ่านครบทุกขั้นตอนแล้ว
ยังไม่ได้ทดสอบผ่านหน้าเว็บจริงบน URL ที่ deploy แล้ว — ดู "ต้องทำเอง" ด้านล่าง):**
- [x] `backend/thai_admin_boundary.py` + `backend/data/thai_admin/thai_tambon_geometry.json.gz` —
      ขอบเขตตำบลทั้งประเทศ 8,105 ตำบล (แปลง UTM47N→WGS84 + simplify ~30m + gzip ล่วงหน้าจาก
      `THA_Tambon.shp` ล่วงหน้าแล้ว ไม่ต้องพึ่ง pyshp/pyproj/shapely ตอน deploy จริง — ดูเหตุผลเต็มใน
      หัวไฟล์ `thai_admin_boundary.py` และ `04_scripts/extract_thai_tambon_geometry.py`)
- [x] Endpoint ใหม่: `POST /admin/thai-tambon-lookup` (admin เท่านั้น — หา geometry จากชื่อจังหวัด/
      อำเภอ/ตำบลที่ต้องมาจาก dropdown เท่านั้น, 404 ถ้าไม่ตรงรายชื่อจริง), `POST /village-boundary-parts`
      + `GET /village-boundary-parts` (admin เท่านั้น — geometry ต้องมาจากการวาดบนแผนที่เท่านั้น)
- [x] `frontend/login.html` — หน้า login จริง (เรียก `POST /auth/login`, เก็บ JWT ใน localStorage)
      แทนวิธี manual token เดิม
- [x] `frontend/admin-setup.html` — wizard เพิ่มตำบลใหม่แบบเต็ม (ไม่จำกัดแค่แม่นาเรือ):
      dropdown จังหวัด→อำเภอ→ตำบล (ผูก `admin_boundary_lookup.json`) → โหลด/ยืนยันขอบเขตจากฐานข้อมูล
      กลาง → เพิ่มหมู่บ้าน + วาดขอบเขตด้วย Leaflet.draw → ปักหมุดแหล่งน้ำด้วยการคลิกแผนที่ —
      **ไม่มีช่องพิมพ์พิกัด/พื้นที่อิสระที่ไหนเลย** ตามเกณฑ์ผ่าน Phase 3
- [x] ทดสอบ backend ผ่าน `FastAPI TestClient` กับ Postgres+PostGIS จริง (local): lookup ตำบลสมมติ →
      สร้างตำบล → สร้างหมู่บ้าน → วาดขอบเขตหมู่บ้าน (คำนวณไร่จาก PostGIS จริง) → ปักหมุดแหล่งน้ำ →
      ยืนยันสิทธิ์ (village_rep โดน 403 ทุก endpoint ที่เป็นของ admin) — ผ่านหมดทุกเคส
- [x] **ทดสอบผ่านเบราว์เซอร์จริงบน production แล้ว** (2026-08-22): สร้างตำบลนครป่าหมาก
      (อ.บางกระทุ่ม จ.พิษณุโลก — ไม่ใช่แม่นาเรือ) ผ่านหน้า `admin-setup.html` จริงครบทุกขั้นตอน
      (ดึงขอบเขตจากฐานข้อมูลกลาง → ยืนยันสร้างตำบล → เพิ่มหมู่บ้านจริงครบ 13 หมู่ → ปักหมุดแหล่งน้ำ
      2 จุด) ตรวจสอบข้อมูลใน Supabase แล้วถูกต้องครบทุกจุด — **Phase 3 ผ่านเกณฑ์เต็มรูปแบบ**

**เพิ่มเติมหลัง Phase 3 ผ่านเกณฑ์ (อัปโหลดไฟล์ขอบเขต/แหล่งน้ำ):**
- [x] `frontend/js/geo-upload.js` — parse ไฟล์ Shapefile (.zip ผ่าน shpjs, แปลง CRS ให้อัตโนมัติ) /
      GeoJSON / KML (ผ่าน @tmcw/togeojson) ทั้งหมดฝั่ง client ไม่ผ่าน backend เลย (endpoint เดิมรับ
      geometry/lat-lon ที่เป็น WGS84 อยู่แล้ว ไม่ต้องเพิ่ม dependency ฝั่ง backend)
- [x] หน้า admin-setup: อัปโหลดขอบเขตตำบลเองแทนการดึงจากฐานข้อมูลกลางได้ (พร้อม sanity check เทียบ
      พื้นที่กับค่าทางการ), อัปโหลดขอบเขตหมู่บ้านทั้งตำบลจากไฟล์เดียว (จับคู่กับหมู่บ้านอัตโนมัติจาก
      field หมู่ที่/ชื่อในไฟล์ + ให้ยืนยัน/แก้เอง), อัปโหลดตำแหน่ง+รายละเอียดแหล่งน้ำจากไฟล์ — ทุกจุด
      ยังเป็นไฟล์ GIS จริง ไม่ใช่ช่องพิมพ์พิกัด/พื้นที่อิสระ ไม่ขัดเกณฑ์ผ่าน Phase 3
- [x] ใช้ Turf.js เตือน (ไม่ block) เมื่อขอบเขตหมู่บ้านที่วาด/อัปโหลดล้นนอกตำบล หรือทับกับหมู่บ้านอื่น
      เกิน 15% ของพื้นที่ — เป็นการเตือนเฉยๆ เพราะข้อมูล GIS จริงมักมีส่วนต่างเล็กน้อยตามธรรมชาติ
      (เช่น ขอบเขตตำบลกลาง simplify ไว้ ~30 เมตร)
- [x] สลับแผนที่ถนน/ภาพถ่ายดาวเทียมได้ (Esri World Imagery) บนแผนที่ปักหมุด
- [ ] **ต้องทำเอง:** ยังไม่ได้ทดสอบฟีเจอร์อัปโหลด 3 จุดนี้ผ่านเบราว์เซอร์จริง (ทดสอบแค่ syntax +
      โครงสร้าง HTML/matching backend endpoint เดิมที่ผ่านการทดสอบแล้ว) — ทดสอบด้วยไฟล์ .zip/.geojson/
      .kml จริงสักไฟล์ก่อนใช้งานจริงกับตำบลอื่นต่อไป

## Phase 2 (เสร็จแล้ว)
- [x] `pipeline/rainfall_et0.py` — ฝน (CHIRPS) + ET0 (MOD16A2) ระดับตำบล ต่อยอดจาก
      `03_legacy_prototype/gee_pipeline.py`
- [x] `pipeline/landcover.py` — runoff coefficient ถ่วงน้ำหนักจากข้อมูลการใช้ที่ดินทางการปี 2566
      (**เปลี่ยนจากแผนเดิมที่จะใช้ Sentinel-2 classification** — เจอข้อมูลทางการที่แม่นยำกว่าระหว่างทำ
      ดูเหตุผลเต็มใน `pipeline/landcover.py` หัวไฟล์)
- [x] `pipeline/rice_paddy.py` — พื้นที่นาข้าว (Sentinel-1 SAR) ระดับหมู่บ้าน ต่อยอดจากโค้ดเดิม
- [x] `pipeline/run_monthly.py` — orchestrator เขียนผลเข้า Supabase โดยตรงทุกตำบล/หมู่บ้าน
- [x] `.github/workflows/gee-pipeline.yml` — พร้อมรัน manual (workflow_dispatch) แล้ว cron ยังปิดอยู่
      โดยตั้งใจจนกว่าจะทดสอบ manual ผ่าน 1 รอบก่อน (ตามเกณฑ์ผ่าน Phase 2)
- [ ] **ต้องทำเอง:** ตั้ง GitHub Secret 2 ตัว (`EE_SERVICE_ACCOUNT_KEY`, `DATABASE_URL`) แล้วรัน
      workflow ด้วยมือ 1 ครั้งเพื่อยืนยัน ก่อนเปิด `schedule:` — ดูรายละเอียดในแชท

## Phase 1 (เสร็จแล้ว)

Phase 0 ผ่านครบแล้ว (repo/Supabase/Render/GitHub Pages เชื่อมกัน + seed ข้อมูลจริง) กำลังอยู่ระหว่าง
Phase 1 — Data model + Backend API ขั้นต่ำ ตาม `01-phased-work-plan.md`

**Phase 0:**
- [x] Supabase project สร้างแล้ว, เปิด extension `postgis` แล้ว
- [x] Schema เต็ม (6-tier data model) apply แล้ว — ดู `04_scripts/001_init_schema.sql`
- [x] Seed ข้อมูลจริงของ ต.แม่นาเรือแล้ว (18 หมู่บ้าน, สระ 6 + อ่าง 5, ค่าคงที่คำนวณน้ำ) —
      ดู `04_scripts/002_seed_maenaruea.sql`
- [x] แปลง boundary shapefile → GeoJSON แล้ว — ดู `pipeline/data/geo/`
- [x] Repo public, GitHub Pages + Render + Supabase เชื่อมกันครบ, deploy "Hello World" สำเร็จ

**Phase 1 — เพิ่มใหม่:**
- [x] ตาราง `users` (admin / village_rep, bcrypt password hash) — `04_scripts/004_add_users_table.sql`
- [x] Endpoint: `GET/POST /tambons`, `/villages`, `/water-sources`, `/crop-reports`, `/livestock-reports`
- [x] Auth ขั้นต่ำ: `POST /auth/login` (คืน JWT อายุ 30 วัน), `GET /users/me`,
      `POST /users` (admin สร้างบัญชีตัวแทนหมู่บ้าน)
- [x] สิทธิ์: GET เปิดอ่านได้ทุกคน / POST `/tambons`,`/villages`,`/water-sources` admin เท่านั้น /
      POST `/crop-reports`,`/livestock-reports` admin หรือ village_rep ของหมู่บ้านนั้นเท่านั้น
- [x] ทดสอบ end-to-end กับ Postgres+PostGIS จริง (local) ก่อนส่งมอบแล้ว — ดูผลทดสอบใน commit message
- [ ] **ต้องทำเอง:** ตั้ง env var ใหม่บน Render → `SECRET_KEY` (ดูขั้นตอนด้านล่าง) แล้วรอ auto-deploy
      (หรือกด Manual Deploy) จากนั้นทดสอบผ่าน curl/Postman บน URL จริง (ไม่ใช่ localhost)

### ตั้งค่าเพิ่มบน Render สำหรับ Phase 1

Environment → Add Environment Variable:
```
SECRET_KEY = <string สุ่มยาวๆ สำหรับเซ็นชื่อ JWT — ห้ามใช้ค่าเดียวกับที่อื่น>
```
สร้างค่าใหม่เองได้ด้วย `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` — ผมสร้างให้ชุดหนึ่งแล้ว
ส่งในแชทแยกต่างหาก (ไม่ใส่ไว้ในไฟล์นี้เพราะ repo เป็น public แล้ว)

รหัสผ่านบัญชี admin เริ่มต้น (`username: admin`) ก็ส่งในแชทแยกต่างหากด้วยเหตุผลเดียวกัน — ไม่ได้เก็บไว้ที่ไหนในไฟล์เลย
เก็บไว้ในที่ปลอดภัย (เช่น password manager) แล้วอย่า commit ลง repo

### งานที่เหลือจาก Phase 0 (ค้างอยู่)
5. Export GEE credential เดิม (ผูกกับ GCP project `ee-mpdox69`) → เก็บเป็น GitHub Secret ชื่อ
   `EE_SERVICE_ACCOUNT_KEY` (repo Settings → Secrets and variables → Actions → New repository
   secret) — ยังไม่ต้องรีบทำจนกว่าจะถึง Phase 2 ที่ pipeline จริงเขียนเสร็จ

## Push ขึ้น GitHub ครั้งแรก

รันจากเครื่องคุณเอง (ในโฟลเดอร์นี้):

```bash
git init
git add .
git commit -m "Phase 0: scaffold backend/frontend/pipeline + GeoJSON ที่แปลงแล้ว"
git branch -M main
git remote add origin https://github.com/mpdox30/water-balance-app.git
git push -u origin main
```

## รัน backend ในเครื่อง (local dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # แล้วใส่ DATABASE_URL จริงจาก Supabase
uvicorn main:app --reload
```

เปิด `http://localhost:8000/health` — ควรได้ `{"database": "connected"}` ถ้าตั้ง `DATABASE_URL`
ถูกต้อง

## ทดสอบ API ผ่าน curl (Phase 1)

แก้ `<BACKEND_URL>` เป็น URL จริงของ Render (เช่น `https://water-balance-app.onrender.com`)

```bash
# อ่านข้อมูล (ไม่ต้อง login)
curl <BACKEND_URL>/tambons
curl <BACKEND_URL>/villages
curl <BACKEND_URL>/water-sources

# login เป็น admin (รหัสผ่านอยู่ในแชทแยกต่างหาก)
curl -X POST <BACKEND_URL>/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<PASSWORD_จากแชท>"}'
# เก็บ access_token จาก response ไปใช้ต่อ

# admin สร้างบัญชีตัวแทนหมู่บ้าน (แทน <VILLAGE_ID> ด้วย village_id จริงจาก GET /villages)
curl -X POST <BACKEND_URL>/users \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"username":"rep_moo1","password":"ตั้งรหัสผ่านเอง12","role":"village_rep","village_id":"<VILLAGE_ID>","display_name":"ตัวแทนหมู่ 1"}'
```

เอกสาร API แบบ interactive (Swagger UI) ดูได้ที่ `<BACKEND_URL>/docs` เลย ไม่ต้องพิมพ์ curl เองก็ได้

## เกณฑ์ผ่าน Phase 0 (ตาม 01-phased-work-plan.md)

- [x] Repo/Supabase/Render/GitHub Pages เชื่อมกันครบ deploy "Hello World" ได้จริง
- [x] DB มีตำบลแม่นาเรือ + 18 หมู่บ้าน + แหล่งน้ำ 11 แห่ง (สระ 6 + อ่าง 5) พร้อมข้อมูลที่ตรวจสอบแล้วเท่านั้น

## เกณฑ์ผ่าน Phase 1 (ตาม 01-phased-work-plan.md)

- [x] เรียก API ทุกตัวผ่าน Postman/curl ได้จริงบน Render (ยืนยันแล้ว: `/tambons`, `/villages`,
      `/health` ตอบถูกต้องบน URL จริงหลังตั้ง `SECRET_KEY`)
- [x] ข้อมูลที่ seed ไว้ใน Phase 0 อ่านผ่าน API ได้ครบ (ทดสอบแล้ว: 1 ตำบล, 18 หมู่บ้าน, 11 แหล่งน้ำ)

## เกณฑ์ผ่าน Phase 2 (ตาม 01-phased-work-plan.md)

- [x] รัน pipeline ย้อนหลังกับข้อมูลฝนจริงของแม่นาเรือ เทียบผลลัพธ์สมเหตุสมผล — ทดสอบ manual
      (workflow_dispatch) แล้ว 2026-08-21: rainfall_mm=197.4, et0_mm=36.1 (2026-07, สมเหตุสมผลกับ
      ฤดูฝนภาคเหนือ), land cover + rice paddy เขียนครบทั้ง 18 หมู่บ้าน
- [ ] Scheduled workflow รันสำเร็จอัตโนมัติอย่างน้อย 1 รอบเต็มโดยไม่ต้องสั่งมือ — เปิด cron แล้ว
      (ต้นเดือน 08:00 เวลาไทย) รอยืนยันรอบอัตโนมัติแรกต้นเดือนถัดไป

## เกณฑ์ผ่าน Phase 3 (ตาม 01-phased-work-plan.md)

- [x] ไม่มีช่องพิมพ์ข้อความอิสระสำหรับตำแหน่ง/พื้นที่เลย (ตำบล/หมู่บ้าน/แหล่งน้ำ มาจาก dropdown +
      วาด/คลิกบนแผนที่ทั้งหมด)
- [x] ทดสอบกับตำบลสมมติ (ไม่ใช่แม่นาเรือ) ได้จริง — ทดสอบระดับ backend ผ่าน `FastAPI TestClient` แล้ว
      (ด่านคล้า อ.โนนสูง จ.นครราชสีมา) ผ่านครบทุกขั้นตอน (lookup → สร้างตำบล → เพิ่มหมู่บ้าน →
      วาดขอบเขต → ปักหมุดแหล่งน้ำ → ตรวจสิทธิ์)
- [x] ทดสอบผ่านหน้าเว็บจริงบนเบราว์เซอร์ (ไม่ใช่แค่ TestClient) — ทดสอบแล้วกับตำบลนครป่าหมาก
      (อ.บางกระทุ่ม จ.พิษณุโลก) ครบทุกฟีเจอร์รวมอัปโหลดไฟล์ขอบเขต/แหล่งน้ำ ตรวจสอบข้อมูลใน Supabase แล้ว
      ถูกต้องครบทุกจุด (พบ+ลบระเบียนซ้ำที่เกิดจากรอบทดสอบก่อนหน้าออกแล้ว 3 แถว เหลือระเบียนที่ถูกต้อง 1 แถว)

## เกณฑ์ผ่าน Phase 4 (ตาม 01-phased-work-plan.md)

- [ ] ทดสอบกรอกฟอร์มจริงอย่างน้อย 2–3 หมู่บ้านนำร่อง ได้ข้อมูลปศุสัตว์ชุดแรกที่ยืนยันได้ (ไม่ใช่ตัวเลขสมมติ) —
      ทดสอบด้วยบัญชี admin ได้ก่อน (ไม่ต้องรอบัญชี village_rep จริง) ดู "ต้องทำเอง" ด้านบน
