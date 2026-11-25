from decimal import Decimal
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StockAssetChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    target_location_id: UUID | None = None
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None


class StockAssetRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    department_id: UUID | None = None
    custodian_user_id: UUID | None = None
    asset_no: str | None = Field(default=None, min_length=1, max_length=64)
    acquired_date: date | None = None
    original_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class StockAssetTracking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[StockAssetChoice] = Field(default_factory=list, max_length=200)
    registration: StockAssetRegistration | None = None

    @model_validator(mode="after")
    def unique_bindings(self):
        if self.registration is not None and self.selections:
            raise ValueError("新收货登记与已有实物流转不能同时选择")
        if len({row.binding_id for row in self.selections}) != len(self.selections):
            raise ValueError("同一实物不能重复选择")
        return self
