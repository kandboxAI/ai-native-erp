"""库存余额、流水、批次的只读查询。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, or_, true, false
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import table_scope_condition
from app.framework.datetime_local import local_date_end, local_date_start
from app.modules.organization.models import SysOrg

from ..constants import STOCK_AVAILABLE, STOCK_LENT
from ..warehouse_scope import warehouse_condition
from ..warehouse.access_repository import repository as access_repository
from ..models import (
    InvLot,
    InvItemWarehouseSetting,
    InvStockBalance,
    InvStockOrder,
    InvStockOrderType,
    InvStockTransaction,
    InvWarehouse,
    MdItem,
    MdItemCategory,
)
from .schemas import LotOptionQuery, StockBalanceQuery, StockSummaryQuery, TransactionQuery


def _alert_condition(alert_status: str, available, setting=InvItemWarehouseSetting):
    lower, upper = setting.min_quantity, setting.max_quantity
    out_of_stock = and_(lower.is_not(None), available <= lower, available <= 0)
    low_stock = and_(lower.is_not(None), available > 0, available <= lower)
    overstock = and_(upper.is_not(None), available > upper, or_(lower.is_(None), available > lower))
    if alert_status == "out_of_stock":
        return out_of_stock
    if alert_status == "low_stock":
        return low_stock
    if alert_status == "overstock":
        return overstock
    if alert_status == "replenishment":
        return or_(out_of_stock, low_stock)
    if alert_status == "normal":
        return and_(
            or_(lower.is_not(None), upper.is_not(None)),
            or_(lower.is_(None), available > lower),
            or_(upper.is_(None), available <= upper),
        )
    return and_(lower.is_(None), upper.is_(None))


class StockQueryRepository:
    def _balance_filters(
        self,
        query,
        current_user: AuthenticatedUser,
        scope_permission_key: str = "inventory_item:list",
    ) -> list[Any]:
        active_warehouses = select(InvWarehouse.id).where(
            warehouse_condition(getattr(query, "warehouse_scope_key", None), current_user),
            InvWarehouse.is_active.is_(True),
            InvWarehouse.deleted_at.is_(None),
        )
        conditions: list[Any] = [InvStockBalance.warehouse_id.in_(active_warehouses)]
        scope = table_scope_condition(InvStockBalance, current_user, scope_permission_key)
        if scope is not None:
            conditions.append(scope)
        if query.org_id is not None:
            conditions.append(InvStockBalance.org_id == query.org_id)
        if getattr(query, "warehouse_id", None) is not None:
            conditions.append(InvStockBalance.warehouse_id == query.warehouse_id)
        if query.item_id is not None:
            conditions.append(InvStockBalance.item_id == query.item_id)
        return conditions

    async def summary(
        self,
        session: AsyncSession,
        query: StockSummaryQuery,
        current_user: AuthenticatedUser,
        *,
        scope_permission_key: str = "inventory_item:list",
        warehouse_level: bool = False,
    ) -> tuple[int, list[dict[str, Any]]]:
        available_expr = func.sum(
            case(
                (InvStockBalance.stock_status_code == STOCK_AVAILABLE, InvStockBalance.quantity - InvStockBalance.reserved_quantity),
                else_=0,
            )
        )
        grouped_columns = [InvStockBalance.item_id, InvStockBalance.org_id]
        if warehouse_level:
            grouped_columns.append(InvStockBalance.warehouse_id)
        grouped = select(
            InvStockBalance.item_id.label("item_id"),
            InvStockBalance.org_id.label("org_id"),
            *([InvStockBalance.warehouse_id.label("warehouse_id")] if warehouse_level else []),
            func.sum(InvStockBalance.quantity).label("quantity"),
            available_expr.label("available_quantity"),
            func.sum(case((InvStockBalance.stock_status_code == STOCK_LENT, InvStockBalance.quantity), else_=0)).label("lent_quantity"),
            func.sum(InvStockBalance.reserved_quantity).label("reserved_quantity"),
            func.max(InvStockBalance.updated_at).label("updated_at"),
        )
        grouped = grouped.where(*self._balance_filters(query, current_user, scope_permission_key)).group_by(*grouped_columns)
        if not query.include_zero:
            grouped = grouped.having(func.sum(func.abs(InvStockBalance.quantity)) != 0)
        sub = grouped.subquery()
        conditions: list[Any] = [MdItem.deleted_at.is_(None)]
        if query.category_id is not None:
            conditions.append(MdItem.category_id == query.category_id)
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(or_(MdItem.item_name.ilike(pattern), MdItem.item_no.ilike(pattern), MdItem.specification.ilike(pattern)))
        if query.alert_status and warehouse_level:
            conditions.append(_alert_condition(query.alert_status, sub.c.available_quantity))
        selected = [sub, MdItem, MdItemCategory.category_name, SysOrg.org_name]
        if warehouse_level:
            selected.extend([
                InvWarehouse.warehouse_name,
                InvItemWarehouseSetting.min_quantity,
                InvItemWarehouseSetting.max_quantity,
            ])
        base = select(*selected).join(MdItem, MdItem.id == sub.c.item_id)
        base = base.join(MdItemCategory, MdItemCategory.id == MdItem.category_id, isouter=True).join(SysOrg, SysOrg.id == sub.c.org_id)
        if warehouse_level:
            base = base.join(InvWarehouse, InvWarehouse.id == sub.c.warehouse_id).join(
                InvItemWarehouseSetting,
                and_(
                    InvItemWarehouseSetting.item_id == sub.c.item_id,
                    InvItemWarehouseSetting.warehouse_id == sub.c.warehouse_id,
                    InvItemWarehouseSetting.deleted_at.is_(None),
                ),
                isouter=True,
            )
        base = base.where(*conditions)
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(SysOrg.org_name, MdItem.item_name).limit(query.page_size).offset((query.page - 1) * query.page_size)
            )
        ).all()
        result = []
        for row in rows:
            mapping = row._mapping
            item: MdItem = mapping[MdItem]
            result.append(
                {
                    "item_id": item.id,
                    "org_id": mapping["org_id"],
                    "org_name": mapping["org_name"],
                    **(
                        {
                            "warehouse_id": mapping["warehouse_id"],
                            "warehouse_name": mapping["warehouse_name"],
                        }
                        if warehouse_level
                        else {}
                    ),
                    "item_no": item.item_no,
                    "item_name": item.item_name,
                    "category_id": item.category_id,
                    "category_name": mapping["category_name"],
                    "specification": item.specification,
                    "unit_code": item.unit_code,
                    "unit_price": item.unit_price,
                    "min_quantity": mapping["min_quantity"] if warehouse_level else None,
                    "max_quantity": mapping["max_quantity"] if warehouse_level else None,
                    "quantity": Decimal(mapping["quantity"] or 0),
                    "available_quantity": Decimal(mapping["available_quantity"] or 0),
                    "lent_quantity": Decimal(mapping["lent_quantity"] or 0),
                    "reserved_quantity": Decimal(mapping["reserved_quantity"] or 0),
                    "updated_at": mapping["updated_at"],
                }
            )
        return total or 0, result

    async def balances(self, session: AsyncSession, query: StockBalanceQuery, current_user: AuthenticatedUser) -> tuple[int, list[dict[str, Any]]]:
        conditions = self._balance_filters(query, current_user)
        if query.lot_id is not None:
            conditions.append(InvStockBalance.lot_id == query.lot_id)
        if query.stock_status_code:
            conditions.append(InvStockBalance.stock_status_code == query.stock_status_code)
        if not query.include_zero:
            conditions.append(InvStockBalance.quantity != 0)
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(or_(MdItem.item_name.ilike(pattern), MdItem.item_no.ilike(pattern)))
        base = (
            select(InvStockBalance, MdItem, InvWarehouse, SysOrg.org_name, InvLot)
            .join(MdItem, MdItem.id == InvStockBalance.item_id)
            .join(InvWarehouse, InvWarehouse.id == InvStockBalance.warehouse_id)
            .join(SysOrg, SysOrg.id == InvStockBalance.org_id)
            .join(InvLot, InvLot.id == InvStockBalance.lot_id, isouter=True)
            .where(*conditions)
        )
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(SysOrg.org_name, InvWarehouse.warehouse_no, MdItem.item_name, InvLot.expiry_date.nulls_last())
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        result = []
        for balance, item, warehouse, org_name, lot in rows:
            result.append(
                {
                    "id": balance.id,
                    "org_id": balance.org_id,
                    "org_name": org_name,
                    "item_id": item.id,
                    "item_no": item.item_no,
                    "item_name": item.item_name,
                    "specification": item.specification,
                    "unit_code": item.unit_code,
                    "warehouse_id": warehouse.id,
                    "warehouse_no": warehouse.warehouse_no,
                    "warehouse_name": warehouse.warehouse_name,
                    "lot_id": balance.lot_id,
                    "lot_no": lot.lot_no if lot else None,
                    "production_date": lot.production_date if lot else None,
                    "expiry_date": lot.expiry_date if lot else None,
                    "stock_status_code": balance.stock_status_code,
                    "quantity": balance.quantity,
                    "reserved_quantity": balance.reserved_quantity,
                    "available_quantity": Decimal(balance.quantity) - Decimal(balance.reserved_quantity),
                    "version_no": balance.version_no,
                    "updated_at": balance.updated_at,
                }
            )
        return total or 0, result

    async def transactions(self, session: AsyncSession, query: TransactionQuery, current_user: AuthenticatedUser) -> tuple[int, list[dict[str, Any]]]:
        system_warehouses = select(InvWarehouse.id).where(
            warehouse_condition(getattr(query, "warehouse_scope_key", None), current_user),
        )
        conditions: list[Any] = [
            or_(
                InvStockTransaction.from_warehouse_id.in_(system_warehouses),
                InvStockTransaction.to_warehouse_id.in_(system_warehouses),
            )
        ]
        scope = table_scope_condition(InvStockTransaction, current_user, "inventory_movement:list")
        if scope is not None:
            conditions.append(scope)
        if query.org_id is not None:
            conditions.append(InvStockTransaction.org_id == query.org_id)
        if query.item_id is not None:
            conditions.append(InvStockTransaction.item_id == query.item_id)
        if query.warehouse_id is not None:
            conditions.append(
                or_(InvStockTransaction.from_warehouse_id == query.warehouse_id, InvStockTransaction.to_warehouse_id == query.warehouse_id)
            )
        if query.lot_id is not None:
            conditions.append(InvStockTransaction.lot_id == query.lot_id)
        if query.stock_order_id is not None:
            conditions.append(InvStockTransaction.stock_order_id == query.stock_order_id)
        if query.transaction_type_code:
            conditions.append(InvStockTransaction.transaction_type_code == query.transaction_type_code)
        if query.occurred_date_start is not None:
            conditions.append(InvStockTransaction.occurred_at >= local_date_start(query.occurred_date_start))
        if query.occurred_date_end is not None:
            conditions.append(InvStockTransaction.occurred_at <= local_date_end(query.occurred_date_end))
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(MdItem.item_name.ilike(pattern), MdItem.item_no.ilike(pattern), InvStockTransaction.transaction_no.ilike(pattern))
            )
        base = (
            select(InvStockTransaction, MdItem, InvStockOrder.order_no, InvStockOrderType.type_name, InvStockOrderType.direction_code, InvLot.lot_no)
            .join(MdItem, MdItem.id == InvStockTransaction.item_id)
            .join(InvStockOrder, InvStockOrder.id == InvStockTransaction.stock_order_id)
            .join(InvStockOrderType, InvStockOrderType.id == InvStockOrder.order_type_id)
            .join(InvLot, InvLot.id == InvStockTransaction.lot_id, isouter=True)
            .where(*conditions)
        )
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(InvStockTransaction.occurred_at.desc(), InvStockTransaction.transaction_no.desc())
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        warehouse_ids = {tx.from_warehouse_id for tx, *_ in rows} | {tx.to_warehouse_id for tx, *_ in rows}
        labels = await self.warehouse_labels(session, warehouse_ids)
        result = []
        for tx, item, order_no, type_name, direction_code, lot_no in rows:
            result.append(
                {
                    "id": tx.id,
                    "org_id": tx.org_id,
                    "transaction_no": tx.transaction_no,
                    "transaction_type_code": tx.transaction_type_code,
                    "item_id": item.id,
                    "item_no": item.item_no,
                    "item_name": item.item_name,
                    "specification": item.specification,
                    "unit_code": item.unit_code,
                    "lot_id": tx.lot_id,
                    "lot_no": lot_no,
                    "from_warehouse_id": tx.from_warehouse_id,
                    "from_warehouse_label": labels.get(tx.from_warehouse_id),
                    "to_warehouse_id": tx.to_warehouse_id,
                    "to_warehouse_label": labels.get(tx.to_warehouse_id),
                    "from_stock_status_code": tx.from_stock_status_code,
                    "to_stock_status_code": tx.to_stock_status_code,
                    "quantity": tx.quantity,
                    "stock_order_id": tx.stock_order_id,
                    "stock_order_line_id": tx.stock_order_line_id,
                    "order_no": order_no,
                    "order_type_name": type_name,
                    "direction_code": direction_code,
                    "occurred_at": tx.occurred_at,
                    "created_by": tx.created_by,
                }
            )
        return total or 0, result

    async def warehouse_labels(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, str]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (
            await session.exec(
                select(InvWarehouse.id, InvWarehouse.warehouse_name, SysOrg.org_name)
                .join(SysOrg, SysOrg.id == InvWarehouse.org_id)
                .where(InvWarehouse.id.in_(ids))
            )
        ).all()
        return {row[0]: f"{row[2]} / {row[1]}" for row in rows}

    async def lot_options(self, session: AsyncSession, query: LotOptionQuery, current_user=None, permissions=()) -> list[dict[str, Any]]:
        # 批次选项也必须应用仓库授权，不能通过省略仓库读取其他仓库库存。
        scopes = [table_scope_condition(InvStockBalance, current_user, key) for key in permissions] if current_user else []
        visibility = true() if any(scope is None for scope in scopes) else or_(*scopes) if scopes else false()
        quantity = func.coalesce(func.sum(InvStockBalance.quantity - InvStockBalance.reserved_quantity), 0)
        balance_join = and_(
            InvStockBalance.lot_id == InvLot.id,
            InvStockBalance.stock_status_code == query.stock_status_code,
            visibility,
            *([InvStockBalance.warehouse_id == query.warehouse_id] if query.warehouse_id else []),
        )
        statement = (
            select(InvLot, quantity.label("available_quantity"))
            .join(InvStockBalance, balance_join, isouter=True)
            .where(InvLot.item_id == query.item_id, InvLot.deleted_at.is_(None))
            .group_by(InvLot.id)
            .order_by(InvLot.expiry_date.nulls_last(), InvLot.created_at)
        )
        statement = statement.having(func.count(InvStockBalance.id) > 0)
        if query.in_stock_only:
            statement = statement.having(quantity > 0)
        rows = (await session.exec(statement)).all()
        return [
            {
                "id": lot.id,
                "lot_no": lot.lot_no,
                "production_date": lot.production_date,
                "expiry_date": lot.expiry_date,
                "supplier_id": lot.supplier_id,
                "available_quantity": available,
            }
            for lot, available in rows
        ]


repository = StockQueryRepository()
