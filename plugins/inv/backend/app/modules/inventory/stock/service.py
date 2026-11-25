"""库存查询：汇总加上预警状态与库存价值。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context

from ..warehouse_scope import configurable_scope, get_scope
from ..stock_order.repository import repository as order_repository
from ..valuation import weighted_inventory_value
from ..warning.service import evaluate_stock_alert
from ..warning.notifier import notify_stock_alerts
from ..warning.repository import repository as warning_repository
from ..warning.schemas import StockSettingQuery, StockThresholdUpdate
from ..warning.service import threshold_alert_transitions
from .repository import repository
from .schemas import LotOptionQuery, StockBalanceQuery, StockSummaryQuery, TransactionQuery


def _page(total: int, items: list[dict[str, Any]], query) -> dict[str, Any]:
    return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}


class StockQueryService:
    _ALERT_FIELDS = {
        "item_id",
        "org_id",
        "org_name",
        "warehouse_id",
        "warehouse_name",
        "item_no",
        "item_name",
        "category_id",
        "category_name",
        "specification",
        "unit_code",
        "min_quantity",
        "max_quantity",
        "available_quantity",
        "stock_alert_status",
        "stock_alert_label",
        "suggested_replenishment_quantity",
        "updated_at",
    }

    @classmethod
    def _alert_item(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key in cls._ALERT_FIELDS}

    async def configure_threshold(
        self,
        item_id: UUID,
        warehouse_id: UUID,
        payload: StockThresholdUpdate,
        current_user: AuthenticatedUser,
    ) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await warning_repository.item_warehouse_setting(
                session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                current_user=current_user,
                for_update=True,
            )
            if row is None:
                raise AppException("物料或仓库不存在，或不在当前数据范围内", status_code=status.HTTP_404_NOT_FOUND)
            item, warehouse, setting = row
            scope = configurable_scope(warehouse)
            if scope is not None:
                get_scope(scope.key, current_user)
            previous_min = Decimal(setting.min_quantity) if setting is not None else None
            previous_max = Decimal(setting.max_quantity) if setting is not None else None
            quantity = await warning_repository.available_for_pair(
                session,
                item_id=item_id,
                warehouse_id=warehouse_id,
            )
            setting = await warning_repository.save_setting(
                session,
                setting=setting,
                item_id=item_id,
                warehouse=warehouse,
                min_quantity=payload.min_quantity,
                max_quantity=payload.max_quantity,
                user_id=current_user.user_id,
            )
            alerts = threshold_alert_transitions(
                item,
                org_id=warehouse.org_id,
                warehouse_id=warehouse.id,
                quantity=quantity,
                min_quantity=Decimal(setting.min_quantity),
                max_quantity=Decimal(setting.max_quantity),
                previous_min_quantity=previous_min,
                previous_max_quantity=previous_max,
            )
            if alerts:
                await notify_stock_alerts(
                    session,
                    alerts=alerts,
                    operator_user_id=current_user.user_id,
                    org_names=await order_repository.org_names(session, {warehouse.org_id}),
                    warehouse_names=await order_repository.warehouse_names(session, {warehouse.id}),
                    unit_names=await order_repository.unit_names(session),
                    business_type_code="inventory_item_warehouse_setting",
                    business_id=setting.id,
                    event_id=setting.updated_at.isoformat(),
                )
            await session.commit()
            return {
                "item_id": item.id,
                "warehouse_id": warehouse.id,
                "org_id": warehouse.org_id,
                "min_quantity": setting.min_quantity,
                "max_quantity": setting.max_quantity,
            }

    async def stock_settings(
        self,
        query: StockSettingQuery,
        current_user: AuthenticatedUser,
    ) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await warning_repository.settings(session, query, current_user)
        for row in rows:
            evaluation = evaluate_stock_alert(
                quantity=row["available_quantity"],
                min_quantity=row["min_quantity"],
                max_quantity=row["max_quantity"],
            )
            row["stock_alert_status"] = evaluation.status
            row["stock_alert_label"] = evaluation.label
        return _page(total, rows, query)

    async def summary(
        self,
        query: StockSummaryQuery,
        current_user: AuthenticatedUser,
        *,
        scope_permission_key: str = "inventory_item:list",
        include_valuation: bool = True,
        warehouse_level: bool = False,
    ) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.summary(
                session,
                query,
                current_user,
                scope_permission_key=scope_permission_key,
                warehouse_level=warehouse_level,
            )
            costs = (
                await order_repository.average_costs(session, {row["item_id"] for row in rows})
                if include_valuation
                else {}
            )
        for row in rows:
            evaluation = evaluate_stock_alert(
                quantity=row["available_quantity"], min_quantity=row["min_quantity"], max_quantity=row["max_quantity"]
            )
            row["stock_alert_status"] = evaluation.status
            row["stock_alert_label"] = evaluation.label
            row["suggested_replenishment_quantity"] = evaluation.suggested_replenishment_quantity
            if include_valuation:
                purchased_qty, purchased_value = costs.get(row["item_id"], (Decimal("0"), Decimal("0")))
                if purchased_qty <= 0 and row["unit_price"] is not None:
                    purchased_qty, purchased_value = Decimal("1"), Decimal(row["unit_price"])
                row["inventory_value"] = weighted_inventory_value(
                    stock_quantity=row["quantity"], purchased_quantity=purchased_qty, purchase_value=purchased_value
                )
            else:
                row.pop("unit_price", None)
        return _page(total, rows, query)

    async def low_stock_alerts(
        self,
        query: StockSummaryQuery,
        current_user: AuthenticatedUser,
    ) -> dict[str, Any]:
        result = await self.summary(
            query,
            current_user,
            scope_permission_key="inventory_stock_alert:list",
            include_valuation=False,
            warehouse_level=True,
        )
        result["items"] = [self._alert_item(row) for row in result["items"]]
        return result

    async def alert_detail(
        self,
        item_id: UUID,
        warehouse_id: UUID,
        current_user: AuthenticatedUser,
    ) -> dict[str, Any]:
        scope_permission_key = (
            "inventory_stock_alert:list"
            if "inventory_stock_alert:list" in current_user.permissions
            else "inventory_item:list"
        )
        result = await self.summary(
            StockSummaryQuery(
                item_id=item_id,
                warehouse_id=warehouse_id,
                include_zero=True,
                page=1,
                page_size=1,
            ),
            current_user,
            scope_permission_key=scope_permission_key,
            include_valuation=False,
            warehouse_level=True,
        )
        if not result["items"]:
            raise AppException("库存详情不存在，或不在当前数据范围内", status_code=status.HTTP_404_NOT_FOUND)
        return self._alert_item(result["items"][0])

    async def balances(self, query: StockBalanceQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.balances(session, query, current_user)
        return _page(total, rows, query)

    async def transactions(self, query: TransactionQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.transactions(session, query, current_user)
        return _page(total, rows, query)

    async def lot_options(self, query: LotOptionQuery, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            permissions = [key for key in ("inventory_item:list", "inventory_outbound:create",
                "inventory_transfer:create", "inventory_lend:create", "inventory_damage:create") if key in current_user.permissions]
            return await repository.lot_options(session, query, current_user, permissions)


service = StockQueryService()
