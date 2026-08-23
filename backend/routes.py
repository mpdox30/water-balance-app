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

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

import thai_admin_boundary
from db import get_conn
from schemas import (
    BalanceCategoryValue,
    BalanceResponse,
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

_RES_USAGE_COLS = "usage_id, source_id, village_id, use_type, households, population, source, note"


def _row_to_reservoir_usage(row) -> ReservoirVillageUsageResponse:
    return ReservoirVillageUsageResponse(
        usage_id=str(row["usage_id"]),
        source_id=str(row["source_id"]),
        village_id=str(row["village_id"]),
        use_type=row["use_type"],
        households=row["households"],
        population=row["population"],
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
                    "(source_id, village_id, use_type, households, population, source, note) "
                    "values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        source_id,
                        item.village_id,
                        item.use_type,
                        item.households,
                        item.population,
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
def create_crop_report(body: CropReportCreateRequest, user: dict = Depends(get_current_user)):
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
    return CropReportResponse(**{**row, "report_id": str(row["report_id"]), "village_id": str(row["village_id"])})


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
def create_livestock_report(body: LivestockReportCreateRequest, user: dict = Depends(get_current_user)):
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
