"""
routes.py — Phase 1 API endpoints (01-phased-work-plan.md ข้อ Phase 1):
GET/POST /tambons, /villages, /water-sources, /crop-reports, /livestock-reports
+ POST /auth/login, POST /users (admin สร้างบัญชีตัวแทนหมู่บ้าน), GET /users/me

หลักการสิทธิ์:
- GET ทุกตัวเปิดอ่านได้โดยไม่ต้อง login (ข้อมูลระดับตำบล/หมู่บ้านไม่ใช่ข้อมูลส่วนบุคคลอ่อนไหว
  และหน้า dashboard/Phase 3 admin-setup ต้องอ่านได้ก่อนมีระบบ login เต็มรูปแบบ)
- POST /tambons, /villages, /water-sources — admin เท่านั้น (งาน setup โครงสร้าง ตาม Phase 3)
- POST /crop-reports, /livestock-reports — admin หรือ village_rep ของหมู่บ้านนั้นเท่านั้น (ตาม Phase 4)
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

import thai_admin_boundary
from db import get_conn
from schemas import (
    BalanceCategoryValue,
    BalanceResponse,
    CropReportBulkRequest,
    CropReportCreateRequest,
    CropReportResponse,
    LivestockReportCreateRequest,
    LivestockReportResponse,
    LoginRequest,
    LoginResponse,
    TambonBalanceOverview,
    TambonCreateRequest,
    TambonResponse,
    ThaiTambonLookupRequest,
    ThaiTambonLookupResponse,
    UserCreateRequest,
    UserResponse,
    VillageBalanceResponse,
    VillageBoundaryPartCreateRequest,
    VillageBoundaryPartResponse,
    VillageCreateRequest,
    VillageResponse,
    VillageUpdateRequest,
    WaterSourceCreateRequest,
    WaterSourceResponse,
    ReservoirVillageUsageReplaceRequest,
    ReservoirVillageUsageResponse,
    CategoryCompleteness,
    DataCompletenessResponse,
    ReservoirCompleteness,
    VillageCompleteness,
)
from security import (
    check_can_write_village,
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)

router = APIRouter()


# ============================================================
# Auth
# ============================================================

@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select user_id, username, password_hash, role, village_id, display_name "
                "from users where username = %s",
                (body.username,),
            )
            row = cur.fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="username หรือ password ไม่ถูกต้อง")
    token = create_access_token(row)
    return LoginResponse(
        access_token=token,
        role=row["role"],
        village_id=str(row["village_id"]) if row["village_id"] else None,
        display_name=row["display_name"],
    )


@router.get("/users/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select user_id, username, role, village_id, display_name from users where user_id = %s",
                (user["user_id"],),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    return _row_to_user(row)


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(body: UserCreateRequest, _admin: dict = Depends(require_admin)):
    """admin สร้างบัญชีตัวแทนหมู่บ้าน (Phase 4) หรือ admin เพิ่มเติม"""
    if body.role == "village_rep" and not body.village_id:
        raise HTTPException(status_code=422, detail="village_rep ต้องระบุ village_id")
    if body.role == "admin" and body.village_id:
        raise HTTPException(status_code=422, detail="admin ต้องไม่ผูก village_id")
    pw_hash = hash_password(body.password)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into users (username, password_hash, role, village_id, display_name) "
                    "values (%s, %s, %s, %s, %s) "
                    "returning user_id, username, role, village_id, display_name",
                    (body.username, pw_hash, body.role, body.village_id, body.display_name),
                )
                row = cur.fetchone()
            conn.commit()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="username นี้มีอยู่แล้ว")
    return _row_to_user(row)


def _row_to_user(row) -> UserResponse:
    return UserResponse(
        user_id=str(row["user_id"]),
        username=row["username"],
        role=row["role"],
        village_id=str(row["village_id"]) if row["village_id"] else None,
        display_name=row["display_name"],
    )


# ============================================================
# Tambons
# ============================================================

_TAMBON_COLS = "tambon_id, name_th, name_en, province_th, amphoe_th, area_km2, area_km2_source, is_pilot"


def _row_to_tambon(row, geom_geojson=None) -> TambonResponse:
    return TambonResponse(
        tambon_id=str(row["tambon_id"]),
        name_th=row["name_th"],
        name_en=row["name_en"],
        province_th=row["province_th"],
        amphoe_th=row["amphoe_th"],
        area_km2=float(row["area_km2"]),
        area_km2_source=row["area_km2_source"],
        is_pilot=row["is_pilot"],
        geom_geojson=geom_geojson,
    )


@router.get("/tambons", response_model=list[TambonResponse])
def list_tambons(is_pilot: bool | None = Query(default=None), geom: bool = Query(default=False)):
    geom_select = ", ST_AsGeoJSON(geom)::json as geom_geojson" if geom else ""
    sql = f"select {_TAMBON_COLS}{geom_select} from tambons"
    params: list = []
    if is_pilot is not None:
        sql += " where is_pilot = %s"
        params.append(is_pilot)
    sql += " order by name_th"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [_row_to_tambon(r, r.get("geom_geojson")) for r in rows]


@router.get("/tambons/{tambon_id}", response_model=TambonResponse)
def get_tambon(tambon_id: str, geom: bool = Query(default=False)):
    geom_select = ", ST_AsGeoJSON(geom)::json as geom_geojson" if geom else ""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_TAMBON_COLS}{geom_select} from tambons where tambon_id = %s", (tambon_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="tambon not found")
    return _row_to_tambon(row, row.get("geom_geojson"))


@router.post("/tambons", response_model=TambonResponse, status_code=201)
def create_tambon(body: TambonCreateRequest, _admin: dict = Depends(require_admin)):
    geom_expr = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)" if body.geom_geojson else "NULL"
    params = [
        body.name_th,
        body.name_en,
        body.province_th,
        body.amphoe_th,
        body.area_km2,
        body.area_km2_source,
        body.is_pilot,
    ]
    if body.geom_geojson:
        params.append(json.dumps(body.geom_geojson))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"insert into tambons (name_th, name_en, province_th, amphoe_th, area_km2, "
                f"area_km2_source, is_pilot, geom) "
                f"values (%s, %s, %s, %s, %s, %s, %s, {geom_expr}) "
                f"returning {_TAMBON_COLS}",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_tambon(row)


# ============================================================
# Thai nationwide admin boundary lookup (Phase 3 — เพิ่มตำบลใหม่นอกแม่นาเรือ)
# ============================================================

@router.post("/admin/thai-tambon-lookup", response_model=ThaiTambonLookupResponse)
def lookup_thai_tambon(body: ThaiTambonLookupRequest, _admin: dict = Depends(require_admin)):
    """หา geometry ตำบลจากฐานข้อมูลทั้งประเทศ (THA_Tambon.shp, ดู thai_admin_boundary.py) —
    ใช้ preview ขอบเขตบนแผนที่ก่อนกด "ยืนยันสร้างตำบล" (ที่จะเรียก POST /tambons ต่อด้วย
    geom_geojson ที่ได้จาก endpoint นี้ — หน้า admin-setup ไม่มีช่องพิมพ์พิกัด/พื้นที่เอง)
    admin-only เพื่อกันการดึงข้อมูลขอบเขตทั้งประเทศไปใช้นอกระบบ (ข้อมูล public แต่ bandwidth เป็นของเรา)"""
    result = thai_admin_boundary.find_tambon_geometry(body.province_th, body.amphoe_th, body.tambon_th)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="ไม่พบตำบลนี้ในฐานข้อมูล THA_Tambon — ตรวจว่าเลือกจาก dropdown ที่ผูกกับ "
            "admin_boundary_lookup.json จริง ไม่ใช่พิมพ์ชื่อเอง",
        )
    return ThaiTambonLookupResponse(
        province_th=body.province_th,
        amphoe_th=body.amphoe_th,
        tambon_th=body.tambon_th,
        name_en=result["name_en"],
        area_km2=result["area_km2"],
        area_km2_source="THA_Tambon.dbf (ฐานข้อมูลระดับประเทศ, นำเข้าอัตโนมัติผ่านหน้า admin-setup)",
        geom_geojson=result["geom_geojson"],
    )


# ============================================================
# Villages
# ============================================================

_VILLAGE_COLS = (
    "village_id, tambon_id, moo, name_th, name_source, households, population, "
    "residential_rai, agri_rai, forest_rai, other_rai, total_rai, data_year_be"
)


def _row_to_village(row) -> VillageResponse:
    def _f(v):
        return float(v) if v is not None else None

    return VillageResponse(
        village_id=str(row["village_id"]),
        tambon_id=str(row["tambon_id"]),
        moo=row["moo"],
        name_th=row["name_th"],
        name_source=row["name_source"],
        households=row["households"],
        population=row["population"],
        residential_rai=_f(row["residential_rai"]),
        agri_rai=_f(row["agri_rai"]),
        forest_rai=_f(row["forest_rai"]),
        other_rai=_f(row["other_rai"]),
        total_rai=_f(row["total_rai"]),
        data_year_be=row["data_year_be"],
    )


@router.get("/villages", response_model=list[VillageResponse])
def list_villages(tambon_id: str | None = Query(default=None)):
    sql = f"select {_VILLAGE_COLS} from villages"
    params: list = []
    if tambon_id:
        sql += " where tambon_id = %s"
        params.append(tambon_id)
    sql += " order by moo"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [_row_to_village(r) for r in rows]


@router.get("/villages/{village_id}", response_model=VillageResponse)
def get_village(village_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_VILLAGE_COLS} from villages where village_id = %s", (village_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="village not found")
    return _row_to_village(row)


@router.post("/villages", response_model=VillageResponse, status_code=201)
def create_village(body: VillageCreateRequest, _admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into villages (tambon_id, moo, name_th, name_source, households, population, "
                "residential_rai, agri_rai, forest_rai, other_rai, total_rai, data_year_be) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                f"returning {_VILLAGE_COLS}",
                (
                    body.tambon_id,
                    body.moo,
                    body.name_th,
                    body.name_source,
                    body.households,
                    body.population,
                    body.residential_rai,
                    body.agri_rai,
                    body.forest_rai,
                    body.other_rai,
                    body.total_rai,
                    body.data_year_be,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_village(row)


@router.patch("/villages/{village_id}", response_model=VillageResponse)
def update_village(village_id: str, body: VillageUpdateRequest, _admin: dict = Depends(require_admin)):
    """แก้ไขข้อมูลหมู่บ้านบางส่วน (partial update) — ใช้เติมประชากร/ครัวเรือน/พื้นที่ใช้ที่ดิน
    ให้หมู่บ้านที่สร้างไว้ก่อนหน้านี้ได้ โดยไม่ต้องลบสร้างใหม่ (ซึ่งจะทำให้เสียขอบเขตที่วาดไว้แล้ว)"""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="ไม่มีฟิลด์ที่จะแก้ไข")
    set_clauses = [f"{col} = %s" for col in fields]
    params = list(fields.values()) + [village_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"update villages set {', '.join(set_clauses)} where village_id = %s returning {_VILLAGE_COLS}",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="village not found")
    return _row_to_village(row)


# ============================================================
# Village boundary parts (Phase 3 — วาดขอบเขตหมู่บ้านบน Leaflet เท่านั้น)
# ============================================================

@router.get("/village-boundary-parts", response_model=list[VillageBoundaryPartResponse])
def list_village_boundary_parts(village_id: str = Query(...)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select part_id, village_id, part_label, "
                "ST_Area(geom::geography) / 1600.0 as area_rai, "
                "ST_AsGeoJSON(geom)::json as geom_geojson "
                "from village_boundary_parts where village_id = %s order by created_at",
                (village_id,),
            )
            rows = cur.fetchall()
    return [_row_to_boundary_part(r) for r in rows]


@router.post("/village-boundary-parts", response_model=VillageBoundaryPartResponse, status_code=201)
def create_village_boundary_part(body: VillageBoundaryPartCreateRequest, _admin: dict = Depends(require_admin)):
    """admin-only — geom_geojson ต้องมาจากการวาดโพลิกอนบนแผนที่ (Leaflet.draw) ในหน้า admin-setup
    เท่านั้น (ตรงตามเกณฑ์ผ่าน Phase 3: ไม่มีช่องพิมพ์ข้อความอิสระสำหรับตำแหน่ง/พื้นที่)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "insert into village_boundary_parts (village_id, part_label, geom) "
                    "values (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) "
                    "returning part_id, village_id, part_label, "
                    "ST_Area(geom::geography) / 1600.0 as area_rai, "
                    "ST_AsGeoJSON(geom)::json as geom_geojson",
                    (body.village_id, body.part_label, json.dumps(body.geom_geojson)),
                )
            except psycopg.errors.ForeignKeyViolation:
                raise HTTPException(status_code=404, detail="village_id ไม่พบ")
            row = cur.fetchone()
        conn.commit()
    return _row_to_boundary_part(row)


