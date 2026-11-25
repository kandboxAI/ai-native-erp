from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.db.pagination import PageParams


class DeliveryQuery(PageParams):
    fulfillment_mode_code: Literal["direct", "stock"] = "direct"
    warehouse_id: UUID | None = None
    sales_order_id: UUID | None = None
    org_id: UUID | None = None
    customer_id: UUID | None = None
    customer_no: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=128)
    customer: str | None = Field(default=None, max_length=128)
    status_code: str | None = Field(default=None, max_length=64)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ShipmentLineBody(BaseModel):
    work_order_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class ShipmentBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    org_id: UUID | None = None
    sales_order_id: UUID | None = None
    customer_id: UUID | None = None
    shipment_no: str | None = Field(default=None, min_length=1, max_length=64)
    customer_no_snapshot: str | None = Field(default=None, min_length=1, max_length=64)
    customer_name_snapshot: str | None = Field(default=None, min_length=1, max_length=128)
    business_date: date
    fulfillment_mode_code: Literal["direct", "stock"] = "direct"
    warehouse_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)
    lines: list[ShipmentLineBody] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("lines")
    @classmethod
    def unique_lines(cls, value):
        if len({row.work_order_id for row in value}) != len(value):
            raise ValueError("同一出货单不能重复选择工单，请合并数量")
        return value

    @model_validator(mode="after")
    def warehouse(self):
        if (self.fulfillment_mode_code == "stock") != (self.warehouse_id is not None):
            raise ValueError("仓储出货必须指定来源仓库；生产直发不指定仓库")
        if not self.customer_id and not (self.customer_no_snapshot and self.customer_name_snapshot):
            raise ValueError("请选择出货客户")
        return self


class ShipmentUpdate(ShipmentBody):
    version_no: int = Field(ge=1)


class ReconciliationLineBody(BaseModel):
    shipment_line_id: UUID
    adjustment_amount: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2)
    adjustment_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def reason(self):
        if self.adjustment_amount and not (self.adjustment_reason or "").strip():
            raise ValueError("调整金额非零时必须填写调整原因")
        return self


class ReconciliationBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    org_id: UUID | None = None
    reconciliation_no: str = Field(min_length=1, max_length=64)
    customer_no_snapshot: str = Field(min_length=1, max_length=64)
    customer_name_snapshot: str = Field(min_length=1, max_length=128)
    period_start: date
    period_end: date
    note: str | None = Field(default=None, max_length=2000)
    lines: list[ReconciliationLineBody] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_period_lines(self):
        if self.period_start > self.period_end:
            raise ValueError("对账期间开始不能晚于结束")
        if len({row.shipment_line_id for row in self.lines}) != len(self.lines):
            raise ValueError("同一出货明细不能重复对账")
        return self


class DeliveryCommand(BaseModel):
    version_no: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
