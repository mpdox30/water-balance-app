"""
main.py — Backend API ของระบบสมดุลน้ำชุมชนระดับตำบล (FastAPI)

สถานะ: Phase 1 — CRUD endpoints พื้นฐาน (/tambons, /villages, /water-sources,
/crop-reports, /livestock-reports) + auth ขั้นต่ำ (admin / village_rep) ตาม
00_docs/01-phased-work-plan.md — endpoint จริงอยู่ใน routes.py

Deploy: Render Free Web Service, root directory = backend, start command:
    uvicorn main:app --host 0.0.0.0 --port $PORT

Environment variables ที่ต้องตั้งใน Render:
    DATABASE_URL = connection string จาก Supabase (Project Settings → Database →
                   Connection string → "Transaction pooler" เพื่อให้ใช้กับ serverless/
                   free-tier ได้โดยไม่ชนขีดจำกัด connection)
    SECRET_KEY   = string สุ่มยาวๆ สำหรับเซ็นชื่อ JWT (ห้ามใช้ค่าเดียวกับที่อื่น, ห้าม commit)
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routes import router as api_router

app = FastAPI(
    title="ระบบสมดุลน้ำชุมชนระดับตำบล — API",
    description="Phase 1 — ดู 00_docs/01-phased-work-plan.md",
    version="0.1.0",
)

# เปิด CORS กว้างไว้ก่อน (frontend ยังเป็น static placeholder บน GitHub Pages, ไม่มี cookie/session) —
# ปรับจำกัดเฉพาะ origin ของ GitHub Pages จริงได้ใน Phase 6 ตอนทำ dashboard จริงถ้าต้องการเข้มขึ้น
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def root():
    return {"service": "water-balance-app backend", "status": "ok", "phase": 0}


@app.get("/health")
def health():
    """เช็คว่า backend ต่อ Supabase (DATABASE_URL) ได้จริงไหม — ใช้ยืนยันเกณฑ์ผ่านของ Phase 0
    ("deploy Hello World ได้จริง") โดยไม่ query ตารางจริงใดๆ (แค่ SELECT 1)"""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not set")
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
        return {"database": "connected"}
    except Exception as exc:  # noqa: BLE001 — health check ต้อง surface error ดิบให้เห็นตรงๆ
        raise HTTPException(status_code=500, detail=f"database connection failed: {exc}") from exc
