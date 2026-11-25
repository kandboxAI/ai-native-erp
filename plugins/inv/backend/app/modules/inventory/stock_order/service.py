"""库存单据业务：保存、提交、审批、确认（记账）、作废、冲销、借出归还。

权限按单据类型的表单（constants.type_form）对应到原有页面的权限资源：
inventory_inbound / inventory_outbound / inventory_transfer / inventory_lend / inventory_damage / inventory_item（盘点）。
动作：list、detail、create、update、delete、approve、confirm。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.supplier.repository import repository as supplier_repository, supplier_names

from ..common import money, qty
from ..constants import (
    DIRECTION_ADJUST,
    DIRECTION_IN,
    DIRECTION_MOVE,
    DIRECTION_OUT,
    DIRECTION_STATUS,
    FORM_PERMISSION_RESOURCE,
    ORDER_APPROVED,
    ORDER_CONFIRMED,
    ORDER_DRAFT,
    ORDER_SUBMITTED,
    ORDER_VOIDED,
    REQUIRABLE_ORDER_FIELDS,
    type_form,
    type_no_prefix,
    type_permission_resource,
    type_required_fields,
)
from ..models import InvLot, InvStockOrder, InvStockOrderLine, InvStockOrderType
from ..warehouse.repository import warehouse_repository
from ..warehouse.access_repository import repository as access_repository
from ..warning.notifier import notify_stock_alerts
from ..warning.repository import repository as warning_repository
from ..warning.schemas import InboundWarningPreview, ProjectedOverstockWarning
from .confirmation import run_confirmation_validators
from .lifecycle import run_source_document_handlers, run_source_mutation_guards
from ..warehouse_scope import get_scope, configurable_scope
from .posting import post_order
from .repository import repository, type_item, type_repository
from .rules import fixed_order_type, validate_stock_statuses
from .schemas import (
    OrderBatchCreate,
    OrderCreate,
    OrderLineListQuery,
    OrderLineWrite,
    OrderListQuery,
    OrderTypeItem,
    OrderTypeOptionQuery,
    OrderUpdate,
    ReturnCreate,
)
from .write_validation import run_write_validators
from .tracking import read_tracking, save_tracking

HEADER_FIELDS = (
    "business_date",
    "from_warehouse_id",
    "to_warehouse_id",
    "counterparty_party_id",
    "counterparty_name_snapshot",
    "department_id",
    "purpose",
    "reason",
    "handling_method_code",
    "expected_return_date",
    "source_doc_type_code",
    "source_doc_id",
    "currency_code",
    "remark",
)


def _forbidden(permission: str) -> AppException:
    return AppException(f"missing permissions: {permission}", status_code=status.HTTP_403_FORBIDDEN)


def require_type_permission(current_user: AuthenticatedUser, order_type: InvStockOrderType, action: str) -> str:
    config = getattr(order_type, "required_field_config", None) or {}
    get_scope(config.get("warehouse_scope_key"), current_user)
    permission = f"{type_permission_resource(order_type)}:{action}"
    inbound_menu_permission = "inventory_inbound:list"
    if permission in current_user.permissions:
        return permission
    if type_form(order_type) == "inbound" and inbound_menu_permission in current_user.permissions:
        return inbound_menu_permission
    raise _forbidden(permission)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (UUID, date)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    return value


class StockOrderService:
    async def type_options(self, query: OrderTypeOptionQuery, current_user: AuthenticatedUser) -> list[OrderTypeItem]:
        get_scope(query.warehouse_scope_key, current_user)
        async with get_session_context() as session:
            items = await type_repository.options(session, form=query.form,
                direction_code=query.direction_code, include_inactive=query.include_inactive)
        return [item for item in items
            if (item.required_field_config or {}).get("warehouse_scope_key") in (None, query.warehouse_scope_key)]

    async def source_document_order_stats_in_session(
        self,
        session: AsyncSession,
        *,
        source_doc_type_code: str,
        source_doc_ids: set[UUID],
    ) -> dict[UUID, dict[str, int]]:
        """供来源业务批量读取关联库存单据的生命周期统计。"""

        return await repository.source_document_order_stats(
            session,
            source_doc_type_code=source_doc_type_code,
            source_doc_ids=source_doc_ids,
        )

    async def source_document_item_quantities_in_session(
        self,
        session: AsyncSession,
        *,
        source_doc_type_code: str,
        source_doc_id: UUID,
        confirmed_only: bool,
    ) -> dict[UUID, Decimal]:
        """供来源业务在现有事务内读取库存单据净数量。"""

        return await repository.source_document_item_quantities(
            session,
            source_doc_type_code=source_doc_type_code,
            source_doc_id=source_doc_id,
            confirmed_only=confirmed_only,
        )

    async def outstanding_lends_for_party(
        self, session: AsyncSession, *, org_id: UUID, party_id: UUID
    ) -> list[dict[str, Any]]:
        """跨模块只读契约：返回某主体尚未归还的库存借用明细。"""
        rows = await repository.outstanding_lends_for_party(
            session, org_id=org_id, party_id=party_id
        )
        return [
            {
                "source_line_id": line.id,
                "order_id": order.id,
                "order_no": order.order_no,
                "item_id": item.id,
                "item_no": item.item_no,
                "item_name": item.item_name,
                "specification": item.specification,
                "quantity": quantity,
                "unit_code": line.unit_code,
            }
            for line, order, item, quantity in rows
        ]

    # ───────── 读取与权限 ─────────
    async def _get_type(self, session: AsyncSession, type_id: UUID, *, active_only: bool = True) -> InvStockOrderType:
        order_type = await type_repository.get(session, type_id)
        if order_type is not None:
            order_type = fixed_order_type(order_type, require_supported=active_only)
        if order_type is None or (active_only and not order_type.is_active):
            raise AppException("单据类型不存在或已停用", status_code=status.HTTP_400_BAD_REQUEST)
        return order_type

    async def _load(
        self,
        session: AsyncSession,
        order_id: UUID,
        current_user: AuthenticatedUser,
        action: str,
        *,
        for_update: bool = False,
    ) -> tuple[InvStockOrder, InvStockOrderType]:
        order = await repository.get_order(session, order_id, for_update=for_update)
        if order is None:
            raise AppException("库存单据不存在", status_code=status.HTTP_404_NOT_FOUND)
        order_type = await self._get_type(session, order.order_type_id, active_only=False)
        permission = require_type_permission(current_user, order_type, action)
        condition = repository.scope_condition(current_user, permission)
        if condition is not None:
            visible = (await session.exec(select(InvStockOrder.id).where(InvStockOrder.id == order.id, condition))).first()
            if visible is None:
                raise AppException("库存单据不存在", status_code=status.HTTP_404_NOT_FOUND)
        if for_update:
            await run_source_mutation_guards(session, order, current_user, action)
        return order, order_type

    def _scopes_for_list(self, current_user: AuthenticatedUser, types: dict[UUID, InvStockOrderType], query: OrderListQuery):
        """按权限资源分组的 (类型 ID 列表, 数据范围条件)。"""
        get_scope(getattr(query, "warehouse_scope_key", None), current_user)
        grouped: dict[str, list[UUID]] = {}
        for order_type in types.values():
            if query.form and type_form(order_type) != query.form:
                continue
            if query.direction_code and order_type.direction_code != query.direction_code:
                continue
            grouped.setdefault(type_permission_resource(order_type), []).append(order_type.id)
        result = []
        for resource, type_ids in grouped.items():
            permission = f"{resource}:list"
            if permission not in current_user.permissions:
                continue
            result.append((type_ids, repository.scope_condition(current_user, permission)))
        if query.form and not result:
            resource = FORM_PERMISSION_RESOURCE.get(query.form, query.form)
            raise _forbidden(f"{resource}:list")
        return result

    # ───────── 序列化 ─────────
    async def _serialize_orders(self, session: AsyncSession, orders: list[InvStockOrder], *, with_lines: bool) -> list[dict[str, Any]]:
        if not orders:
            return []
        types = await type_repository.get_many(session, {order.order_type_id for order in orders})
        warehouses = await repository.warehouse_labels(session, {o.from_warehouse_id for o in orders} | {o.to_warehouse_id for o in orders})
        orgs = await repository.org_names(session, {order.org_id for order in orders})
        departments = await repository.department_names(session, {order.department_id for order in orders})
        users = await repository.user_names(
            session, {o.created_by for o in orders} | {o.confirmed_by for o in orders} | {o.voided_by for o in orders}
        )
        stats = await repository.line_stats(session, [order.id for order in orders])
        result = []
        for order in orders:
            order_type = types.get(order.order_type_id)
            data = {column: _json(getattr(order, column)) for column in InvStockOrder.model_fields}
            data.update(
                {
                    "order_type": type_item(order_type).model_dump(mode="json") if order_type else None,
                    "order_type_name": order_type.type_name if order_type else None,
                    "direction_code": order_type.direction_code if order_type else None,
                    "form": type_form(order_type) if order_type else None,
                    "org_name": orgs.get(order.org_id),
                    "from_warehouse": warehouses.get(order.from_warehouse_id),
                    "to_warehouse": warehouses.get(order.to_warehouse_id),
                    "department_name": departments.get(order.department_id),
                    "created_by_name": users.get(order.created_by),
                    "confirmed_by_name": users.get(order.confirmed_by),
                    "voided_by_name": users.get(order.voided_by),
                    "line_count": stats.get(order.id, {}).get("line_count", 0),
                    "total_quantity": _json(stats.get(order.id, {}).get("total_quantity", 0)),
                    "item_names": stats.get(order.id, {}).get("item_names", ""),
                    "item_summaries": [
                        _json_dict(line) for line in stats.get(order.id, {}).get("item_summaries", [])
                    ],
                }
            )
            data["from_warehouse"] = _json_dict(data["from_warehouse"])
            data["to_warehouse"] = _json_dict(data["to_warehouse"])
            result.append(data)
        if with_lines:
            for data, order in zip(result, orders):
                data["lines"] = await self._serialize_lines(session, order, await repository.get_lines(session, order.id))
                data["related_orders"] = await self._related_orders(session, order, data["lines"])
        return result

    async def _serialize_lines(self, session: AsyncSession, order: InvStockOrder, lines: list[InvStockOrderLine]) -> list[dict[str, Any]]:
        items = await repository.items(session, {line.item_id for line in lines})
        lots = await repository.get_lots(session, {line.lot_id for line in lines})
        warehouses = await repository.warehouse_labels(session, {l.from_warehouse_id for l in lines} | {l.to_warehouse_id for l in lines})
        returned = await repository.returned_quantities(session, {line.id for line in lines}) if order.status_code == ORDER_CONFIRMED else {}
        transactions = await repository.line_transactions(session, {line.id for line in lines}) if order.status_code == ORDER_CONFIRMED else []
        tx_lots = await repository.get_lots(session, {tx.lot_id for tx in transactions})
        tx_by_line: dict[UUID, list[dict[str, Any]]] = {}
        for tx in transactions:
            tx_by_line.setdefault(tx.stock_order_line_id, []).append(
                {
                    "id": str(tx.id),
                    "transaction_no": tx.transaction_no,
                    "transaction_type_code": tx.transaction_type_code,
                    "lot_id": str(tx.lot_id) if tx.lot_id else None,
                    "lot_no": tx_lots[tx.lot_id].lot_no if tx.lot_id in tx_lots else None,
                    "from_warehouse_id": str(tx.from_warehouse_id) if tx.from_warehouse_id else None,
                    "to_warehouse_id": str(tx.to_warehouse_id) if tx.to_warehouse_id else None,
                    "from_stock_status_code": tx.from_stock_status_code,
                    "to_stock_status_code": tx.to_stock_status_code,
                    "quantity": str(tx.quantity),
                    "occurred_at": tx.occurred_at.isoformat(),
                }
            )
        result = []
        for line in lines:
            item = items.get(line.item_id)
            lot = lots.get(line.lot_id)
            data = {column: _json(getattr(line, column)) for column in InvStockOrderLine.model_fields}
            returned_qty = returned.get(line.id, Decimal("0"))
            data.update(
                {
                    "item_no": item.item_no if item else None,
                    "item_name": item.item_name if item else None,
                    "is_asset_managed": item.is_asset_managed if item else False,
                    "default_asset_type_code": item.default_asset_type_code if item else None,
                    "default_asset_management_mode_code": "individual" if item and item.is_asset_managed else None,
                    "specification": item.specification if item else None,
                    "lot_no": lot.lot_no if lot else None,
                    "production_date": lot.production_date.isoformat() if lot and lot.production_date else None,
                    "expiry_date": lot.expiry_date.isoformat() if lot and lot.expiry_date else None,
                    "from_warehouse": _json_dict(warehouses.get(line.from_warehouse_id)),
                    "to_warehouse": _json_dict(warehouses.get(line.to_warehouse_id)),
                    "returned_quantity": str(returned_qty),
                    "unreturned_quantity": str(max(Decimal(line.quantity) - returned_qty, Decimal("0"))),
                    "transactions": tx_by_line.get(line.id, []),
                    "tracking": await read_tracking(session, line),
                }
            )
            result.append(data)
        return result

    async def _related_orders(self, session: AsyncSession, order: InvStockOrder, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        related = await repository.return_orders_of(session, {UUID(line["id"]) for line in lines})
        if order.reversal_of_order_id is not None:
            original = await repository.get_order(session, order.reversal_of_order_id)
            if original is not None:
                related.append(original)
        reversals = (await session.exec(select(InvStockOrder).where(InvStockOrder.reversal_of_order_id == order.id))).all()
        related.extend(reversals)
        return [
            {
                "id": str(item.id),
                "order_no": item.order_no,
                "status_code": item.status_code,
                "business_date": item.business_date.isoformat(),
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
                "is_reversal": item.reversal_of_order_id is not None,
            }
            for item in related
        ]

    async def _detail(self, session: AsyncSession, order: InvStockOrder) -> dict[str, Any]:
        return (await self._serialize_orders(session, [order], with_lines=True))[0]

    # ───────── 查询 ─────────
    async def list_orders(self, query: OrderListQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            types = await type_repository.get_many(session)
            scopes = self._scopes_for_list(current_user, types, query)
            total, orders = await repository.list_orders(session, query, scopes, current_user)
            items = await self._serialize_orders(session, orders, with_lines=False)
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def list_lines(self, query: OrderLineListQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            types = await type_repository.get_many(session)
            scopes = self._scopes_for_list(current_user, types, query)
            total, rows = await repository.list_lines(session, query, scopes, query.item_keyword, current_user)
            orders = {order.id: order for _line, order in rows}
            headers = {item["id"]: item for item in await self._serialize_orders(session, list(orders.values()), with_lines=False)}
            serialized: dict[UUID, dict[str, Any]] = {}
            for order_id, order in orders.items():
                order_lines = [line for line, line_order in rows if line_order.id == order_id]
                for data in await self._serialize_lines(session, order, order_lines):
                    serialized[UUID(data["id"])] = data
            items = []
            for line, order in rows:
                line_data = serialized[line.id]
                line_data.pop("transactions", None)
                line_data["order"] = headers[str(order.id)]
                items.append(line_data)
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def detail(self, order_id: UUID, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            order, _ = await self._load(session, order_id, current_user, "detail")
            return await self._detail(session, order)

    async def personnel_options(self, org_id: UUID | None) -> dict[str, Any]:
        async with get_session_context() as session:
            return await repository.personnel_options(session, org_id)

    # ───────── 保存 ─────────
    async def _new_order_no(self, session: AsyncSession, order_type: InvStockOrderType) -> str:
        today = local_now().strftime("%Y%m%d")
        for _ in range(5):
            order_no = f"{type_no_prefix(order_type)}{today}{uuid7().hex[-6:].upper()}"
            if not await repository.order_no_exists(session, order_no):
                return order_no
        raise AppException("生成单号失败，请重试", status_code=status.HTTP_409_CONFLICT)

    async def _apply_header(
        self,
        session: AsyncSession,
        order: InvStockOrder,
        order_type: InvStockOrderType,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
        permission: str,
        *,
        is_create: bool,
    ) -> UUID | None:
        """写入单据头字段；返回供应商 ID（入库时记录到新批次）。"""
        for field in HEADER_FIELDS:
            if field in payload:
                setattr(order, field, payload[field])
        supplier_id = payload.get("supplier_id")
        if supplier_id is not None:
            supplier = await supplier_repository.get_alive(session, supplier_id)
            if supplier is None:
                raise AppException("供应商不存在", status_code=status.HTTP_400_BAD_REQUEST)
            order.counterparty_party_id = supplier.party_id
            order.counterparty_name_snapshot = (await supplier_names(session, {supplier.id})).get(supplier.id)
            order.flex_form = {**(order.flex_form or {}), "supplier_id": str(supplier.id)}
        if payload.get("counterparty_user_id") is not None:
            party_id, name = await repository.user_party(session, payload["counterparty_user_id"])
            order.counterparty_party_id = party_id
            order.counterparty_name_snapshot = payload.get("counterparty_name_snapshot") or name
            order.flex_form = {**(order.flex_form or {}), "counterparty_user_id": str(payload["counterparty_user_id"])}
        if order.department_id is not None and "department_id" in payload and not await repository.department_exists(session, order.department_id):
            raise AppException("领用部门不存在", status_code=status.HTTP_400_BAD_REQUEST)

        direction = order_type.direction_code
        if direction == DIRECTION_IN:
            order.from_warehouse_id = None
        elif direction in (DIRECTION_OUT,):
            order.to_warehouse_id = None
        warehouses = await repository.get_warehouses(session, {order.from_warehouse_id, order.to_warehouse_id})
        for warehouse_id in (order.from_warehouse_id, order.to_warehouse_id):
            if warehouse_id is not None and warehouse_id not in warehouses:
                raise AppException("仓库不存在", status_code=status.HTTP_400_BAD_REQUEST)
        # 单据组织：来源仓库所属组织，入库取目标仓库所属组织；也可显式传入
        anchor = order.from_warehouse_id if direction in (DIRECTION_OUT, DIRECTION_MOVE, DIRECTION_STATUS) else order.to_warehouse_id
        anchor = anchor or order.from_warehouse_id or order.to_warehouse_id
        org_id = payload.get("org_id") or (warehouses[anchor].org_id if anchor in warehouses else None) or order.org_id
        if is_create or payload.get("org_id") is not None or anchor in warehouses:
            order.org_id = resolve_write_org_id(current_user, org_id, permission)
        if order.business_date is None:
            order.business_date = local_now().date()
        if not order.currency_code:
            order.currency_code = "CNY"
        return UUID(order.flex_form["supplier_id"]) if (order.flex_form or {}).get("supplier_id") else None

    async def _validate_line_warehouses(
        self,
        session: AsyncSession,
        order: InvStockOrder,
        order_type: InvStockOrderType,
        lines: list[InvStockOrderLine],
        current_user: AuthenticatedUser,
        permission: str,
    ) -> None:
        warehouse_ids = {order.from_warehouse_id, order.to_warehouse_id}
        for line in lines:
            warehouse_ids.update({line.from_warehouse_id, line.to_warehouse_id})
        warehouse_ids.discard(None)
        warehouses = await warehouse_repository.get_many(session, warehouse_ids, lock=True)
        if set(warehouses) != warehouse_ids:
            raise AppException("单据明细包含不存在或已停用的仓库", status_code=status.HTTP_400_BAD_REQUEST)
        configured = [configurable_scope(row) for row in warehouses.values()]
        if any(configured):
            if current_user is None: raise AppException("业务仓库操作必须校验当前用户", 403)
            for scope in configured:
                if scope is not None: get_scope(scope.key, current_user)
            if not all(configured) or len({scope.key for scope in configured}) != 1:
                raise AppException("本次单据不能混用系统仓库与业务仓库")
            if any(warehouse.org_id != order.org_id for warehouse in warehouses.values()):
                raise AppException("业务仓库必须与单据所属组织一致", 403)
        for warehouse in warehouses.values():
            ensure_org_access(current_user, warehouse.org_id, permission)
            if not await access_repository.can_access(session, warehouse.id, current_user, permission):
                raise AppException("无权操作单据中的仓库", status_code=403)
        if getattr(order_type, "direction_code", None) == DIRECTION_MOVE:
            for line in lines:
                source = line.from_warehouse_id or order.from_warehouse_id
                target = line.to_warehouse_id or order.to_warehouse_id
                if source is not None and source == target:
                    raise AppException("调拨来源与目标仓库不能相同", status_code=status.HTTP_400_BAD_REQUEST)

    async def _build_lines(
        self,
        session: AsyncSession,
        order: InvStockOrder,
        order_type: InvStockOrderType,
        lines: list[OrderLineWrite],
        current_user: AuthenticatedUser,
        supplier_id: UUID | None,
        permission: str,
        *, use_reference_price: bool = True,
    ) -> list[InvStockOrderLine]:
        fixed_order_type(order_type, require_supported=True)
        validate_stock_statuses(order_type, lines)
        items = await repository.items(session, {line.item_id for line in lines})
        direction = order_type.direction_code
        source_lines = await repository.get_lines_by_ids(session, {line.source_line_id for line in lines if line.source_line_id})
        result: list[InvStockOrderLine] = []
        for index, payload in enumerate(lines, start=1):
            item = items.get(payload.item_id)
            if item is None or item.deleted_at is not None:
                raise AppException(f"第 {index} 行物料不存在", status_code=status.HTTP_400_BAD_REQUEST)
            if not item.is_active:
                raise AppException(f"第 {index} 行物料「{item.item_name}」已停用", status_code=status.HTTP_400_BAD_REQUEST)
            quantity = qty(payload.quantity) if payload.quantity is not None else Decimal("0")
            if direction == DIRECTION_ADJUST:
                if payload.counted_quantity is None:
                    raise AppException(f"第 {index} 行缺少实盘数量", status_code=status.HTTP_400_BAD_REQUEST)
            elif quantity <= 0:
                raise AppException(f"第 {index} 行数量必须大于 0", status_code=status.HTTP_400_BAD_REQUEST)
            lot_id = payload.lot_id
            if lot_id is None and direction in (DIRECTION_IN, DIRECTION_ADJUST):
                lot_no = (payload.lot_no or "").strip() or (order.order_no if item.is_lot_controlled and direction == DIRECTION_IN else "")
                if lot_no:
                    lot = await repository.find_lot(session, item.id, lot_no)
                    if lot is None:
                        lot = await repository.add_lot(
                            session,
                            InvLot(
                                org_id=order.org_id,
                                item_id=item.id,
                                lot_no=lot_no,
                                production_date=payload.production_date,
                                expiry_date=payload.expiry_date,
                                supplier_id=supplier_id,
                                created_by=current_user.user_id,
                                updated_by=current_user.user_id,
                            ),
                        )
                    lot_id = lot.id
            elif lot_id is None and payload.lot_no:
                lot = await repository.find_lot(session, item.id, payload.lot_no.strip())
                if lot is None:
                    raise AppException(f"第 {index} 行批次「{payload.lot_no}」不存在", status_code=status.HTTP_400_BAD_REQUEST)
                lot_id = lot.id
            if payload.source_line_id is not None:
                source = source_lines.get(payload.source_line_id)
                if source is None or source.item_id != item.id:
                    raise AppException(f"第 {index} 行关联明细无效", status_code=status.HTTP_400_BAD_REQUEST)
            unit_price = payload.unit_price if payload.unit_price is not None else (item.unit_price if direction == DIRECTION_IN and use_reference_price else None)
            result.append(
                InvStockOrderLine(
                    org_id=order.org_id,
                    line_no=index,
                    item_id=item.id,
                    lot_id=lot_id,
                    from_warehouse_id=payload.from_warehouse_id,
                    to_warehouse_id=payload.to_warehouse_id,
                    from_stock_status_code=payload.from_stock_status_code,
                    to_stock_status_code=payload.to_stock_status_code,
                    quantity=quantity,
                    unit_code=payload.unit_code or item.unit_code,
                    unit_price=money(unit_price) if unit_price is not None else None,
                    amount=money(Decimal(unit_price) * quantity) if unit_price is not None else None,
                    source_line_id=payload.source_line_id,
                    counted_quantity=qty(payload.counted_quantity) if payload.counted_quantity is not None else None,
                    remark=payload.remark,
                    created_by=current_user.user_id,
                    updated_by=current_user.user_id,
                )
            )
        amounts = [line.amount for line in result if line.amount is not None]
        order.total_amount = money(sum(amounts, Decimal("0"))) if amounts else None
        await self._validate_line_warehouses(session, order, order_type, result, current_user, permission)
        from ..products.warehouse_service import validate_inbound_warehouses
        await validate_inbound_warehouses(session, order, order_type, result)
        await run_write_validators(session, order, order_type, result, current_user)
        return result

    def _validate_required(self, order: InvStockOrder, order_type: InvStockOrderType, lines: list[InvStockOrderLine]) -> None:
        missing = [REQUIRABLE_ORDER_FIELDS[field] for field in type_required_fields(order_type) if getattr(order, field) in (None, "")]
        if missing:
            raise AppException(f"{order_type.type_name}需要填写：{'、'.join(missing)}", status_code=status.HTTP_400_BAD_REQUEST)
        if not lines:
            raise AppException("单据没有明细", status_code=status.HTTP_400_BAD_REQUEST)
        direction = order_type.direction_code
        for line in lines:
            from_warehouse = line.from_warehouse_id or order.from_warehouse_id
            to_warehouse = line.to_warehouse_id or order.to_warehouse_id
            if direction in (DIRECTION_OUT, DIRECTION_MOVE) and from_warehouse is None:
                raise AppException(f"第 {line.line_no} 行缺少来源仓库", status_code=status.HTTP_400_BAD_REQUEST)
            if direction in (DIRECTION_IN, DIRECTION_MOVE) and to_warehouse is None:
                raise AppException(f"第 {line.line_no} 行缺少目标仓库", status_code=status.HTTP_400_BAD_REQUEST)
            if direction in (DIRECTION_STATUS, DIRECTION_ADJUST) and from_warehouse is None and to_warehouse is None:
                raise AppException(f"第 {line.line_no} 行缺少仓库", status_code=status.HTTP_400_BAD_REQUEST)

    async def _create_in_session(self, session: AsyncSession, payload: OrderCreate, current_user: AuthenticatedUser, *, use_reference_price: bool = True) -> InvStockOrder:
        order_type = await self._get_type(session, payload.order_type_id)
        permission = require_type_permission(current_user, order_type, "create")
        order = InvStockOrder(
            order_no=await self._new_order_no(session, order_type),
            order_type_id=order_type.id,
            status_code=ORDER_DRAFT,
            business_date=payload.business_date or local_now().date(),
            created_by=current_user.user_id,
            updated_by=current_user.user_id,
        )
        data = payload.model_dump(exclude_unset=True)
        supplier_id = await self._apply_header(session, order, order_type, data, current_user, permission, is_create=True)
        lines = await self._build_lines(session, order, order_type, payload.lines, current_user, supplier_id, permission, use_reference_price=use_reference_price)
        await repository.add_order(session, order, lines)
        await save_tracking(session, order, lines, payload.lines, current_user)
        if payload.confirm:
            await self._confirm_locked(session, order, order_type, current_user)
        elif payload.submit:
            self._submit(order, order_type, lines, current_user)
        await session.flush()
        return order

    async def create(self, payload: OrderCreate, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            order = await self._create_in_session(session, payload, current_user)
            await session.commit()
            return await self._detail(session, order)

    async def create_in_session(self, session: AsyncSession, payload: OrderCreate, current_user: AuthenticatedUser, *, use_reference_price: bool = True) -> InvStockOrder:
        """公开组合事务写入；不提交，由调用方完成完整业务动作。"""
        return await self._create_in_session(session, payload, current_user, use_reference_price=use_reference_price)

    async def batch_create(self, payload: OrderBatchCreate, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            orders = [await self._create_in_session(session, item, current_user) for item in payload.orders]
            await session.commit()
            items = await self._serialize_orders(session, orders, with_lines=False)
        return {"items": items, "count": len(items)}

    async def update(self, order_id: UUID, payload: OrderUpdate, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            order, order_type = await self._load(session, order_id, current_user, "update", for_update=True)
            if order.status_code != ORDER_DRAFT:
                raise AppException("只有草稿状态的单据可以修改", status_code=status.HTTP_409_CONFLICT)
            data = payload.model_dump(exclude_unset=True)
            permission = require_type_permission(current_user, order_type, "update")
            supplier_id = await self._apply_header(session, order, order_type, data, current_user, permission, is_create=False)
            if payload.lines is not None:
                lines = await self._build_lines(session, order, order_type, payload.lines, current_user, supplier_id, permission)
                await repository.replace_lines(session, order, lines)
                await save_tracking(session, order, lines, payload.lines, current_user)
            order.updated_by = current_user.user_id
            order.updated_at = utc_now()
            session.add(order)
            await session.commit()
            return await self._detail(session, order)

    async def delete(self, order_id: UUID, current_user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            order, _ = await self._load(session, order_id, current_user, "delete", for_update=True)
            if order.status_code != ORDER_DRAFT:
                raise AppException("只有草稿可以删除；已提交的单据请作废", status_code=status.HTTP_409_CONFLICT)
            await repository.delete_order(session, order)
            await session.commit()
            return True

    # ───────── 状态流转 ─────────
    def _submit(self, order: InvStockOrder, order_type: InvStockOrderType, lines: list[InvStockOrderLine], current_user: AuthenticatedUser) -> None:
        order_type = fixed_order_type(order_type, require_supported=True)
        validate_stock_statuses(order_type, lines)
        if order.status_code != ORDER_DRAFT:
            raise AppException("只有草稿可以提交", status_code=status.HTTP_409_CONFLICT)
        self._validate_required(order, order_type, lines)
        order.status_code = ORDER_SUBMITTED if order_type.is_approval_required else ORDER_APPROVED
        order.updated_by = current_user.user_id
        order.updated_at = utc_now()

    async def _transition(self, order_id: UUID, current_user: AuthenticatedUser, action: str, handler) -> dict[str, Any]:
        async with get_session_context() as session:
            order, order_type = await self._load(session, order_id, current_user, action, for_update=True)
            await handler(session, order, order_type)
            session.add(order)
            await session.commit()
            return await self._detail(session, order)

    async def submit(self, order_id: UUID, current_user: AuthenticatedUser) -> dict[str, Any]:
        async def handler(session, order, order_type):
            lines = await repository.get_lines(session, order.id)
            await self._validate_line_warehouses(session, order, order_type, lines, current_user, require_type_permission(current_user, order_type, "create"))
            self._submit(order, order_type, lines, current_user)

        return await self._transition(order_id, current_user, "create", handler)

    async def approve(self, order_id: UUID, current_user: AuthenticatedUser) -> dict[str, Any]:
        async def handler(session, order, order_type):
            if order.status_code != ORDER_SUBMITTED:
                raise AppException("只有待审批的单据可以审批", status_code=status.HTTP_409_CONFLICT)
            order.status_code = ORDER_APPROVED
            order.updated_by = current_user.user_id
            order.updated_at = utc_now()

        return await self._transition(order_id, current_user, "approve", handler)

    async def reject(self, order_id: UUID, reason: str | None, current_user: AuthenticatedUser) -> dict[str, Any]:
        async def handler(session, order, order_type):
            if order.status_code != ORDER_SUBMITTED:
                raise AppException("只有待审批的单据可以驳回", status_code=status.HTTP_409_CONFLICT)
            order.status_code = ORDER_DRAFT
            order.flex_form = {**(order.flex_form or {}), "reject_reason": reason or ""}
            order.updated_by = current_user.user_id
            order.updated_at = utc_now()

        return await self._transition(order_id, current_user, "approve", handler)

    async def void(self, order_id: UUID, reason: str | None, current_user: AuthenticatedUser) -> dict[str, Any]:
        async def handler(session, order, order_type):
            if order.status_code in (ORDER_CONFIRMED, ORDER_VOIDED):
                raise AppException("已确认或已作废的单据不能作废；已确认的单据请冲销", status_code=status.HTTP_409_CONFLICT)
            lines = await repository.get_lines(session, order.id)
            order.status_code = ORDER_VOIDED
            order.voided_at = utc_now()
            order.voided_by = current_user.user_id
            order.void_reason = reason
            order.updated_by = current_user.user_id
            order.updated_at = utc_now()
            session.add(order)
            await session.flush()
            await run_source_document_handlers(session, order, order_type, lines, current_user)

        return await self._transition(order_id, current_user, "update", handler)

    async def _confirm_locked(self, session: AsyncSession, order: InvStockOrder, order_type: InvStockOrderType, current_user: AuthenticatedUser) -> dict[str, Any]:
        order_type = fixed_order_type(order_type, require_supported=order.reversal_of_order_id is None)
        permission = require_type_permission(current_user, order_type, "confirm")
        lines = await repository.get_lines(session, order.id)
        await self._validate_line_warehouses(session, order, order_type, lines, current_user, permission)
        if order.status_code == ORDER_DRAFT and not order_type.is_approval_required:
            self._submit(order, order_type, lines, current_user)
        if order.status_code == ORDER_SUBMITTED:
            raise AppException("单据尚未审批，不能确认", status_code=status.HTTP_409_CONFLICT)
        if order.status_code != ORDER_APPROVED:
            raise AppException(f"当前状态（{order.status_code}）不能确认", status_code=status.HTTP_409_CONFLICT)
        self._validate_required(order, order_type, lines)
        await run_confirmation_validators(session, order, order_type, lines, current_user)
        from ..products.warehouse_service import validate_inbound_warehouses
        await validate_inbound_warehouses(session, order, order_type, lines)
        result = await post_order(session, order, order_type, lines, current_user.user_id, current_user=current_user)
        order.status_code = ORDER_CONFIRMED
        order.confirmed_at = utc_now()
        order.confirmed_by = current_user.user_id
        order.updated_by = current_user.user_id
        order.updated_at = utc_now()
        session.add(order)
        for line in lines:
            session.add(line)
        await session.flush()
        await run_source_document_handlers(session, order, order_type, lines, current_user)
        await repository.add_outbox_event(
            session,
            payload={
                "stock_order_id": str(order.id),
                "order_no": order.order_no,
                "order_type_id": str(order_type.id),
                "order_type_name": order_type.type_name,
                "direction_code": order_type.direction_code,
                "org_id": str(order.org_id),
                "confirmed_by": str(current_user.user_id),
                "confirmed_at": order.confirmed_at.isoformat(),
                "transaction_count": result["transaction_count"],
                "stock_alerts": result["alerts"],
                "source_doc_type_code": order.source_doc_type_code,
                "source_doc_id": str(order.source_doc_id) if order.source_doc_id else None,
                "reversal_of_order_id": (
                    str(order.reversal_of_order_id) if order.reversal_of_order_id else None
                ),
                "redirect_url": "/logistics-management/warehouse/ledger",
            },
            user_id=current_user.user_id,
        )
        if result["alerts"]:
            await notify_stock_alerts(
                session,
                alerts=result["alerts"],
                stock_order_id=order.id,
                operator_user_id=current_user.user_id,
                org_names=await repository.org_names(session, {UUID(alert["org_id"]) for alert in result["alerts"]}),
                warehouse_names=await repository.warehouse_names(
                    session,
                    {UUID(alert["warehouse_id"]) for alert in result["alerts"]},
                ),
                unit_names=await repository.unit_names(session),
            )
        return result

    async def confirm(self, order_id: UUID, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            order, order_type = await self._load(session, order_id, current_user, "confirm", for_update=True)
            result = await self._confirm_locked(session, order, order_type, current_user)
            await session.commit()
            detail = await self._detail(session, order)
            detail["stock_alerts"] = result["alerts"]
            return detail

    async def confirm_in_session(self, session: AsyncSession, order_id: UUID, current_user: AuthenticatedUser) -> InvStockOrder:
        """供导入、演示数据在同一会话中确认（调用方提交事务）。"""
        order, order_type = await self._load(session, order_id, current_user, "confirm", for_update=True)
        await self._confirm_locked(session, order, order_type, current_user)
        return order

    async def reverse(self, order_id: UUID, reason: str | None, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            reversal = await self.reverse_in_session(session, order_id, reason, current_user)
            await session.commit()
            return await self._detail(session, reversal)

    async def reverse_in_session(self, session: AsyncSession, order_id: UUID, reason: str | None, current_user: AuthenticatedUser) -> InvStockOrder:
        """在调用方事务内冲销；校验、记账和来源处理器与原入口一致，不提交。"""
        original, order_type = await self._load(session, order_id, current_user, "confirm", for_update=True)
        if original.status_code != ORDER_CONFIRMED or original.reversal_of_order_id is not None:
            raise AppException("只有已确认的原单据可以冲销", status_code=status.HTTP_409_CONFLICT)
        existing = (
            await session.exec(
                select(InvStockOrder.id).where(InvStockOrder.reversal_of_order_id == original.id, InvStockOrder.status_code != ORDER_VOIDED)
            )
        ).first()
        if existing is not None:
            raise AppException("该单据已冲销", status_code=status.HTTP_409_CONFLICT)
        reversal = InvStockOrder(
            order_no=f"{original.order_no}-CX",
            order_type_id=original.order_type_id,
            status_code=ORDER_APPROVED,
            business_date=local_now().date(),
            org_id=original.org_id,
            from_warehouse_id=original.from_warehouse_id,
            to_warehouse_id=original.to_warehouse_id,
            counterparty_party_id=original.counterparty_party_id,
            counterparty_name_snapshot=original.counterparty_name_snapshot,
            department_id=original.department_id,
            purpose=original.purpose,
            reason=reason or f"冲销 {original.order_no}",
            handling_method_code=original.handling_method_code,
            reversal_of_order_id=original.id,
            source_doc_type_code=original.source_doc_type_code,
            source_doc_id=original.source_doc_id,
            total_amount=-original.total_amount if original.total_amount is not None else None,
            currency_code=original.currency_code,
            created_by=current_user.user_id,
            updated_by=current_user.user_id,
        )
        lines = [
            InvStockOrderLine(
                org_id=line.org_id,
                line_no=line.line_no,
                item_id=line.item_id,
                lot_id=line.lot_id,
                from_warehouse_id=line.to_warehouse_id,
                to_warehouse_id=line.from_warehouse_id,
                from_stock_status_code=line.to_stock_status_code,
                to_stock_status_code=line.from_stock_status_code,
                quantity=line.quantity,
                unit_code=line.unit_code,
                unit_price=line.unit_price,
                amount=-line.amount if line.amount is not None else None,
                source_line_id=line.id,
                remark=f"冲销第 {line.line_no} 行",
                created_by=current_user.user_id,
                updated_by=current_user.user_id,
            )
            for line in await repository.get_lines(session, original.id)
        ]
        await repository.add_order(session, reversal, lines)
        await self._confirm_locked(session, reversal, order_type, current_user)
        return reversal

    async def void_in_session(self, session: AsyncSession, order_id: UUID, reason: str, current_user: AuthenticatedUser) -> InvStockOrder:
        """来源业务取消未记账单据；不提交调用方事务。"""
        order, order_type = await self._load(session, order_id, current_user, "update", for_update=True)
        if order.status_code in (ORDER_CONFIRMED, ORDER_VOIDED):
            raise AppException("已确认或已作废的单据不能作废", status_code=status.HTTP_409_CONFLICT)
        lines = await repository.get_lines(session, order.id)
        order.status_code, order.voided_at, order.voided_by = ORDER_VOIDED, utc_now(), current_user.user_id
        order.void_reason = reason
        order.updated_at, order.updated_by = utc_now(), current_user.user_id
        session.add(order)
        await session.flush()
        await run_source_document_handlers(session, order, order_type, lines, current_user)
        return order

    # ───────── 借出与归还 ─────────
    async def _return_type(self, session: AsyncSession, lend_type: InvStockOrderType) -> InvStockOrderType:
        """归还类型：状态转换方向，且来源/目标状态与借出类型相反（按属性识别，不按类型编号）。"""
        candidates = await type_repository.options(session, form=None, direction_code=DIRECTION_STATUS, include_inactive=False)
        for item in candidates:
            if item.default_from_status_code == lend_type.default_to_status_code and item.default_to_status_code == lend_type.default_from_status_code:
                return await self._get_type(session, item.id)
        raise AppException("未配置对应的归还单据类型", status_code=status.HTTP_400_BAD_REQUEST)

    async def create_return(self, lend_order_id: UUID, payload: ReturnCreate, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            lend, lend_type = await self._load(session, lend_order_id, current_user, "detail", for_update=True)
            if lend_type.direction_code != DIRECTION_STATUS or lend.status_code != ORDER_CONFIRMED:
                raise AppException("只能对已确认的借出单办理归还", status_code=status.HTTP_409_CONFLICT)
            return_type = await self._return_type(session, lend_type)
            lend_lines = {line.id: line for line in await repository.get_lines(session, lend.id)}
            returned = await repository.returned_quantities(session, set(lend_lines))
            requested = (
                {item.source_line_id: qty(item.quantity) for item in payload.lines}
                if payload.lines
                else {line_id: qty(Decimal(line.quantity) - returned.get(line_id, Decimal("0"))) for line_id, line in lend_lines.items()}
            )
            line_payloads = []
            for line_id, quantity in requested.items():
                source = lend_lines.get(line_id)
                if source is None:
                    raise AppException("归还明细不属于该借出单", status_code=status.HTTP_400_BAD_REQUEST)
                if quantity <= 0:
                    continue
                line_payloads.append(
                    OrderLineWrite(
                        item_id=source.item_id,
                        tracking=next((row.tracking for row in (payload.lines or []) if row.source_line_id == line_id), {}),
                        quantity=quantity,
                        source_line_id=source.id,
                        from_warehouse_id=source.from_warehouse_id,
                        unit_code=source.unit_code,
                    )
                )
            if not line_payloads:
                raise AppException("没有需要归还的数量", status_code=status.HTTP_409_CONFLICT)
            order = await self._create_in_session(
                session,
                OrderCreate(
                    order_type_id=return_type.id,
                    org_id=lend.org_id,
                    business_date=payload.business_date,
                    from_warehouse_id=lend.from_warehouse_id or lend.to_warehouse_id,
                    counterparty_party_id=lend.counterparty_party_id,
                    counterparty_name_snapshot=lend.counterparty_name_snapshot,
                    department_id=lend.department_id,
                    remark=payload.remark,
                    source_doc_type_code=None,
                    lines=line_payloads,
                    confirm=True,
                ),
                current_user,
            )
            await session.commit()
            return await self._detail(session, order)

    # ───────── 入库预警预览 ─────────
    async def preview_inbound_warnings(self, order_id: UUID, current_user: AuthenticatedUser) -> InboundWarningPreview:
        async with get_session_context() as session:
            order, order_type = await self._load(session, order_id, current_user, "detail")
            lines = await repository.get_lines(session, order.id)
            items = await repository.items(session, {line.item_id for line in lines})
            incoming: dict[tuple[UUID, UUID], Decimal] = {}
            for line in lines:
                warehouse_id = line.to_warehouse_id or order.to_warehouse_id
                if warehouse_id is None:
                    continue
                key = (line.item_id, warehouse_id)
                incoming[key] = incoming.get(key, Decimal("0")) + Decimal(line.quantity)
            alert_keys = {(item_id, order.org_id, warehouse_id) for item_id, warehouse_id in incoming}
            current = await repository.available_by_item_warehouse(session, alert_keys)
            thresholds = await warning_repository.thresholds_for_keys(session, alert_keys)
        warnings = []
        for (item_id, warehouse_id), quantity in incoming.items():
            item = items.get(item_id)
            threshold = thresholds.get((item_id, order.org_id, warehouse_id))
            if item is None or threshold is None or order_type.direction_code != DIRECTION_IN:
                continue
            max_quantity = threshold[1]
            now = current.get((item_id, order.org_id, warehouse_id), Decimal("0"))
            if now + quantity >= max_quantity:
                warnings.append(
                    ProjectedOverstockWarning(
                        item_id=item.id,
                        item_name=item.item_name,
                        unit_code=item.unit_code,
                        current_quantity=now,
                        inbound_quantity=quantity,
                        projected_quantity=now + quantity,
                        max_quantity=max_quantity,
                    )
                )
        return InboundWarningPreview(warnings=sorted(warnings, key=lambda item: item.item_name))


def _json_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {key: _json(item) for key, item in value.items()}


service = StockOrderService()
