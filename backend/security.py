"""
security.py — auth ขั้นต่ำตาม Phase 1 (01-phased-work-plan.md):
"admin กับตัวแทนหมู่บ้าน (แยกสิทธิ์ — ตัวแทนหมู่บ้านแก้ได้แค่ข้อมูลหมู่บ้านตัวเอง)"

ออกแบบ:
- รหัสผ่านเก็บเป็น bcrypt hash เท่านั้น (ตาราง users, ไม่มี endpoint ไหน return password_hash)
- Login ได้ JWT อายุ 30 วัน (village_rep กรอกฟอร์มแค่เดือนละครั้ง ไม่อยากให้ต้อง login ถี่)
- SECRET_KEY เซ็นชื่อ JWT ต้องตั้งเป็น env var บน Render (ไม่ commit ลง repo)
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

_bearer_scheme = HTTPBearer(auto_error=False)


def _secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if not key:
        raise RuntimeError("SECRET_KEY is not set")
    return key


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # password_hash เสียรูปแบบ (ไม่ควรเกิดถ้าสร้างผ่าน hash_password เสมอ)
        return False


def create_access_token(user: dict) -> str:
    """user ต้องมี keys: user_id, username, role, village_id (village_id เป็น None ได้ถ้า admin)"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["user_id"]),
        "username": user["username"],
        "role": user["role"],
        "village_id": str(user["village_id"]) if user["village_id"] else None,
        "iat": now,
        "exp": now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency — decode JWT จาก Authorization: Bearer <token>"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = decode_access_token(credentials.credentials)
    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "role": payload["role"],
        "village_id": payload.get("village_id"),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")
    return user


def check_can_write_village(user: dict, village_id: str) -> None:
    """เรียกจากในตัว endpoint (ไม่ใช่ Depends) เพราะ village_id มาจาก request body ไม่ใช่ path —
    ใช้กับ POST /crop-reports, /livestock-reports: admin เขียนหมู่บ้านไหนก็ได้,
    village_rep เขียนได้แค่ village_id ของตัวเอง"""
    if user["role"] == "admin":
        return
    if user["role"] == "village_rep" and user["village_id"] == str(village_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="village_rep แก้ได้แค่ข้อมูลหมู่บ้านตัวเอง",
    )
