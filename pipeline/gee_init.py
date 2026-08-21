"""
gee_init.py — เริ่ม session Google Earth Engine จาก service account credential

รองรับ 2 ทาง:
1. EE_SERVICE_ACCOUNT_KEY env var = เนื้อหาไฟล์ JSON ทั้งไฟล์ (ใช้ตอนรันบน GitHub Actions —
   เก็บเป็น GitHub Secret ชื่อนี้ ตามที่ระบุไว้ใน .github/workflows/gee-pipeline.yml)
2. GOOGLE_APPLICATION_CREDENTIALS env var = path ไปยังไฟล์ JSON บนเครื่อง (ใช้ตอน dev ในเครื่อง)

ถ้าไม่มีทั้งสองอย่าง raise error ทันทีพร้อมคำอธิบายชัดเจน (ไม่ fallback ไป interactive
auth เพราะสคริปต์นี้ต้องรันแบบ headless ใน CI ได้)
"""
import json
import os
import tempfile

import ee


def init_earth_engine() -> None:
    key_json = os.environ.get("EE_SERVICE_ACCOUNT_KEY")
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if key_json:
        # เขียนลงไฟล์ชั่วคราวเพราะ ee.ServiceAccountCredentials ต้องการ path ไม่ใช่ string เนื้อหา
        info = json.loads(key_json)  # เช็ค JSON ถูกต้องก่อน — error ชัดเจนกว่าปล่อยให้ ee พังทีหลัง
        service_account_email = info["client_email"]
        gcp_project = info["project_id"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(key_json)
            temp_path = f.name
        credentials = ee.ServiceAccountCredentials(service_account_email, temp_path)
        ee.Initialize(credentials, project=gcp_project)
        return

    if key_file:
        with open(key_file) as f:
            info = json.load(f)
        credentials = ee.ServiceAccountCredentials(info["client_email"], key_file)
        ee.Initialize(credentials, project=info["project_id"])
        return

    raise RuntimeError(
        "ไม่พบ GEE credential — ตั้ง EE_SERVICE_ACCOUNT_KEY (เนื้อหา JSON เต็ม, ใช้บน GitHub Actions) "
        "หรือ GOOGLE_APPLICATION_CREDENTIALS (path ไฟล์, ใช้ตอน dev ในเครื่อง) อย่างใดอย่างหนึ่งก่อนรัน pipeline นี้"
    )
