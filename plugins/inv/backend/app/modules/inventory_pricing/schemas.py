from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.db.pagination import PageParams


class PriceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    org_id: UUID
    supplier_id: UUID
    item_id: UUID
    currency_code: str = Field(default="CNY", min_length=1, max_length=64)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    valid_from: date
    valid_to: date | None = None
    is_active: bool = True
    version_no: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_period(self):
        if self.valid_to and self.valid_to <= self.valid_from: raise ValueError("失效日期必须晚于生效日期")
        return self


class PriceQuery(PageParams):
    org_id: UUID | None = None
    is_active: bool | None = None


