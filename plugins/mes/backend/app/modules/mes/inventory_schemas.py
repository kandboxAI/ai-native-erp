from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.db.pagination import PageParams


class InventoryPostingBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    work_order_id: UUID
    operation_id: UUID | None = None
    posting_type_code: Literal["issue", "return", "receipt"]
    source_posting_id: UUID | None = None
    item_id: UUID
    warehouse_id: UUID
    lot_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    business_date: date | None = None
    note: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def source(self):
        if (self.posting_type_code == "return") != (self.source_posting_id is not None):
            raise ValueError("只有退料需要且必须指定原领料记录")
        return self


class InventoryPostingQuery(PageParams):
    keyword: str | None = Field(default=None, max_length=128)
    work_order_id: UUID | None = None
    posting_type_code: Literal["issue", "return", "receipt", "shipment"] | None = None


class InventoryPostingCommand(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
