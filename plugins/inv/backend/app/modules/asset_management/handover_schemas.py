"""资产交接请求和查询协议。"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.db.pagination import PageParams


class AssetHandoverLineCreate(BaseModel):
    asset_register_id: UUID | None = None
    location_item_id: UUID | None = None
    quantity: Decimal = Field(gt=0)
    disposition_code: Literal["transfer_teacher", "return_logistics"]
    to_location_id: UUID
    to_department_id: UUID
    to_custodian_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if (self.asset_register_id is None) == (self.location_item_id is None):
            raise ValueError("单件资产和场所数量资产必须且只能指定一项")
        if self.asset_register_id is not None and self.quantity != Decimal("1"):
            raise ValueError("单件资产交接数量必须为 1")
        if self.disposition_code == "transfer_teacher" and self.to_custodian_user_id is None:
            raise ValueError("移交接任教师时必须指定接收人")
        if self.disposition_code == "return_logistics":
            self.to_custodian_user_id = None
        return self


class AssetHandoverCreate(BaseModel):
    org_id: UUID | None = None
    source_type_code: Literal["manual", "teacher_offboarding"] = "manual"
    source_id: UUID | None = None
    transferor_user_id: UUID | None = None
    transferor_name_snapshot: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=1000)
    lines: list[AssetHandoverLineCreate] = Field(min_length=1, max_length=500)


class AssetHandoverUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    remark: str | None = Field(default=None, max_length=1000)
    lines: list[AssetHandoverLineCreate] = Field(min_length=1, max_length=500)


class AssetHandoverQuery(PageParams):
    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=128)
    status_code: str | None = None
    transferor_user_id: UUID | None = None
    receiver_user_id: UUID | None = None
    source_type_code: str | None = None
    source_id: UUID | None = None


class AssetHandoverVersion(BaseModel):
    expected_version: int = Field(ge=1)


class AssetHandoverVoid(AssetHandoverVersion):
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("请填写作废原因")
        return self


class AssetHandoverReject(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AssetHandoverLineResubmit(BaseModel):
    expected_version: int = Field(ge=1)
    quantity: Decimal = Field(gt=0)
    disposition_code: Literal["transfer_teacher", "return_logistics"]
    to_location_id: UUID
    to_department_id: UUID
    to_custodian_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if self.disposition_code == "transfer_teacher" and self.to_custodian_user_id is None:
            raise ValueError("移交接任教师时必须指定接收人")
        if self.disposition_code == "return_logistics":
            self.to_custodian_user_id = None
        return self
