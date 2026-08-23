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
    # เพิ่ม 2569-08 — agri_rai (พื้นที่เกษตร baseline จากฟอร์มสำรวจหมู่บ้าน) แทบไม่มีใครกรอกในทางปฏิบัติ
    # จริง (ต่างจากรายงานพืชรายเดือนที่ชาวบ้านกรอกผ่าน report.html เป็นประจำ) ตั้งใจไม่แตะ agri_rai/total_rai
    # เดิม เพราะ agri_rai ยังใช้เป็นเพดานบล็อกการส่งรายงานพืชเกิน (ดู report.js) — ถ้า sync อัตโนมัติจาก
    # ยอดรายงานเดือนล่าสุดจะกลายเป็นบล็อกเดือนถัดไปที่พื้นที่ปลูกเพิ่มขึ้นแทน จึงเพิ่มฟิลด์ใหม่แยกต่างหาก
    # สำหรับหน้าแดชบอร์ดใช้แสดง "พื้นที่เกษตรรวม" แทน โดยดึงจาก crop_report ของเดือนล่าสุดที่มีรายงานจริง
    # (ดู list_villages/get_village ใน routes.py — LEFT JOIN LATERAL หา reported_month ล่าสุดต่อหมู่บ้าน)
    latest_crop_area_rai: Optional[float] = None
    latest_crop_report_month: Optional[date] = None


class VillageUpdateRequest(BaseModel):
    """แก้ไขข้อมูลหมู่บ้านที่มีอยู่แล้วบางส่วน (partial update) — ส่งเฉพาะฟิลด์ที่ต้องการแก้มาเท่านั้น
    ใช้เติมข้อมูลประชากร/ครัวเรือน/พื้นที่ใช้ที่ดินย้อนหลังให้หมู่บ้านที่สร้างไว้ก่อนมีฟอร์มนี้ได้ด้วย"""
    moo: Optional[int] = None
    name_th: Optional[str] = None
    name_source: Optional[str] = None
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
    source_type: Literal["pond", "reservoir", "groundwater_well", "mountain_spring", "purchased_external", "weir", "small_water_source"]
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


# ---------- Reservoir -> village usage matrix (Phase 6 — จัดสรรอ่างเก็บน้ำระดับตำบลให้หมู่บ้านที่ใช้จริง)
# ออกแบบเป็น manual checkbox matrix (อ่าง x หมู่บ้าน) ไม่ใช่คำนวณจาก GIS — ตำบลที่ไม่มีข้อมูลโซนชลประทาน
# (เช่น zone_b_irrigated.shp ของแม่นาเรือ) ก็กรอกได้ปกติ แถวไหนไม่กรอกเลย ระบบจะ pooled ที่ภาพรวมตำบลแทน
# (ดู routes.py get_balance() และ 00_docs/future-tambon-onboarding-plan.md ข้อ 6) ----------

class ReservoirVillageUsageItem(BaseModel):
    """1 แถวของ matrix: อ่าง (source_id มาจาก path) x หมู่บ้าน x ประเภทการใช้ — ทุกฟิลด์ไม่บังคับ (กรอกได้ถ้ารู้
    ไม่บล็อกถ้าไม่รู้ตัวเลขแน่ชัด) households/population มีความหมายเฉพาะ use_type='domestic' (อ้างอิงประชากร/
    ครัวเรือนที่ได้รับประโยชน์ — ไม่ได้เข้าสูตรคำนวณจริง สูตรน้ำอุปโภคยังใช้ประชากร×50 ล./คน/วันเหมือนเดิม)
    irrigated_area_rai มีความหมายเฉพาะ use_type='agri' (อ้างอิงพื้นที่ชลประทานจากอ่างนี้ — ไม่ได้เข้าสูตรคำนวณจริง
    เช่นกัน ตัวเลขเกษตรที่ใช้คำนวณจริงมาจาก crop_report เสมอ) ฟิลด์ที่ไม่เกี่ยวกับ use_type นั้นๆ ปล่อยว่างได้"""
    village_id: str
    use_type: Literal["agri", "domestic"]
    households: Optional[int] = None
    population: Optional[int] = None
    irrigated_area_rai: Optional[float] = None
    source: Optional[str] = None
    note: Optional[str] = None


