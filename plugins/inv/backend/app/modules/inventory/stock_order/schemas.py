from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


# ───────── 单据类型 ─────────
class OrderTypeCreate(BaseModel):
    type_no: str = Field(..., min_length=1, max_length=64)
    type_name: str = Field(..., min_length=1, max_length=128)
    direction_code: str = Field(..., max_length=64, description="字典 inv_stock_direction")
    default_from_status_code: str | None = Field(default=None, max_length=64)
    default_to_status_code: str | None = Field(default=None, max_length=64)
    is_approval_required: bool = False
    wf_definition_id: UUID | None = None
    required_field_config: dict[str, Any] | None = None
    is_negative_allowed: bool = False
    is_active: bool = True
    sort_no: int | None = None


class OrderTypeUpdate(BaseModel):
    type_name: str | None = Field(default=None, min_length=1, max_length=128)
    default_from_status_code: str | None = Field(default=None, max_length=64)
    default_to_status_code: str | None = Field(default=None, max_length=64)
    is_approval_required: bool | None = None
    wf_definition_id: UUID | None = None
    required_field_config: dict[str, Any] | None = None
    is_negative_allowed: bool | None = None
    is_active: bool | None = None
    sort_no: int | None = None


class OrderTypeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type_no: str
    type_name: str
    direction_code: str
    default_from_status_code: str | None = None
    default_to_status_code: str | None = None
    is_approval_required: bool
    wf_definition_id: UUID | None = None
    required_field_config: dict[str, Any] | None = None
    is_negative_allowed: bool
    is_builtin: bool
    is_source_managed: bool = False
    is_active: bool
    sort_no: int | None = None
    form: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class OrderTypeListQuery(PageParams):
    direction_code: str | None = None
    is_active: bool | None = None


class OrderTypeOptionQuery(BaseModel):
    warehouse_scope_key: str | None = Field(default=None, max_length=64)
    form: str | None = Field(default=None, description="inbound / outbound / transfer / lend / return / damage / adjust")
    direction_code: str | None = None
    include_inactive: bool = False


# ───────── 单据 ─────────
class OrderLineWrite(BaseModel):
    tracking: dict[str, Any] = Field(default_factory=dict, description="已注册的明细追踪配置，由拥有模块校验并保存到关系表")
    item_id: UUID
    lot_id: UUID | None = None
    lot_no: str | None = Field(default=None, max_length=64, description="入库时按批次号查找或新建批次")
    production_date: date | None = None
    expiry_date: date | None = None
    from_warehouse_id: UUID | None = None
    to_warehouse_id: UUID | None = None
    from_stock_status_code: str | None = Field(default=None, max_length=64)
    to_stock_status_code: str | None = Field(default=None, max_length=64)
    quantity: Decimal | None = Field(default=None, ge=0, description="数量，正数；盘点调整行可不传，按实盘数计算")
    unit_code: str | None = Field(default=None, max_length=64, description="默认取物料基本单位")
    unit_price: Decimal | None = Field(default=None, ge=0)
    source_line_id: UUID | None = Field(default=None, description="归还行引用借出行")
    counted_quantity: Decimal | None = Field(default=None, ge=0, description="实盘数量（盘点调整）")
    remark: str | None = None


class OrderCreate(BaseModel):
    order_type_id: UUID
    org_id: UUID | None = Field(default=None, description="不传时取来源（或目标）仓库所属组织")
    business_date: date | None = None
    from_warehouse_id: UUID | None = None
    to_warehouse_id: UUID | None = None
    supplier_id: UUID | None = Field(default=None, description="供应商；写入往来方与名称快照，并记录到新建批次")
    counterparty_party_id: UUID | None = None
    counterparty_user_id: UUID | None = Field(default=None, description="领用人、借用人为本校用户时传入，自动解析为人员主体与姓名快照")
    counterparty_name_snapshot: str | None = Field(default=None, max_length=128)
    department_id: UUID | None = None
    purpose: str | None = None
    reason: str | None = None
    handling_method_code: str | None = Field(default=None, max_length=64)
    expected_return_date: date | None = None
    source_doc_type_code: str | None = Field(default=None, max_length=64)
    source_doc_id: UUID | None = None
    currency_code: str | None = Field(default=None, max_length=64)
    remark: str | None = None
    lines: list[OrderLineWrite] = Field(..., min_length=1)
    submit: bool = Field(default=False, description="保存后提交")
    confirm: bool = Field(default=False, description="保存后直接确认记账（类型需要审批时不可用）")


class OrderUpdate(BaseModel):
    business_date: date | None = None
    from_warehouse_id: UUID | None = None
    to_warehouse_id: UUID | None = None
    supplier_id: UUID | None = None
    counterparty_party_id: UUID | None = None
    counterparty_user_id: UUID | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=128)
    department_id: UUID | None = None
    purpose: str | None = None
    reason: str | None = None
    handling_method_code: str | None = Field(default=None, max_length=64)
    expected_return_date: date | None = None
    currency_code: str | None = Field(default=None, max_length=64)
    remark: str | None = None
    lines: list[OrderLineWrite] | None = Field(default=None, description="传入时整体替换明细")


class OrderBatchCreate(BaseModel):
    orders: list[OrderCreate] = Field(..., min_length=1, max_length=50)


class OrderVoid(BaseModel):
    void_reason: str | None = None


class OrderReject(BaseModel):
    reason: str | None = None


class ReturnLineWrite(BaseModel):
    tracking: dict[str, Any] = Field(default_factory=dict)
    source_line_id: UUID
    quantity: Decimal = Field(..., gt=0)


class ReturnCreate(BaseModel):
    """按借出单生成并确认归还单；不传明细时归还全部未归还数量。"""

    lines: list[ReturnLineWrite] | None = None
    business_date: date | None = None
    remark: str | None = None


class OrderListQuery(PageParams):
    warehouse_scope_key: str | None = Field(default=None, max_length=64)
    form: str | None = None
    direction_code: str | None = None
    order_type_id: UUID | None = None
    status_code: str | None = None
    org_id: UUID | None = None
    warehouse_id: UUID | None = Field(default=None, description="来源或目标仓库")
    item_id: UUID | None = None
    business_date_start: date | None = None
    business_date_end: date | None = None
    has_unreturned: bool | None = Field(default=None, description="借出单：是否仍有未归还数量")


class OrderLineListQuery(OrderListQuery):
    item_keyword: str | None = None
