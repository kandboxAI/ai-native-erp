"""资产管理请求、响应和查询协议。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.pagination import PageParams


class AssetLocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_id: UUID | None = None
    physical_location_id: UUID
    is_active: bool = True
    remark: str | None = Field(default=None, max_length=1000)


class AssetLocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    physical_location_id: UUID
    is_active: bool | None = None
    remark: str | None = Field(default=None, max_length=1000)


class VersionBody(BaseModel):
    expected_version: int = Field(ge=1)


class AssetLedgerQuery(PageParams):
    """统一资产台账查询；底层仍分别维护批量资产和编号资产。"""

    is_asset_managed: bool | None = None
    item_id: UUID | None = None

    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=128)
    management_mode: Literal["batch", "individual"] | None = None
    location_id: UUID | None = None
    asset_type_code: str | None = None
    status_code: str | None = None
    registration_status_code: str | None = None
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None


class AssetItemOptionQuery(PageParams):
    org_id: UUID | None = None
    permission_key: Literal["asset_register:list", "asset_register:create"] = "asset_register:list"
    keyword: str | None = Field(default=None, max_length=128)


class AssetRegistrationCreate(BaseModel):
    """简洁资产登记；数量代表需要生成的逐件资产卡数量。"""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    org_id: UUID | None = None
    asset_no: str | None = Field(default=None, max_length=64)
    item_id: UUID
    quantity: int = Field(default=1, ge=1, le=1000, strict=True)
    warehouse_id: UUID | None = None
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    location_id: UUID | None = None
    original_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    acquired_date: date | None = None
    status_code: Literal["idle", "in_use"] = "idle"
    remark: str | None = Field(default=None, max_length=1000)

    @field_validator("asset_no")
    @classmethod
    def normalize_number(cls, value):
        return value or None

    @model_validator(mode="after")
    def validate_registration(self):
        if self.quantity > 1 and self.asset_no:
            raise ValueError("多件资产自动逐件编号，请留空资产编号")
        if self.warehouse_id:
            if self.status_code != "idle":
                raise ValueError("选择仓库时资产状态为闲置")
        elif not self.location_id or not self.department_id or not self.custodian_user_id:
            raise ValueError("未选仓库时必须填写资产位置、责任部门和资产保管人")
        return self


class LocationAssetCreate(BaseModel):
    acquisition_source_code: Literal["historical", "donation", "direct_delivery", "stock_receipt"] = "historical"
    org_id: UUID | None = None
    location_id: UUID
    item_id: UUID
    asset_type_code: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0)
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    status_code: str = Field(default="in_use", min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=1000)


class LocationAssetUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    asset_type_code: str | None = Field(default=None, min_length=1, max_length=64)
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    status_code: str | None = Field(default=None, min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=1000)


class LocationAssetAdjust(BaseModel):
    expected_version: int = Field(ge=1)
    quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class LocationAssetTransfer(BaseModel):
    expected_version: int = Field(ge=1)
    target_location_id: UUID
    quantity: Decimal = Field(gt=0)
    target_department_id: UUID | None = None
    target_custodian_user_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)


class LocationAssetQuery(PageParams):
    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=128)
    location_id: UUID | None = None
    asset_type_code: str | None = None
    status_code: str | None = None
    registration_status_code: str | None = None
    department_id: UUID | None = None


class AssetRegisterCreate(BaseModel):
    acquisition_source_code: Literal["historical", "donation", "direct_delivery", "stock_receipt"] = "historical"
    org_id: UUID | None = None
    asset_no: str = Field(min_length=1, max_length=64)
    item_id: UUID
    asset_type_code: str = Field(min_length=1, max_length=64)
    serial_no: str | None = Field(default=None, max_length=128)
    location_id: UUID
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    status_code: str = Field(default="in_use", min_length=1, max_length=64)
    acquired_date: date | None = None
    original_amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=1000)


class AssetRegisterUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    asset_no: str | None = Field(default=None, min_length=1, max_length=64)
    asset_type_code: str | None = Field(default=None, min_length=1, max_length=64)
    serial_no: str | None = Field(default=None, max_length=128)
    status_code: str | None = Field(default=None, min_length=1, max_length=64)
    acquired_date: date | None = None
    original_amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=1000)


class AssetRegisterTransfer(BaseModel):
    expected_version: int = Field(ge=1)
    location_id: UUID | None = None
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_change(self):
        if not ({"location_id", "department_id", "custodian_user_id"} & self.model_fields_set):
            raise ValueError("地点、责任部门和保管人至少填写一项")
        return self


class AssetRegisterQuery(PageParams):
    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=128)
    location_id: UUID | None = None
    asset_type_code: str | None = None
    status_code: str | None = None
    registration_status_code: str | None = None
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None


class AssetEventQuery(PageParams):
    asset_register_id: UUID | None = None
    location_item_id: UUID | None = None

    @model_validator(mode="after")
    def require_one_target(self):
        if (self.asset_register_id is None) == (self.location_item_id is None):
            raise ValueError("单件设备和场所数量资产必须且只能指定一项")
        return self


class AssetRegistrationConfirm(BaseModel):
    expected_version: int = Field(ge=1)


class AssetRegistrationVoid(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class AssetEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type_code: str
    quantity_before: Decimal | None = None
    quantity_after: Decimal | None = None
    from_location_id: UUID | None = None
    to_location_id: UUID | None = None
    from_department_id: UUID | None = None
    to_department_id: UUID | None = None
    from_custodian_user_id: UUID | None = None
    to_custodian_user_id: UUID | None = None
    from_status_code: str | None = None
    to_status_code: str | None = None
    source_type_code: str
    source_id: UUID | None = None
    note: str
    operator_name_snapshot: str
    created_at: datetime
