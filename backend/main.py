"""
main.py — Backend API ของระบบสมดุลน้ำชุมชนระดับตำบล (FastAPI)

สถานะ: Phase 0 "Hello World" skeleton เท่านั้น — endpoint จริง (/tambons, /villages,
/water-sources, /crop-reports, /livestock-reports ฯลฯ) จะเพิ่มใน Phase 1 ตาม
00_docs/01-phased-work-plan.md

Deploy: Render Free Web Service, root directory = backend, start command:
    uvicorn main:app --host 0.0.0.0 --port $PORT

Environment variable ที่ต้องตั้งใน Render:
    DATABASE_URL = connection string จาก Supabase (Project Settings → Database →
                   Connection string → "Transaction pooler" เพื่อให้ใช้กับ serverless/
                   free-tier ได้โดยไม่ชนขีดจำกัด connection)
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ระบบสมดุลน้ำชุมชนระดับตำบล — API",
    description="Phase 0 skeleton — ดู 00_docs/01-phased-work-plan.md สำหรับ endpoint ที่จะเพิ่มใน Phase 1",
    version="0.0.1",
)

# เปิด CORS กว้างไว้ก่อนสำหรับ Phase 0 (frontend ยังเป็นแค่ static placeholder) —
# Phase 1 ควรจำกัดเฉพาะ origin ของ GitHub Pages จริง
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
