"""schemas.py — Pydantic request/response models สำหรับ endpoint ทั้งหมดใน Phase 1"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    village_id: Optional[str] = None
    display_name: Optional[str] = None


class UserCreateRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: Literal["admin", "village_rep"]
    village_id: Optional[str] = None
    display_name: Optional[str] = None


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    village_id: Optional[str] = None
    display_name: Optional[str] = None


# ---------- Tambons ----------

class TambonCreateRequest(BaseModel):
    name_th: str
    name_en: Optional[str] = None
    province_th: str
    amphoe_th: str
    area_km2: float
    area_km2_source: str
    is_pilot: bool = False
    geom_geojson: Optional[dict] = None  # GeoJSON Polygon/MultiPolygon geometry object


class TambonResponse(BaseModel):
    tambon_id: str
    name_th: str
    name_en: Optional[str] = None
    province_th: str
    amphoe_th: str
    area_km2: float
    area_km2_source: str
    is_pilot: bool
    geom_geojson: Optional[dict] = None


# ---------- Thai nationwide admin boundary lookup (Phase 3) ----------

class ThaiTambonLookupRequest(BaseModel):
    """มาจากการเลือก dropdown จังหวัด/อำเภอ/ตำบล (ผูกกับ admin_boundary_lookup.json) เท่านั้น —
    ไม่ใช่ช่องพิมพ์ข้อความอิสระ (ค่าที่พิมพ์ไม่ตรงกับตัวเลือกใน dropdown จะหา geometry ไม่เจอ)"""
    province_th: str
    amphoe_th: str
    tambon_th: str


class ThaiTambonLookupResponse(BaseModel):
    province_th: str
    amphoe_th: str
    tambon_th: str
    name_en: Optional[str] = None
    area_km2: float
    area_km2_source: str
    geom_geojson: dict


# ---------- Villages ----------

class VillageCreateRequest(BaseModel):
    tambon_id: str
    moo: int
    name_th: str
    name_source: str = "manual"
    households: Optional[int] = None
    population: Optional[int] = None
    residential_rai: Optional[float] = None
    agri_rai: Optional[float] = None
    forest_rai: Optional[float] = None
    other_rai: Optional[float] = None
    total_rai: Optional[float] = None
    data_year_be: Optional[int] = None


class VillageResponse(BaseModel):
    village_id: str
    tambon_id: str
    moo: int
    name_th: str
    name_source: str
    households: Optional[int] = None
    population: Optional[int] = None
    residential_rai: Optional[float] = None
    agri_rai: Optional[float] = None
    forest_rai: Optional[float] = None
    other_rai: Optional[float] = None
    total_rai: Optional[float] = None
    data_year_be: Optional[int] = None


# ---------- Village boundary parts (Phase 3 — วาดขอบเขตบน Leaflet เท่านั้น ไม่พิมพ์พิกัดเอง) ----------

class VillageBoundaryPartCreateRequest(BaseModel):
    village_id: str
    part_label: Optional[str] = None  # null = ส่วนเดียว, 'เขต1'/'เขต2' = พื้นที่ไม่ต่อเนื่อง
    geom_geojson: dict  # GeoJSON Polygon geometry object — มาจากการวาดบนแผนที่ (Leaflet.draw) เท่านั้น


class VillageBoundaryPartResponse(BaseModel):
    part_id: str
    village_id: str
    part_label: Optional[str] = None
    area_rai: float
    geom_geojson: dict


# ---------- Water storage sources ----------

class WaterSourceCreateRequest(BaseModel):
    tambon_id: str
    village_id: Optional[str] = None
    source_type: Literal["pond", "reservoir", "groundwater_well", "mountain_spring", "purchased_external"]
    name_th: str
    name_en: Optional[str] = None
    telemetry_code: Optional[str] = None
    stored_capacity_m3: Optional[float] = None
    catchment_yield_potential_m3_per_year: Optional[float] = None
    capacity_source_note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    built_by: Optional[str] = None
    beneficiary_agri_rai: Optional[float] = None


class WaterSourceResponse(BaseModel):
    source_id: str
    tambon_id: str
    village_id: Optional[str] = None
    source_type: str
    name_th: str
    name_en: Optional[str] = None
    telemetry_code: Optional[str] = None
    stored_capacity_m3: Optional[float] = None
    catchment_yield_potential_m3_per_year: Optional[float] = None
    capacity_source_note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    built_by: Optional[str] = None
    beneficiary_agri_rai: Optional[float] = None


# ---------- Crop / livestock reports ----------

class CropReportCreateRequest(BaseModel):
    village_id: str
    crop_name: str
    planted_area_rai: float = Field(ge=0)
    reported_month: date


class CropReportResponse(BaseModel):
    report_id: str
    village_id: str
    crop_name: str
    planted_area_rai: float
    reported_month: date
    reported_by_role: str


class LivestockReportCreateRequest(BaseModel):
    village_id: str
    species: str
    head_count: int = Field(ge=0)
    reported_month: date


class LivestockReportResponse(BaseModel):
    report_id: str
    village_id: str
    species: str
    head_count: int
    reported_month: date
    reported_by_role: str