class ReservoirVillageUsageResponse(BaseModel):
    usage_id: str
    source_id: str
    village_id: str
    use_type: str
    households: Optional[int] = None
    population: Optional[int] = None
    irrigated_area_rai: Optional[float] = None
    source: Optional[str] = None
    note: Optional[str] = None


class ReservoirVillageUsageReplaceRequest(BaseModel):
    """แทนที่ข้อมูลการใช้อ่างนี้ทั้งหมดด้วยรายการใหม่ (ลบแถวเดิมที่ไม่อยู่ในลิสต์ + เพิ่มแถวที่ส่งมา) —
    ออกแบบให้เหมาะกับ UI แบบ matrix (แก้ทีเดียวทั้งตาราง แล้วกดบันทึกครั้งเดียวต่ออ่าง 1 แห่ง)"""
    items: list[ReservoirVillageUsageItem]


# ---------- Data completeness dashboard (future-tambon-onboarding-plan.md ขั้นตอนที่ 8) ----------
# เขียว = ครบ, เหลือง = มีบางส่วน, แดง = ยังไม่มีข้อมูลเลย — ดูรายละเอียดเกณฑ์แต่ละหมวดใน routes.py

class CategoryCompleteness(BaseModel):
    status: Literal["green", "yellow", "red"]
    detail: Optional[str] = None


class VillageCompleteness(BaseModel):
    village_id: str
    moo: int
    name_th: str
    village_info: CategoryCompleteness  # ประชากร/ครัวเรือน (ข้อ 1)
    boundary: CategoryCompleteness  # ขอบเขตหมู่บ้าน (ข้อ 2)
    water_supply: CategoryCompleteness  # แหล่งน้ำของหมู่บ้านเอง หรือได้รับจัดสรรจากอ่างตำบล (ข้อ 3-4)
    crop: CategoryCompleteness  # พืชที่ปลูก (ข้อ 6)
    livestock: CategoryCompleteness  # ปศุสัตว์ (ข้อ 8) — นับ "ยืนยันไม่มี" เป็นครบด้วย
    overall_status: Literal["green", "yellow", "red"]


class ReservoirCompleteness(BaseModel):
    """ภาพรวมระดับตำบล (อ่างเก็บน้ำผูกได้หลายหมู่บ้าน ไม่ใช่ของหมู่บ้านใดหมู่บ้านหนึ่ง) — เป็นข้อมูลประกอบ
    ไม่ใช้ gate ปุ่มคำนวณสมดุลน้ำโดยตรง เพราะบางตำบลอาจไม่มีอ่างเลยแล้วพึ่งสระ/แก้มลิงระดับหมู่บ้านแทนได้"""
    total_reservoirs: int
    reservoirs_with_usage: int
    status: Literal["green", "yellow", "red"]
    detail: Optional[str] = None


class DataCompletenessResponse(BaseModel):
    tambon_id: str
    tambon_name: str
    reservoir: ReservoirCompleteness
    villages: list[VillageCompleteness]
    total_villages: int
    villages_green: int
    can_compute_balance: bool


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
    # None ปกติ — ตั้งค่าเฉพาะตอน crop_name (ตัดเอาแค่ "พืชหลัก" ก่อน + หรือ / ตัวแรก) ไม่มีอยู่ในตาราง
    # crop_group_alias เลย เพื่อเตือนผู้กรอก/แอดมินว่าแถวนี้บันทึกสำเร็จแล้วแต่จะไม่ถูกคิดน้ำเกษตรให้ จนกว่า
    # จะมีคนเพิ่ม mapping เข้าตาราง crop_group_alias (ดู _unmapped_crop_warning ใน routes.py)
    unmapped_crop_warning: str | None = None