def _row_to_boundary_part(row) -> VillageBoundaryPartResponse:
    return VillageBoundaryPartResponse(
        part_id=str(row["part_id"]),
        village_id=str(row["village_id"]),
        part_label=row["part_label"],
        area_rai=round(float(row["area_rai"]), 2),
        geom_geojson=row["geom_geojson"],
    )


# ============================================================
# Water storage sources
# ============================================================

_SOURCE_COLS = (
    "source_id, tambon_id, village_id, source_type, name_th, name_en, telemetry_code, "
    "stored_capacity_m3, catchment_yield_potential_m3_per_year, capacity_source_note, "
    "lat, lon, built_by, beneficiary_agri_rai"
)


def _row_to_source(row) -> WaterSourceResponse:
    def _f(v):
        return float(v) if v is not None else None

    return WaterSourceResponse(
        source_id=str(row["source_id"]),
        tambon_id=str(row["tambon_id"]),
        village_id=str(row["village_id"]) if row["village_id"] else None,
        source_type=row["source_type"],
        name_th=row["name_th"],
        name_en=row["name_en"],
        telemetry_code=row["telemetry_code"],
        stored_capacity_m3=_f(row["stored_capacity_m3"]),
        catchment_yield_potential_m3_per_year=_f(row["catchment_yield_potential_m3_per_year"]),
        capacity_source_note=row["capacity_source_note"],
        lat=_f(row["lat"]),
        lon=_f(row["lon"]),
        built_by=row["built_by"],
        beneficiary_agri_rai=_f(row["beneficiary_agri_rai"]),
    )


