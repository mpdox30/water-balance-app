"""
db.py — เชื่อมต่อ Postgres (Supabase) แบบ per-request connection ผ่าน psycopg

Phase 1 ยังใช้ connection ต่อ request เดียวกับที่ /health ใน main.py ทำอยู่แล้ว (ไม่เปิด
connection pool เพิ่มความซับซ้อน) เพราะ:
1. ใช้ Supavisor "Transaction pooler" ของ Supabase อยู่แล้ว ซึ่งทำ pooling ระดับ proxy ให้
2. Traffic ของ pilot ตำบลเดียวต่ำมาก (ไม่กี่ผู้ใช้) — ยังไม่คุ้มความซับซ้อนของ pool ในโค้ด
ถ้า Phase 2+ ขยายหลายตำบลแล้วเห็น latency จาก connection overhead ค่อยเปลี่ยนเป็น psycopg_pool
"""
import os

import psycopg
from psycopg.rows import dict_row


def get_conn():
    """คืน psycopg connection ใหม่ (dict_row เพื่อให้ query คืนค่าเป็น dict อ่านง่าย)"""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row)
