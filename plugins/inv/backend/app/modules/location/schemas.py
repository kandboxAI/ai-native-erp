from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    org_id: UUID | None = None
    location_no: str | None = Field(default=None, min_length=1, max_length=64,
                                    description="不填写时自动生成；编辑时保留原编号")
    location_name: str = Field(min_length=1, max_length=128)
    location_type_code: str = Field(min_length=1, max_length=64)
    parent_id: None = Field(default=None, description="兼容旧请求的空值；当前不支持位置层级")
    latitude: Decimal = Field(ge=-90, le=90, max_digits=10, decimal_places=7)
    longitude: Decimal = Field(ge=-180, le=180, max_digits=10, decimal_places=7)
    coordinate_system_code: str = Field(default="gcj02", min_length=1, max_length=32)
    location_description: str | None = Field(default=None, max_length=500)
    sort_no: int = Field(default=0, ge=0, le=999999)
    is_active: bool = True
    remark: str | None = Field(default=None, max_length=1000)


class LocationUpdate(LocationCreate):
    expected_version: int = Field(ge=1)


class VersionBody(BaseModel):
    expected_version: int = Field(ge=1)
