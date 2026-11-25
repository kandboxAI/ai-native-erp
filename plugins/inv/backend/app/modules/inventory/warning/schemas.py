from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.db.pagination import PageParams

StockAlertStatus = Literal["unconfigured", "out_of_stock", "low_stock", "normal", "overstock"]
StockAlertFilter = Literal["unconfigured", "out_of_stock", "low_stock", "normal", "overstock", "replenishment"]


class StockAlertEvaluation(BaseModel):
    status: StockAlertStatus
    label: str
    suggested_replenishment_quantity: Decimal = Decimal("0")


class ProjectedOverstockWarning(BaseModel):
    item_id: UUID
    item_name: str
    unit_code: str
    current_quantity: Decimal
    inbound_quantity: Decimal
    projected_quantity: Decimal
    max_quantity: Decimal


class InboundWarningPreview(BaseModel):
    warnings: list[ProjectedOverstockWarning]


class StockThresholdUpdate(BaseModel):
    min_quantity: Decimal = Field(ge=0)
    max_quantity: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self):
        if self.min_quantity >= self.max_quantity:
            raise ValueError("安全库存下限必须小于补货目标/库存上限")
        return self


class StockSettingQuery(PageParams):
    warehouse_scope_key: str | None = Field(default=None, max_length=64)
    """安全库存设置：查询已有库存余额或已配置阈值的物料仓库组合。"""

    org_id: UUID | None = None
    warehouse_id: UUID | None = None
    category_id: UUID | None = None
    item_id: UUID | None = None
    keyword: str | None = None
    status_code: Literal[
        "all",
        "configured",
        "unconfigured",
        "out_of_stock",
        "low_stock",
        "normal",
        "overstock",
    ] = "all"


class StockThresholdItem(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    org_id: UUID
    min_quantity: Decimal
    max_quantity: Decimal
