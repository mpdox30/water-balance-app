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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes import router as api_router

app = FastAPI(
    title="ระบบสมดุลน้ำชุมชนระดับตำบล — API",
    description="Phase 1 — ดู 00_docs/01-phased-work-plan.md",
    version="0.1.0",
)

# เปิด CORS กว้างไว้ก่อน (frontend ยังเป็น static placeholder บน GitHub Pages, ไม่มี cookie/session) —
# ปรับจำกัดเฉพาะ origin ของ GitHub Pages จริงได้ใน Phase 6 ตอนทำ dashboard จริงถ้าต้องการเข้มขึ้น
#
# allow_methods ต้องตรงกับ HTTP method ทั้งหมดที่ routes.py ใช้จริง — เดิมมีแค่ GET/POST ทำให้ตอนเพิ่ม
# PATCH /villages/{id} และ PUT /water-sources/{id}/village-usage ทีหลัง (ทั้งคู่แก้ข้อมูลที่มีอยู่แล้ว)
# ถูก browser บล็อกตั้งแต่ CORS preflight (ก่อนคำขอจริงจะถูกส่งไปหา backend เลยด้วยซ้ำ) เห็นแค่ "Failed
# to fetch" เฉยๆ ไม่มี error message จาก backend ให้เห็น (อาการเดียวกับที่ unhandled_exception_handler
# ด้านล่างอธิบายไว้ — CORS header หายไปจาก response แล้ว browser ไม่ยอมให้ frontend เห็น response เลย)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """ดัก unhandled exception ทุกตัว (เช่น Postgres/PostGIS reject insert เพราะ geometry ผิด
    dimension) ให้ตอบกลับเป็น JSON พร้อม error message จริง แทนที่จะปล่อยให้หลุดไปเป็น "Failed to
    fetch" เฉยๆ ฝั่ง frontend

    ข้อควรระวังสำคัญ (แก้ไขเมื่อเจอ CORS error ซ้ำๆ ทั้งที่ deploy allow_methods ครบแล้ว — Phase 6):
    handler ที่ผูกกับ `Exception` แบบนี้ Starlette เอาไปผูกเป็น `handler` ของ ServerErrorMiddleware
    โดยเฉพาะ (ดู Starlette source: applications.py -> build_middleware_stack — ถ้า key เป็น
    Exception หรือ 500 จะไม่เอาไปใส่ใน ExceptionMiddleware ตามปกติ) และ ServerErrorMiddleware ถูก
    ครอบอยู่ "รอบนอกสุด" ของ middleware stack ทั้งหมด รวมถึงอยู่นอก CORSMiddleware ที่เรา
    app.add_middleware ไว้ด้านบนด้วย!

    เท่ากับว่า "ไม่ว่าจะมี handler ตัวนี้หรือไม่" response ที่มาจากตรงนี้ก็ไม่เคยผ่าน CORSMiddleware
    เลยสักครั้ง (เข้าใจผิดมาตลอดว่ามี handler แล้วจะปลอดภัย) — ต้อง set Access-Control-Allow-Origin
    เองตรงนี้ตรงๆ ถึงจะให้ browser (frontend บน GitHub Pages) อ่าน response นี้ได้ ไม่งั้น browser
    จะรายงานเป็น "blocked by CORS policy: No 'Access-Control-Allow-Origin' header" ทับ error จริง
    จนมองไม่เห็นว่า backend ตอบ 500 มาแล้วพร้อมเหตุผลชัดเจน (เจอเคสนี้ตรงๆ ตอน PUT
    /water-sources/{id}/village-usage ล้มเหลว — status จริงคือ 500 แต่ browser เห็นแค่ CORS block)

    การมี handler ระดับ Exception ที่ FastAPI/Starlette เจาะจงกว่านี้ (เช่น HTTPException) จะยังถูก
    เลือกใช้ก่อนเสมอ (เดินตาม MRO ของ exception class, และ HTTPException ยังคงถูกจัดการผ่าน
    ExceptionMiddleware ที่อยู่ "ใน" CORSMiddleware ตามปกติ ไม่ได้รับผลกระทบจากเรื่องนี้) endpoint
    ที่ raise HTTPException เองจึงทำงานเหมือนเดิมทุกประการ — handler นี้ดักเฉพาะ exception ที่
    "ไม่ได้ตั้งใจ" เท่านั้น"""
    origin = request.headers.get("origin")
    headers = {"Access-Control-Allow-Origin": origin} if origin else {}
    return JSONResponse(
        status_code=500,
        content={"detail": f"เกิดข้อผิดพลาดที่ไม่คาดคิดฝั่งเซิร์ฟเวอร์: {exc}"},
        headers=headers,
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
