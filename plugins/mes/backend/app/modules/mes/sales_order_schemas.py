from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.db.pagination import PageParams
from .quotation_schemas import StrictBody, Quantity, Money


class SalesOrderQuery(PageParams):
    status_code: Literal["confirmed", "approved", "cancelled"] | None = None
    quotation_id: UUID | None = None


class SalesOrderLineBody(StrictBody):
    quotation_line_id: UUID
    quotation_version_no: int = Field(ge=1)
    quotation_tier_id: UUID | None = None
    quantity: Quantity
    unit_price: Money
    discount_rate: Decimal | None = Field(default=None, ge=Decimal("0.7"), le=1, max_digits=5, decimal_places=4, allow_inf_nan=False)
    due_date: date
    is_price_confirmed: bool = False
    adjustment_reason: str = Field(default="", max_length=1000)


class SalesOrderBody(StrictBody):
    customer_po_no: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=16, max_length=128)
    lines: list[SalesOrderLineBody] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({row.quotation_line_id for row in self.lines}) != len(self.lines):
            raise ValueError("同一货品请选择一个数量档，不能重复下单")
        return self


class SalesReleaseLine(StrictBody):
    order_line_id: UUID
    quantity: Quantity
    product_item_id: UUID | None = None
    is_create_product: bool = False
    product_unit_code: str | None = Field(default=None, max_length=64)
    processing_type_code: Literal["in_house", "outsourced", "purchased"] = "in_house"

    @model_validator(mode="after")
    def selected_or_created(self):
        if bool(self.product_item_id) == self.is_create_product:
            raise ValueError("请选择已有生产物料，或确认按订单货品建档")
        return self


class SalesReleaseBody(StrictBody):
    version_no: int = Field(ge=1)
    idempotency_key: str = Field(min_length=16, max_length=128)
    is_unit_confirmed: bool = Field(default=False, deprecated=True, description="兼容旧客户端；服务端按真实单位校验，不作为放行依据")
    lines: list[SalesReleaseLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({row.order_line_id for row in self.lines}) != len(self.lines):
            raise ValueError("生产安排货品不能重复")
        return self


class SalesOrderApproval(StrictBody):
    version_no: int = Field(ge=1)


class SalesOrderCommand(StrictBody):
    version_no: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=1000)


class SalesOrderEditLine(StrictBody):
    id: UUID
    quantity: Quantity
    unit_price: Money
    discount_rate: Decimal | None = Field(default=None, ge=Decimal("0.7"), le=1, max_digits=5, decimal_places=4, allow_inf_nan=False)
    due_date: date
    adjustment_reason: str = Field(default="", max_length=1000)
    is_price_confirmed: bool = False


class SalesOrderEdit(StrictBody):
    version_no: int = Field(ge=1)
    customer_po_no: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=1000)
    lines: list[SalesOrderEditLine] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({row.id for row in self.lines}) != len(self.lines):
            raise ValueError("订单货品不得重复")
        return self
