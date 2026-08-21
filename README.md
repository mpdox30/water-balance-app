# water-balance-app

ระบบสมดุลน้ำชุมชนระดับตำบล — พื้นที่นำร่อง ต.แม่นาเรือ อ.เมืองพะเยา จ.พะเยา

เอกสารออกแบบเต็ม/แผนงานแยกเฟส อยู่ที่ `00_docs/` ในโฟลเดอร์ทำงานหลัก (`D:\AI\Water_balance\00_docs\`)
ไม่ได้อยู่ใน repo นี้ — repo นี้มีเฉพาะโค้ด production ตามข้อกำหนดโปรเจกต์ (ดู
`00-system-design-reset.md` ข้อ 9)

## โครงสร้าง

```
backend/     FastAPI — deploy บน Render Free Web Service (root directory = backend)
frontend/    Static site — deploy บน GitHub Pages (source = GitHub Actions)
pipeline/    GEE pipeline รายเดือน (Phase 2) + data/geo/ (GeoJSON ที่แปลงไว้แล้วจาก Phase 0)
.github/workflows/   deploy-pages.yml (auto), gee-pipeline.yml (manual จนกว่าจะถึง Phase 2)
```

## สถานะปัจจุบัน: Phase 0

ตาม `01-phased-work-plan.md` — โครงสร้างพื้นฐาน + seed ข้อมูลจริงที่ตรวจสอบแล้ว

- [x] Supabase project สร้างแล้ว, เปิด extension `postgis` แล้ว
- [x] Schema เต็ม (6-tier data model) apply แล้ว — ดู `04_scripts/001_init_schema.sql`
- [x] Seed ข้อมูลจริงของ ต.แม่นาเรือแล้ว (18 หมู่บ้าน, สระ 6 + อ่าง 5, ค่าคงที่คำนวณน้ำ) —
      ดู `04_scripts/002_seed_maenaruea.sql`
- [x] แปลง boundary shapefile → GeoJSON แล้ว — ดู `pipeline/data/geo/`
- [ ] **ต้องทำเอง (ทำผ่าน dashboard ของแต่ละบริการ ผมทำให้ไม่ได้เพราะไม่มี credential):**
  1. Push repo นี้ขึ้น GitHub (`mpdox30/water-balance-app`) — ดูขั้นตอนด้านล่าง
  2. เชื่อม Render กับ repo → New Web Service → root directory = `backend` → ตั้ง env var
     `DATABASE_URL` (จาก Supabase: Project Settings → Database → Connection string →
     **Transaction pooler** — สำคัญ: ใช้ pooler ไม่ใช่ direct connection เพราะ Render free tier
     ต่อ connection ตรงจะชนขีดจำกัดของ Supabase free tier ได้ง่าย)
  3. เปิด GitHub Pages: repo Settings → Pages → Source = **GitHub Actions**
     (workflow `deploy-pages.yml` มีอยู่แล้ว จะรันอัตโนมัติเมื่อ push)
  4. แก้ `BACKEND_URL` ใน `frontend/index.html` ให้ตรงกับ URL จริงที่ Render ให้มาหลัง deploy
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

## เกณฑ์ผ่าน Phase 0 (ตาม 01-phased-work-plan.md)

- [ ] Repo/Supabase/Render/GitHub Pages เชื่อมกันครบ deploy "Hello World" ได้จริง — เหลือขั้นตอน
      manual ด้านบน (ข้อ 1-4)
- [x] DB มีตำบลแม่นาเรือ + 18 หมู่บ้าน + แหล่งน้ำ 11 แห่ง (สระ 6 + อ่าง 5) พร้อมข้อมูลที่ตรวจสอบแล้วเท่านั้น