class CropReportBulkItem(BaseModel):
    village_id: str
    crop_name: str
    planted_area_rai: float = Field(ge=0)


class CropReportBulkRequest(BaseModel):
    """นำเข้ารายงานพืชหลายหมู่บ้าน/หลายชนิดพืชพร้อมกัน — เหมาะกับกรณีมีตารางสรุปพื้นที่เกษตรทั้งตำบลอยู่แล้ว
    (เช่น สกัดจากชั้นข้อมูล Landuse แบบ 1 แถวต่อหมู่บ้าน หลายคอลัมน์ = พืชแต่ละชนิด) แทนที่จะกรอกทีละหมู่บ้าน
    ทีละพืชผ่านฟอร์มปกติ — reported_month ใช้ร่วมกันทุกแถวใน request เดียว (import 1 ครั้ง = 1 เดือน)"""
    reported_month: date
    items: list[CropReportBulkItem]
    replace_existing: bool = True


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


# ---------- Water balance (Phase 5) ----------

class BalanceCategoryValue(BaseModel):
    """1 หมวด (consumption/domestic/agri/livestock) ของ 1 เดือน — supply_cum ซ้ำกันทั้ง 4 หมวดโดยตั้งใจ
    (สต็อกน้ำก้อนเดียวแข่งกันใช้ทุกประเภท ไม่ได้แบ่งสัดส่วนตายตัวต่อประเภท — ดู pipeline/balance_engine.py)"""
    supply_cum: float
    demand_cum: float
    balance_cum: float
    status: str  # 'surplus' | 'deficit'


class VillageBalanceResponse(BaseModel):
    village_id: str
    name_th: str
    moo: int
    months: dict[str, dict[str, BalanceCategoryValue]]  # {month: {category: value}}


class TambonBalanceOverview(BaseModel):
    """ภาพรวมตำบล — demand = ผลรวมทุกหมู่บ้าน, supply = สระระดับหมู่บ้านทุกแห่ง + อ่างเก็บน้ำระดับตำบล
    (water_storage_sources.village_id IS NULL) ที่ไม่ถูกนับในระดับหมู่บ้านรายตัว"""
    months: dict[str, dict[str, BalanceCategoryValue]]
    reservoir_capacity_m3: float  # ความจุอ่างระดับตำบลที่รวมเข้ามาเพิ่มจากระดับหมู่บ้าน (แสดงแยกให้เห็นที่มา)


class BalanceResponse(BaseModel):
    tambon_id: str
    tambon_name_th: str
    available_months: list[str]  # เดือนที่มีข้อมูล ET0/ฝนจริงแล้วเท่านั้น (ไม่ fabricate เดือนที่ยังไม่มี)
    villages: list[VillageBalanceResponse]
    tambon_overview: TambonBalanceOverview


# ---------- Runoff estimate (แยกจาก BalanceResponse โดยเด็ดขาด — ดูคอมเมนต์ endpoint /runoff-estimate
# ใน routes.py และตาราง runoff_estimate_monthly ใน Supabase — ยังไม่ตัดสินใจว่าจะรวมเข้าน้ำต้นทุนยังไง
# เพิ่ม 2569-08 คู่กับส่วนแสดงผลแยกต่างหากในหน้า dashboard.html) ----------

class RunoffMonthEntry(BaseModel):
    month: str
    runoff_volume_m3: float
    n_villages_computed: int  # จำนวนหมู่บ้านที่มีข้อมูลจริงเดือนนั้น (เทียบกับ n_villages_total ของทั้งตำบล
    # เพื่อบอกความครบถ้วน — บางหมู่บ้านอาจขาด runoff_coefficient/total_rai ของเดือนนั้น)


class RunoffEstimateResponse(BaseModel):
    tambon_id: str
    n_villages_total: int
    months: list[RunoffMonthEntry]
