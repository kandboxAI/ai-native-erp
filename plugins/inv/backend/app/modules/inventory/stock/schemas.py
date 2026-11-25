from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams

from ..warning.schemas import StockAlertFilter


class StockSummaryQuery(PageParams):
    """库存查询：物料 × 仓库汇总。"""
    warehouse_scope_key: str | None = Field(default=None, max_length=64)

    org_id: UUID | None = None
    warehouse_id: UUID | None = None
    category_id: UUID | None = None
    item_id: UUID | None = None
    alert_status: StockAlertFilter | None = None
    include_zero: bool = False


class StockAlertQuery(PageParams):
    """低库存补货预警：按物料 × 仓库返回缺货或低于安全库存的物料。"""
    warehouse_scope_key: str | None = Field(default=None, max_length=64)

    org_id: UUID | None = None
    warehouse_id: UUID | None = None
    category_id: UUID | None = None
    item_id: UUID | None = None
    status_code: Literal["replenishment", "out_of_stock", "low_stock", "unconfigured"] = "replenishment"


class StockBalanceQuery(PageParams):
    """余额明细：物料 × 仓库 × 批次 × 库存状态。"""
    warehouse_scope_key: str | None = Field(default=None, max_length=64)

    org_id: UUID | None = None
    warehouse_id: UUID | None = None
    item_id: UUID | None = None
    lot_id: UUID | None = None
    stock_status_code: str | None = None
    include_zero: bool = False


class TransactionQuery(PageParams):
    warehouse_scope_key: str | None = Field(default=None, max_length=64)
    org_id: UUID | None = None
    item_id: UUID | None = None
    warehouse_id: UUID | None = None
    lot_id: UUID | None = None
    stock_order_id: UUID | None = None
    transaction_type_code: str | None = None
    occurred_date_start: date | None = None
    occurred_date_end: date | None = None


class LotOptionQuery(BaseModel):
    item_id: UUID
    warehouse_id: UUID | None = None
    stock_status_code: str = Field(default="available")
    in_stock_only: bool = True
