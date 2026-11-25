from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator


class InventoryImportOptions(BaseModel):
    allow_update_existing: bool = False


class InventoryImportIssue(BaseModel):
    sheet: str
    row: int
    field: str | None = None
    message: str


class ItemCategoryImportRow(BaseModel):
    row_no: int
    category_name: str = Field(max_length=128)
    description: str | None = None


class ItemImportRow(BaseModel):
    row_no: int
    category_name: str | None = Field(default=None, max_length=128)
    item_name: str = Field(min_length=1, max_length=128)
    specification: str | None = Field(default=None, max_length=128)
    unit_name: str = Field(max_length=64)
    sub_unit_name: str | None = Field(default=None, max_length=64)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    supplier_name: str | None = Field(default=None, max_length=128)
    is_active: bool = True
    remark: str | None = None

    item_no: str | None = Field(default=None, max_length=64)
    is_asset_managed: bool = False
    default_asset_type_code: str | None = Field(default=None, max_length=64)
    default_asset_management_mode_code: str | None = Field(default=None, max_length=64)
    is_lot_controlled: bool | None = None
    shelf_life_days: int | None = Field(default=None, ge=0, le=2147483647)

class StockImportRow(BaseModel):
    row_no: int
    warehouse_label: str = Field(max_length=400)
    item_selection: str
    counted_quantity: Decimal = Field(ge=0, decimal_places=3)
    lot_no: str | None = Field(default=None, max_length=64)
    production_date: date | None = None
    expiry_date: date | None = None
    remark: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.production_date and self.expiry_date and self.expiry_date < self.production_date:
            raise ValueError("有效期不能早于生产日期")
        return self


class ImportSummary(BaseModel):
    rows: int = 0
    categories: int = 0
    items: int = 0
    warehouses: int = 0


class ImportResult(BaseModel):
    valid: bool
    summary: ImportSummary
    errors: list[InventoryImportIssue] = Field(default_factory=list)
    warnings: list[InventoryImportIssue] = Field(default_factory=list)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    stock_order_ids: list[str] = Field(default_factory=list)


class ItemTemplateChoices(BaseModel):
    asset_types: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    suppliers: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)


class StockTemplateChoices(BaseModel):
    warehouses: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
