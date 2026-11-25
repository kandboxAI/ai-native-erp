from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin
from app.modules.inventory.warehouse.schemas import RequisitionApprovalContext

RequisitionStatus = Literal["submitted", "approved", "rejected", "issued", "withdrawn", "pending_receipt", "receipt_exception", "received"]

STATUS_OPTIONS = [
    {"value": "submitted", "label": "待审批"},
    {"value": "approved", "label": "待发放"},
    {"value": "rejected", "label": "已驳回"},
    {"value": "issued", "label": "已发放"},
    {"value": "pending_receipt", "label": "待签收"},
    {"value": "receipt_exception", "label": "收货异常"},
    {"value": "received", "label": "已签收"},
    {"value": "withdrawn", "label": "已撤回"},
]


class RequisitionLineCreate(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(..., gt=0, max_digits=18, decimal_places=3)


class RequisitionCreate(BaseModel):
    custody_location_note: str | None = Field(default=None, max_length=200)
    warehouse_id: UUID | None = Field(default=None, description="兼容旧客户端的仓库字段；实际申请按每条明细的 warehouse_id 分仓处理")
    purpose: str = Field(..., min_length=1, max_length=1000)
    photo_file_ids: list[UUID] = Field(default_factory=list, max_length=6, description="申请照片；有照片时仅允许单仓申请，跨仓请分别提交")
    lines: list[RequisitionLineCreate] = Field(..., min_length=1, max_length=50)

    @field_validator("lines")
    @classmethod
    def unique_items(cls, value: list[RequisitionLineCreate]) -> list[RequisitionLineCreate]:
        if len({(line.item_id, line.warehouse_id) for line in value}) != len(value):
            raise ValueError("同一仓库中的同一种物资不能重复添加")
        return value


class RequisitionDecision(BaseModel):
    version_no: int = Field(..., ge=1)
    note: str | None = Field(default=None, max_length=500)


class RequisitionEvidence(RequisitionDecision):
    photo_file_ids: list[UUID] = Field(default_factory=list, max_length=6)


class RequisitionIssueLine(BaseModel):
    tracking: dict[str, Any] = Field(default_factory=dict)
    line_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class RequisitionIssue(RequisitionEvidence):
    lines: list[RequisitionIssueLine] | None = Field(default=None, min_length=1, max_length=50)


class RequisitionReceiptLine(BaseModel):
    line_id: UUID
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    exception_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    exception_type_code: Literal["shortage", "wrong_item", "damaged", "not_received"] | None = None


class RequisitionReceipt(RequisitionEvidence):
    lines: list[RequisitionReceiptLine] = Field(min_length=1, max_length=50)


class RequisitionReject(RequisitionDecision):
    note: str = Field(..., min_length=1, max_length=500)


class RequisitionVersion(BaseModel):
    version_no: int = Field(..., ge=1)


class RequisitionListQuery(PageParams):
    keyword: str | None = Field(default=None, max_length=128)
    status_code: RequisitionStatus | None = None
    department_id: UUID | None = None
    warehouse_id: UUID | None = None


class MaterialOption(BaseModel):
    id: UUID
    warehouse_id: UUID
    warehouse_no: str
    warehouse_name: str
    item_no: str
    item_name: str
    category_name: str | None = None
    specification: str | None = None
    unit_code: str
    unit_name: str
    available_quantity: Decimal


class RequisitionLineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    item_no_snapshot: str
    item_name_snapshot: str
    specification_snapshot: str | None = None
    unit_code_snapshot: str
    unit_name: str
    quantity: Decimal
    issued_quantity: Decimal | None = None
    requires_asset_selection: bool = False


class RequisitionEventItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("created_at",)
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type_code: str
    from_status_code: str | None = None
    to_status_code: str
    note: str | None = None
    operator_name_snapshot: str
    created_at: datetime
    photos: list[dict] = Field(default_factory=list)
    receipt_lines: list[dict] = Field(default_factory=list)


class RequisitionItem(DisplayDatetimeJsonMixin, RequisitionApprovalContext):
    can_issue: bool = False
    custody_location_note: str | None = None
    personal_custody_assets: list[dict] = Field(default_factory=list)
    __display_datetime_fields__ = (
        "approved_at",
        "rejected_at",
        "withdrawn_at",
        "issued_at",
        "received_at",
        "created_at",
        "updated_at",
    )
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    request_no: str
    submission_batch_no: str
    warehouse_id: UUID
    warehouse_no: str | None = None
    warehouse_name: str | None = None
    applicant_user_id: UUID
    applicant_name_snapshot: str
    applicant_org_id: UUID | None = None
    applicant_org_name_snapshot: str | None = None
    department_id: UUID | None = None
    department_name_snapshot: str | None = None
    purpose: str
    status_code: str
    approval_note: str | None = None
    approved_by_name_snapshot: str | None = None
    approved_at: datetime | None = None
    rejected_by_name_snapshot: str | None = None
    rejected_at: datetime | None = None
    withdrawn_at: datetime | None = None
    issued_by_name_snapshot: str | None = None
    issued_at: datetime | None = None
    received_by_name_snapshot: str | None = None
    received_at: datetime | None = None
    stock_order_id: UUID | None = None
    stock_order_no: str | None = None
    version_no: int
    created_at: datetime
    updated_at: datetime
    lines: list[RequisitionLineItem] = Field(default_factory=list)
    events: list[RequisitionEventItem] = Field(default_factory=list)