@router.get("/water-sources", response_model=list[WaterSourceResponse])
def list_water_sources(
    tambon_id: str | None = Query(default=None),
    village_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
):
    sql = f"select {_SOURCE_COLS} from water_storage_sources where 1=1"
    params: list = []
    if tambon_id:
        sql += " and tambon_id = %s"
        params.append(tambon_id)
    if village_id:
        sql += " and village_id = %s"
        params.append(village_id)
    if source_type:
        sql += " and source_type = %s"
        params.append(source_type)
    sql += " order by name_th"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [_row_to_source(r) for r in rows]


@router.get("/water-sources/{source_id}", response_model=WaterSourceResponse)
def get_water_source(source_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_SOURCE_COLS} from water_storage_sources where source_id = %s", (source_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="water source not found")
    return _row_to_source(row)


@router.post("/water-sources", response_model=WaterSourceResponse, status_code=201)
def create_water_source(body: WaterSourceCreateRequest, _admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into water_storage_sources (tambon_id, village_id, source_type, name_th, name_en, "
                "telemetry_code, stored_capacity_m3, catchment_yield_potential_m3_per_year, "
                "capacity_source_note, lat, lon, built_by, beneficiary_agri_rai) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                f"returning {_SOURCE_COLS}",
                (
                    body.tambon_id,
                    body.village_id,
                    body.source_type,
                    body.name_th,
                    body.name_en,
                    body.telemetry_code,
                    body.stored_capacity_m3,
                    body.catchment_yield_potential_m3_per_year,
                    body.capacity_source_note,
                    body.lat,
                    body.lon,
                    body.built_by,
                    body.beneficiary_agri_rai,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_source(row)


# ============================================================
# Reservoir -> village usage matrix (Phase 6)
# ============================================================

_RES_USAGE_COLS = (
    "usage_id, source_id, village_id, use_type, households, population, irrigated_area_rai, source, note"
)


def _row_to_reservoir_usage(row) -> ReservoirVillageUsageResponse:
    return ReservoirVillageUsageResponse(
        usage_id=str(row["usage_id"]),
        source_id=str(row["source_id"]),
        village_id=str(row["village_id"]),
        use_type=row["use_type"],
        households=row["households"],
        population=row["population"],
        irrigated_area_rai=float(row["irrigated_area_rai"]) if row["irrigated_area_rai"] is not None else None,
        source=row["source"],
        note=row["note"],
    )


@router.get("/water-sources/{source_id}/village-usage", response_model=list[ReservoirVillageUsageResponse])
def list_reservoir_village_usage(source_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"select {_RES_USAGE_COLS} from reservoir_village_usage "
                "where source_id = %s order by village_id, use_type",
                (source_id,),
            )
            rows = cur.fetchall()
    return [_row_to_reservoir_usage(r) for r in rows]


@router.put("/water-sources/{source_id}/village-usage", response_model=list[ReservoirVillageUsageResponse])
def replace_reservoir_village_usage(
    source_id: str, body: ReservoirVillageUsageReplaceRequest, _admin: dict = Depends(require_admin)
):
    """แทนที่ตาราง (matrix) การใช้อ่างนี้ทั้งหมดในคำสั่งเดียว — เหมาะกับ UI แบบเลือก/แก้ทีละอ่าง
    (ลบแถวเดิมทั้งหมดของ source_id นี้ แล้ว insert ตามรายการที่ส่งมาใหม่ ภายใน transaction เดียว)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select source_id from water_storage_sources where source_id = %s", (source_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="water source not found")

            cur.execute("delete from reservoir_village_usage where source_id = %s", (source_id,))
            for item in body.items:
                cur.execute(
                    "insert into reservoir_village_usage "
                    "(source_id, village_id, use_type, households, population, irrigated_area_rai, source, note) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        source_id,
                        item.village_id,
                        item.use_type,
                        item.households,
                        item.population,
                        item.irrigated_area_rai,
                        item.source,
                        item.note,
                    ),
                )
            cur.execute(
                f"select {_RES_USAGE_COLS} from reservoir_village_usage "
                "where source_id = %s order by village_id, use_type",
                (source_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_row_to_reservoir_usage(r) for r in rows]


# ============================================================
# Auto-recompute สมดุลน้ำหลังบันทึกรายงานพืช/ปศุสัตว์ (Phase 6 — instant feedback แทนรอ cron รอบถัดไป)
# ดู 00_docs/future-tambon-onboarding-plan.md ข้อ 7
#
# เรียก pipeline/balance_engine.py เป็น subprocess แยกกระบวนการ (ไม่ import ตรงๆ) เพราะ pipeline/db.py กับ
# backend/db.py ชื่อโมดูลชนกัน (ทั้งคู่ชื่อ "db") — bare import ข้ามโฟลเดอร์เสี่ยงไปเจอโมดูลผิดตัวจาก
# sys.modules cache (import ครั้งแรกของชื่อไหนจะถูก cache ไว้ ใครมา import ซ้ำชื่อเดิมได้ตัวเดิมกลับไปเสมอ
# ไม่ว่าจะอยู่คนละไฟล์กัน) แยกโปรเซสตัดปัญหานี้ทิ้งไปเลย และ pipeline/ ไม่ต้องรู้จัก backend/ เลยแม้แต่น้อย
# (ยังคง standalone รันจาก GitHub Actions ได้เหมือนเดิม ไม่ต้องแก้อะไรในนั้น)
#
# รันผ่าน BackgroundTasks (หลัง response ส่งกลับไปแล้ว) เพราะการกรอกรายงาน 1 ครั้งจากหน้า report.html อาจ
# ยิง POST ทีละแถวติดกันหลายแถว (พืชหลายชนิด) — ถ้า block รอ recompute ทุกแถว (ซึ่งคำนวณทั้งตำบลใหม่ทุกครั้ง
# ไม่ใช่แค่แถวเดียว) ผู้ใช้ต้องรอซ้ำซ้อนหลายรอบ ปล่อยเป็น background แล้วปล่อยให้ recompute ล่าสุดทับของเก่า
# (idempotent อยู่แล้ว — ดู pipeline/db.py::write_balance_results ลบของเดือน/ตำบลนั้นทิ้งก่อนค่อย insert ใหม่)
# ผลลัพธ์สุดท้ายเหมือนกันไม่ว่าจะรันกี่รอบซ้อนกัน แค่เร็วกว่าเพราะไม่ block response
#
# balance_engine.py เองมี fallback อยู่แล้วถ้ายังไม่มี et0_mm ของเดือนนั้น (ยังไม่ถึงรอบ GEE pipeline
# ต้นเดือนถัดไป) จะ print คำเตือนแล้วข้ามตำบลนั้นไปเฉยๆ ไม่ error — ไม่ block การบันทึกรายงานที่เพิ่งสำเร็จ
# ============================================================

_PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"
_BALANCE_ENGINE = _PIPELINE_DIR / "balance_engine.py"


def _recompute_balance_for_month(reported_month: date) -> None:
    """best-effort: ความล้มเหลวใดๆ ที่นี่ต้องไม่กระทบรายงานที่บันทึกไปแล้ว (รันเป็น background task
    หลัง response ส่งกลับไปแล้วเสมอ — ดูจุดเรียกใน create_crop_report / create_livestock_report)"""
    if not _BALANCE_ENGINE.exists():
        print(f"[balance-recompute] ข้าม: ไม่พบ {_BALANCE_ENGINE}")
        return
    try:
        result = subprocess.run(
            [sys.executable, str(_BALANCE_ENGINE), str(reported_month.year), str(reported_month.month)],
            cwd=str(_PIPELINE_DIR),
            timeout=60,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"[balance-recompute] balance_engine.py exit={result.returncode}\n"
                f"{(result.stdout or '')[-2000:]}\n{(result.stderr or '')[-2000:]}"
            )
    except Exception as exc:  # noqa: BLE001 — ตั้งใจกันไม่ให้ recompute ที่พังไปกระทบอะไรอื่น (background แล้ว)
        print(f"[balance-recompute] ล้มเหลว: {exc}")


# ============================================================
# Crop reports
# ============================================================

_CROP_COLS = "report_id, village_id, crop_name, planted_area_rai, reported_month, reported_by_role"


@router.get("/crop-reports", response_model=list[CropReportResponse])
def list_crop_reports(village_id: str | None = Query(default=None), month: str | None = Query(default=None)):
    sql = f"select {_CROP_COLS} from crop_report where 1=1"
    params: list = []
    if village_id:
        sql += " and village_id = %s"
        params.append(village_id)
    if month:
        sql += " and reported_month = %s"
        params.append(month)
    sql += " order by reported_month desc"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [CropReportResponse(**{**r, "report_id": str(r["report_id"]), "village_id": str(r["village_id"])}) for r in rows]


@router.post("/crop-reports", response_model=CropReportResponse, status_code=201)
def create_crop_report(
    body: CropReportCreateRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)
):
    check_can_write_village(user, body.village_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into crop_report (village_id, crop_name, planted_area_rai, reported_month, reported_by_role) "
                "values (%s, %s, %s, %s, %s) "
                f"returning {_CROP_COLS}",
                (body.village_id, body.crop_name, body.planted_area_rai, body.reported_month, user["role"]),
            )
            row = cur.fetchone()
        conn.commit()
    background_tasks.add_task(_recompute_balance_for_month, body.reported_month)
    return CropReportResponse(**{**row, "report_id": str(row["report_id"]), "village_id": str(row["village_id"])})


@router.post("/crop-reports/bulk", response_model=list[CropReportResponse], status_code=201)
def bulk_create_crop_reports(
    body: CropReportBulkRequest, background_tasks: BackgroundTasks, admin: dict = Depends(require_admin)
):
    """นำเข้ารายงานพืชหลายหมู่บ้าน/หลายชนิดพืชในคำสั่งเดียว (admin เท่านั้น) — เพิ่มมาเพื่อรองรับกรณีมีตาราง
    สรุปพื้นที่เกษตรทั้งตำบลอยู่แล้ว (เช่น สกัดจากชั้นข้อมูล Landuse แบบ 1 แถวต่อหมู่บ้าน) แทนที่จะต้องกรอกทีละ
    หมู่บ้านทีละพืชผ่าน POST /crop-reports เดี่ยวๆ (ตามฟอร์มปกติใน report.html) — frontend ที่เรียก endpoint
    นี้คือ js/bulk-crop-import.js (ส่วน "นำเข้าพื้นที่เกษตรหลายหมู่บ้านพร้อมกัน" ใน report.html)

    ต่างจาก POST /crop-reports เดี่ยวๆ 3 จุด:
    1) รับได้หลายแถว (หลายหมู่บ้าน x หลายพืช) พร้อมกันใน 1 request แทนที่จะวน POST ทีละแถวจาก frontend
       (เร็วกว่า และ atomic กว่า — ถ้าแถวใดพัง จะ rollback ทั้งชุดแทนที่จะได้ผลลัพธ์ค้างครึ่งๆ กลางๆ)
    2) ถ้า replace_existing=true (ค่าเริ่มต้น) จะลบรายงานพืชเดิมของทุก (village_id, reported_month) ที่ปรากฏ
       อยู่ใน items ก่อน insert ชุดใหม่ทั้งหมด — ต่างจากฟอร์มเดี่ยวใน report.js ที่ "block" การส่งซ้ำแทน เพราะ
       ที่นี่คือการ "แทนที่ทั้งชุดข้อมูลของหมู่บ้านนั้นในเดือนนั้น" ด้วยตารางสรุปที่นำเข้าใหม่ (เช่น ไฟล์ landuse
       ที่แก้ไขแล้วนำมา import ซ้ำ) ไม่ใช่การเพิ่มทีละรายการที่ต้องกันซ้ำแบบ append
    3) เรียก recompute background task แค่ครั้งเดียวต่อเดือนที่ import (ไม่ใช่ทุกแถวเหมือนฟอร์มเดี่ยว) กัน
       overload ตอน import พร้อมกันหลายร้อยแถว

    หมายเหตุ: ไม่ตรวจ "พื้นที่ปลูกรวมไม่เกิน agri_rai ของหมู่บ้าน" แบบที่ frontend ฟอร์มเดี่ยว (report.js) ทำ
    เพราะข้อมูลที่เข้ามาทางนี้มักมาจากแหล่งที่แม่นกว่า/ใหม่กว่า (เช่น landuse overlay) ซึ่งควรเป็นตัวปรับปรุง
    agri_rai ของหมู่บ้านเอง (ผ่าน PATCH /villages/{id} แยกต่างหาก) ไม่ใช่ถูกบล็อกด้วยค่า agri_rai เดิมที่อาจ
    เก่ากว่า/ไม่แม่นเท่า"""
    village_ids = list({item.village_id for item in body.items})
    created = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            if body.replace_existing and village_ids:
                cur.execute(
                    "delete from crop_report where reported_month = %s and village_id = any(%s)",
                    (body.reported_month, village_ids),
                )
            for item in body.items:
                cur.execute(
                    "insert into crop_report (village_id, crop_name, planted_area_rai, reported_month, reported_by_role) "
                    "values (%s, %s, %s, %s, %s) "
                    f"returning {_CROP_COLS}",
                    (item.village_id, item.crop_name, item.planted_area_rai, body.reported_month, admin["role"]),
                )
                created.append(cur.fetchone())
        conn.commit()
    background_tasks.add_task(_recompute_balance_for_month, body.reported_month)
    return [
        CropReportResponse(**{**r, "report_id": str(r["report_id"]), "village_id": str(r["village_id"])})
        for r in created
    ]


# ============================================================
# Livestock reports
# ============================================================

_LIVESTOCK_COLS = "report_id, village_id, species, head_count, reported_month, reported_by_role"


@router.get("/livestock-reports", response_model=list[LivestockReportResponse])
def list_livestock_reports(village_id: str | None = Query(default=None), month: str | None = Query(default=None)):
    sql = f"select {_LIVESTOCK_COLS} from livestock_report where 1=1"
    params: list = []
    if village_id:
        sql += " and village_id = %s"
        params.append(village_id)
    if month:
        sql += " and reported_month = %s"
        params.append(month)
    sql += " order by reported_month desc"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [
        LivestockReportResponse(**{**r, "report_id": str(r["report_id"]), "village_id": str(r["village_id"])})
        for r in rows
    ]


@router.post("/livestock-reports", response_model=LivestockReportResponse, status_code=201)
def create_livestock_report(
    body: LivestockReportCreateRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)
):
    check_can_write_village(user, body.village_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into livestock_report (village_id, species, head_count, reported_month, reported_by_role) "
                "values (%s, %s, %s, %s, %s) "
                f"returning {_LIVESTOCK_COLS}",
                (body.village_id, body.species, body.head_count, body.reported_month, user["role"]),
            )
            row = cur.fetchone()
        conn.commit()
    background_tasks.add_task(_recompute_balance_for_month, body.reported_month)
    return LivestockReportResponse(
        **{**row, "report_id": str(row["report_id"]), "village_id": str(row["village_id"])}
    )


# ============================================================
# Water balance (Phase 5) — อ่านอย่างเดียว ผลคำนวณมาจาก pipeline/balance_engine.py
# ============================================================

@router.get("/balance", response_model=BalanceResponse)
def get_balance(tambon_id: str = Query(...)):
    """คืนสมดุลน้ำ 4 หมวด ต่อหมู่บ้าน + ภาพรวมตำบล ตามเกณฑ์ผ่าน Phase 5 (01-phased-work-plan.md)

    available_months คือเดือนที่มี water_balance_monthly จริงเท่านั้น (มาจาก ET0/ฝนที่ pipeline/run_monthly.py
    คำนวณแล้วจริง) — ไม่ fabricate เดือนที่ยังไม่ได้รัน GEE pipeline ให้ครบ 12 เดือน
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select tambon_id, name_th from tambons where tambon_id = %s", (tambon_id,))
            tambon_row = cur.fetchone()
            if not tambon_row:
                raise HTTPException(status_code=404, detail="tambon not found")

            cur.execute(
                "select village_id, name_th, moo from villages where tambon_id = %s order by moo",
                (tambon_id,),
            )
            village_rows = cur.fetchall()

            cur.execute(
                "select wb.village_id, wb.month, wb.category, wb.supply_cum, wb.demand_cum, "
                "wb.balance_cum, wb.status "
                "from water_balance_monthly wb "
                "join villages v on v.village_id = wb.village_id "
                "where v.tambon_id = %s "
                "order by wb.month",
                (tambon_id,),
            )
            balance_rows = cur.fetchall()

            # อ่างเก็บน้ำระดับตำบล (village_id IS NULL) — ไม่ถูกนับในระดับหมู่บ้านรายตัว, รวมเฉพาะภาพรวมตำบล
            cur.execute(
                "select coalesce(sum(stored_capacity_m3), 0) as total "
                "from water_storage_sources where tambon_id = %s and village_id is null",
                (tambon_id,),
            )
            reservoir_total = float(cur.fetchone()["total"])

    months_set = sorted({str(r["month"]) for r in balance_rows})

    # จัดกลุ่มต่อหมู่บ้าน
    by_village: dict = {}
    for r in balance_rows:
        vid = str(r["village_id"])
        month = str(r["month"])
        by_village.setdefault(vid, {}).setdefault(month, {})[r["category"]] = BalanceCategoryValue(
            supply_cum=float(r["supply_cum"]),
            demand_cum=float(r["demand_cum"]),
            balance_cum=float(r["balance_cum"]),
            status=r["status"],
        )

    villages_out = [
        VillageBalanceResponse(
            village_id=str(v["village_id"]),
            name_th=v["name_th"],
            moo=v["moo"],
            months=by_village.get(str(v["village_id"]), {}),
        )
        for v in village_rows
    ]

    # ภาพรวมตำบล: demand = ผลรวมทุกหมู่บ้านต่อหมวด/เดือน, supply = สระหมู่บ้านทุกแห่ง (ผลรวม supply_cum
    # ต่อหมู่บ้าน นับซ้ำไม่ได้เพราะแต่ละหมู่บ้าน supply_cum ก็คือสระของหมู่บ้านตัวเองอยู่แล้ว) + อ่างตำบล
    overview_months: dict = {}
    for month in months_set:
        for category in ("consumption", "domestic", "agri", "livestock"):
            total_demand = 0.0
            total_supply = 0.0
            seen_village = set()
            for r in balance_rows:
                if str(r["month"]) != month or r["category"] != category:
                    continue
                total_demand += float(r["demand_cum"])
                vid = str(r["village_id"])
                if vid not in seen_village:  # supply_cum ต่อหมู่บ้านนับครั้งเดียว (ซ้ำกันทั้ง 4 หมวดในแถวเดิม)
                    total_supply += float(r["supply_cum"])
                    seen_village.add(vid)
            total_supply += reservoir_total
            balance = round(total_supply - total_demand, 2)
            status = "surplus" if (total_demand <= 0 or total_supply >= total_demand) else "deficit"
            overview_months.setdefault(month, {})[category] = BalanceCategoryValue(
                supply_cum=round(total_supply, 2),
                demand_cum=round(total_demand, 2),
                balance_cum=balance,
                status=status,
            )

    return BalanceResponse(
        tambon_id=str(tambon_row["tambon_id"]),
        tambon_name_th=tambon_row["name_th"],
        available_months=months_set,
        villages=villages_out,
        tambon_overview=TambonBalanceOverview(months=overview_months, reservoir_capacity_m3=reservoir_total),
    )


