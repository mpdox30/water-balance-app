# water-balance-app

ระบบสมดุลน้ำชุมชนระดับตำบล — พื้นที่นำร่อง ต.แม่นาเรือ อ.เมืองพะเยา จ.พะเยา

เอกสารออกแบบเต็ม/แผนงานแยกเฟส อยู่ที่ `00_docs/` ในโฟลเดอร์ทำงานหลัก (`D:\AI\Water_balance\00_docs\`)
ไม่ได้อยู่ใน repo นี้ — repo นี้มีเฉพาะโค้ด production ตามข้อกำหนดโปรเจกต์ (ดู
`00-system-design-reset.md` ข้อ 9)

## โครงสร้าง

```
backend/     FastAPI — deploy บน Render Free Web Service (root directory = backend)
frontend/    Static site — deploy บน GitHub Pages (source = GitHub Actions)
pipeline/    GEE pipeline รายเดือน (Phase 2 — เขียนเสร็จแล้ว) + data/geo/ (GeoJSON อ้างอิงทั้งหมด)
.github/workflows/   deploy-pages.yml (auto), gee-pipeline.yml (manual — รอทดสอบ credential จริงก่อนเปิด cron)
```

## สถานะปัจจุบัน: Phase 2

**Phase 2 — เพิ่มใหม่ (โค้ดเขียนเสร็จ ทดสอบ logic ทั้งหมดที่ไม่พึ่ง Earth Engine แล้ว แต่ยังไม่ได้รันกับ
GEE credential จริง — ดู "ต้องทำเอง" ด้านล่าง):**
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

- [ ] รัน pipeline ย้อนหลังกับข้อมูลฝนจริงของแม่นาเรือ เทียบผลลัพธ์สมเหตุสมผล — โค้ดเขียน+ทดสอบ logic
      (DB read/write, land cover) ผ่านหมดแล้วด้วยข้อมูลจริงในเครื่อง แต่ยังไม่เคยรันกับ GEE credential
      จริง (CHIRPS/MOD16A2/Sentinel-1) เพราะยังไม่มี credential ให้ทดสอบ — รอ `EE_SERVICE_ACCOUNT_KEY`
- [ ] Scheduled workflow รันสำเร็จอัตโนมัติอย่างน้อย 1 รอบเต็มโดยไม่ต้องสั่งมือ — cron ปิดอยู่โดยตั้งใจ
      จนกว่าจะทดสอบ manual (workflow_dispatch) ผ่านก่อน