# ============================================================
# Data completeness dashboard (future-tambon-onboarding-plan.md ขั้นตอนที่ 8)
# ============================================================
# ต้องตรงกับ frontend/js/report.js — sentinel ที่ POST ไปที่ /livestock-reports (head_count=0) เพื่อยืนยัน
# "หมู่บ้านนี้ไม่มีปศุสัตว์เดือนนี้จริงๆ" (ไม่ใช่แค่ยังไม่ได้กรอก) ต้อง filter ออกก่อนนับเป็นชนิดสัตว์จริง
# แต่นับเป็น "มีข้อมูลครบแล้ว" (green) เหมือนกัน — ห้ามลืม sync ค่านี้ถ้าฝั่ง frontend เปลี่ยน
NO_LIVESTOCK_SENTINEL = "ไม่มีปศุสัตว์"


@router.get("/data-completeness", response_model=DataCompletenessResponse)
def get_data_completeness(tambon_id: str = Query(...)):
    """สรุปความครบถ้วนข้อมูลรายหมู่บ้าน+ภาพรวมตำบล ใช้ก่อนตัดสินใจกด "คำนวณสมดุลน้ำ" — เกณฑ์เขียว/เหลือง/แดง
    เทียบเท่างานที่เคยทำด้วยมือให้แม่นาเรือใน 00_docs/phase5-data-gaps.md อิงตารางข้อ 2 ของ
    future-tambon-onboarding-plan.md (เฉพาะหมวดที่ "จำเป็น": หมู่บ้าน/ขอบเขต/แหล่งน้ำ/พืช/ปศุสัตว์ —
    ปฏิทินเพาะปลูก(7), ฝาย(9), บ่อรายจุด(10) เป็นหมวดเสริมคุณภาพ ไม่รวมในเกณฑ์นี้เพราะไม่บล็อกการคำนวณ)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select tambon_id, name_th from tambons where tambon_id = %s", (tambon_id,))
            tambon_row = cur.fetchone()
            if not tambon_row:
                raise HTTPException(status_code=404, detail="tambon not found")

            cur.execute(
                "select village_id, moo, name_th, population, households "
                "from villages where tambon_id = %s order by moo",
                (tambon_id,),
            )
            village_rows = cur.fetchall()
            village_ids = [r["village_id"] for r in village_rows]

            boundary_counts: dict = {}
            supply_own_counts: dict = {}
            supply_usage_village_ids: set = set()
            crop_counts: dict = {}
            livestock_species_by_village: dict = {}

            if village_ids:
                cur.execute(
                    "select village_id, count(*) as n from village_boundary_parts "
                    "where village_id = any(%s) group by village_id",
                    (village_ids,),
                )
                boundary_counts = {str(r["village_id"]): r["n"] for r in cur.fetchall()}

                cur.execute(
                    "select village_id, count(*) as n from water_storage_sources "
                    "where village_id = any(%s) group by village_id",
                    (village_ids,),
                )
                supply_own_counts = {str(r["village_id"]): r["n"] for r in cur.fetchall()}

                cur.execute(
                    "select distinct rvu.village_id from reservoir_village_usage rvu "
                    "where rvu.village_id = any(%s)",
                    (village_ids,),
                )
                supply_usage_village_ids = {str(r["village_id"]) for r in cur.fetchall()}

                cur.execute(
                    "select village_id, count(*) as n from crop_report "
                    "where village_id = any(%s) group by village_id",
                    (village_ids,),
                )
                crop_counts = {str(r["village_id"]): r["n"] for r in cur.fetchall()}

                cur.execute(
                    "select village_id, species, count(*) as n from livestock_report "
                    "where village_id = any(%s) group by village_id, species",
                    (village_ids,),
                )
                for r in cur.fetchall():
                    livestock_species_by_village.setdefault(str(r["village_id"]), []).append(
                        {"species": r["species"], "n": r["n"]}
                    )

            # อ่างเก็บน้ำระดับตำบล (ไม่ผูกหมู่บ้านใดหมู่บ้านหนึ่ง) — ดูภาพรวม
            cur.execute(
                "select source_id from water_storage_sources where tambon_id = %s and source_type = 'reservoir'",
                (tambon_id,),
            )
            reservoir_ids = [r["source_id"] for r in cur.fetchall()]
            reservoirs_with_usage = 0
            if reservoir_ids:
                cur.execute(
                    "select count(distinct source_id) as n from reservoir_village_usage where source_id = any(%s)",
                    (reservoir_ids,),
                )
                reservoirs_with_usage = cur.fetchone()["n"]

    if not reservoir_ids:
        reservoir_status = "yellow"
        reservoir_detail = "ตำบลนี้ยังไม่มีอ่างเก็บน้ำในระบบ — ถ้าจริงไม่มีอ่างเลยไม่ต้องกรอก (ไม่บล็อกการคำนวณ)"
    elif reservoirs_with_usage < len(reservoir_ids):
        reservoir_status = "yellow"
        reservoir_detail = (
            f"มีอ่าง {len(reservoir_ids)} แห่ง แต่ยังไม่ได้กรอกตารางการใช้น้ำแยกหมู่บ้าน "
            f"{len(reservoir_ids) - reservoirs_with_usage} แห่ง (ขั้นตอนที่ 4)"
        )
    else:
        reservoir_status = "green"
        reservoir_detail = f"อ่างทั้ง {len(reservoir_ids)} แห่งกรอกตารางการใช้น้ำแยกหมู่บ้านครบแล้ว"

    villages_out: list[VillageCompleteness] = []
    for v in village_rows:
        vid = str(v["village_id"])

        has_pop = v["population"] is not None
        has_hh = v["households"] is not None
        if has_pop and has_hh:
            village_info = CategoryCompleteness(status="green", detail="มีข้อมูลประชากร+ครัวเรือนแล้ว")
        elif has_pop or has_hh:
            village_info = CategoryCompleteness(status="yellow", detail="มีข้อมูลบางส่วน (ประชากรหรือครัวเรือน)")
        else:
            village_info = CategoryCompleteness(status="red", detail="ยังไม่มีข้อมูลประชากร/ครัวเรือน")

        boundary_n = boundary_counts.get(vid, 0)
        boundary = (
            CategoryCompleteness(status="green", detail=f"วาดขอบเขตแล้ว {boundary_n} ส่วน")
            if boundary_n > 0
            else CategoryCompleteness(status="red", detail="ยังไม่ได้วาดขอบเขตหมู่บ้าน")
        )

        has_own_supply = supply_own_counts.get(vid, 0) > 0
        has_reservoir_usage = vid in supply_usage_village_ids
        if has_own_supply and has_reservoir_usage:
            water_supply = CategoryCompleteness(status="green", detail="มีแหล่งน้ำของหมู่บ้านเอง + ใช้อ่างตำบลด้วย")
        elif has_own_supply or has_reservoir_usage:
            water_supply = CategoryCompleteness(
                status="green" if has_own_supply else "yellow",
                detail=(
                    f"มีแหล่งน้ำของหมู่บ้านเอง {supply_own_counts.get(vid, 0)} แห่ง"
                    if has_own_supply
                    else "ใช้อ่างเก็บน้ำระดับตำบล (ยังไม่มีแหล่งน้ำของหมู่บ้านเอง)"
                ),
            )
        else:
            water_supply = CategoryCompleteness(status="red", detail="ยังไม่มีแหล่งน้ำ (สระ/บ่อ/อ่าง) เลย")

        crop_n = crop_counts.get(vid, 0)
        crop = (
            CategoryCompleteness(status="green", detail=f"มีรายงานพืช {crop_n} รายการ (สะสมทุกเดือน)")
            if crop_n > 0
            else CategoryCompleteness(status="red", detail="ยังไม่มีรายงานพืชเลยแม้แต่เดือนเดียว")
        )

        species_rows = livestock_species_by_village.get(vid, [])
        has_confirmed_none = any(r["species"] == NO_LIVESTOCK_SENTINEL for r in species_rows)
        real_species_count = sum(r["n"] for r in species_rows if r["species"] != NO_LIVESTOCK_SENTINEL)
        if real_species_count > 0:
            livestock = CategoryCompleteness(status="green", detail=f"มีรายงานปศุสัตว์ {real_species_count} รายการ")
        elif has_confirmed_none:
            livestock = CategoryCompleteness(status="green", detail="ยืนยันแล้วว่าหมู่บ้านนี้ไม่มีปศุสัตว์")
        else:
            livestock = CategoryCompleteness(status="red", detail="ยังไม่ได้กรอก/ยืนยันข้อมูลปศุสัตว์เลย")

        cat_statuses = [village_info.status, boundary.status, water_supply.status, crop.status, livestock.status]
        if all(s == "green" for s in cat_statuses):
            overall = "green"
        elif any(s == "red" for s in cat_statuses):
            overall = "red"
        else:
            overall = "yellow"

        villages_out.append(
            VillageCompleteness(
                village_id=vid,
                moo=v["moo"],
                name_th=v["name_th"],
                village_info=village_info,
                boundary=boundary,
                water_supply=water_supply,
                crop=crop,
                livestock=livestock,
                overall_status=overall,
            )
        )

    villages_green = sum(1 for v in villages_out if v.overall_status == "green")

    return DataCompletenessResponse(
        tambon_id=str(tambon_row["tambon_id"]),
        tambon_name=tambon_row["name_th"],
        reservoir=ReservoirCompleteness(
            total_reservoirs=len(reservoir_ids),
            reservoirs_with_usage=reservoirs_with_usage,
            status=reservoir_status,
            detail=reservoir_detail,
        ),
        villages=villages_out,
        total_villages=len(villages_out),
        villages_green=villages_green,
        can_compute_balance=len(villages_out) > 0 and villages_green == len(villages_out),
    )
