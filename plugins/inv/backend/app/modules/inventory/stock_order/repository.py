"""库存单据、余额、流水的数据访问。只有本文件写 SQL / ORM。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, case, delete, exists, false, func, or_, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import table_scope_condition
from app.core.exceptions import AppException
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository
from app.framework.db.models import utc_now
from app.modules.department.models import SysDepartment
from app.modules.masterdata.models import MdPerson
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.message_bus.service import enqueue_event
from app.modules.organization.models import SysOrg
from app.modules.user_profile.models import SysUser

from ..constants import (
    ORDER_CONFIRMED,
    ORDER_VOIDED,
    STOCK_AVAILABLE,
    type_form,
    type_required_fields,
)
from ..models import (
    InvLot,
    InvStockBalance,
    InvStockOrder,
    InvStockOrderLine,
    InvStockOrderType,
    InvStockTransaction,
    InvWarehouse,
    MdItem,
)
from .schemas import OrderListQuery, OrderTypeItem
from ..warehouse_scope import warehouse_condition
from ..warehouse.access_repository import repository as access_repository

from .rules import fixed_order_type, stock_order_rule


def type_item(entity: InvStockOrderType) -> OrderTypeItem:
    entity = fixed_order_type(entity)
    item = OrderTypeItem.model_validate(entity)
    item.form = type_form(entity)
    item.required_fields = type_required_fields(entity)
    config = entity.required_field_config
    item.is_source_managed = bool(config.get("source_managed")) if isinstance(config, dict) else False
    return item


# ───────── 单据类型（系统业务标识及历史关联，只读） ─────────
async def _normalize_type(session: AsyncSession, data: dict[str, Any], current_user: AuthenticatedUser, entity) -> dict[str, Any]:
    raise AppException("库存单据处理方式由系统固定维护，不支持新增或修改规则", status_code=409)


class OrderTypeRepository(SqlModelCrudRepository):
    def _serialize_list_entity(self, entity):
        return type_item(entity).model_dump(mode="json")

    def _serialize_detail_entity(self, entity):
        return type_item(entity)

    def _parse_entity(self, entity):
        return type_item(entity)

    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        raise AppException("系统单据类型及历史关联不能删除", status_code=409)

    async def options(self, session: AsyncSession, *, form: str | None, direction_code: str | None, include_inactive: bool) -> list[OrderTypeItem]:
        statement = select(InvStockOrderType).where(InvStockOrderType.deleted_at.is_(None))
        rows = (await session.exec(statement.order_by(InvStockOrderType.sort_no.nulls_last(), InvStockOrderType.type_no))).all()
        items = [type_item(row) for row in rows if stock_order_rule(row) is not None]
        return sorted((item for item in items
                       if (form is None or item.form == form)
                       and (direction_code is None or item.direction_code == direction_code)),
                      key=lambda item: (item.sort_no or 0, item.type_no))

    async def get(self, session: AsyncSession, type_id: UUID) -> InvStockOrderType | None:
        row = (
            await session.exec(select(InvStockOrderType).where(InvStockOrderType.id == type_id, InvStockOrderType.deleted_at.is_(None)))
        ).one_or_none()
        return fixed_order_type(row) if row is not None else None

    async def get_many(self, session: AsyncSession, ids: set[UUID] | None = None) -> dict[UUID, InvStockOrderType]:
        statement = select(InvStockOrderType)
        if ids is not None:
            if not ids:
                return {}
            statement = statement.where(InvStockOrderType.id.in_(ids))
        return {row.id: fixed_order_type(row) for row in (await session.exec(statement)).all()}

    async def find_by_no(self, session: AsyncSession, type_no: str) -> InvStockOrderType | None:
        row = (
            await session.exec(select(InvStockOrderType).where(InvStockOrderType.type_no == type_no, InvStockOrderType.deleted_at.is_(None)))
        ).first()
        return fixed_order_type(row) if row is not None else None


type_repository = OrderTypeRepository(
    table_model=InvStockOrderType,
    item_model=OrderTypeItem,
    writable_columns=[
        "type_no",
        "type_name",
        "direction_code",
        "default_from_status_code",
        "default_to_status_code",
        "is_approval_required",
        "wf_definition_id",
        "required_field_config",
        "is_negative_allowed",
        "is_builtin",
        "is_active",
        "sort_no",
    ],
    searchable_columns=["type_no", "type_name"],
    filterable_columns=["direction_code", "is_active"],
    create_payload_normalizer=_normalize_type,
    update_payload_normalizer=_normalize_type,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="inventory_stock_order_type",
)


class StockOrderRepository:
    # ───────── 单据 ─────────
    async def get_order(self, session: AsyncSession, order_id: UUID, *, for_update: bool = False) -> InvStockOrder | None:
        statement = select(InvStockOrder).where(InvStockOrder.id == order_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).one_or_none()

    async def get_lines(self, session: AsyncSession, order_id: UUID) -> list[InvStockOrderLine]:
        return list(
            (
                await session.exec(
                    select(InvStockOrderLine).where(InvStockOrderLine.stock_order_id == order_id).order_by(InvStockOrderLine.line_no)
                )
            ).all()
        )

    async def get_lines_by_ids(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, InvStockOrderLine]:
        if not ids:
            return {}
        rows = (await session.exec(select(InvStockOrderLine).where(InvStockOrderLine.id.in_(ids)))).all()
        return {row.id: row for row in rows}

    async def add_order(self, session: AsyncSession, order: InvStockOrder, lines: list[InvStockOrderLine]) -> None:
        session.add(order)
        await session.flush()
        for line in lines:
            line.stock_order_id = order.id
            session.add(line)
        await session.flush()

    async def replace_lines(self, session: AsyncSession, order: InvStockOrder, lines: list[InvStockOrderLine]) -> None:
        await session.exec(delete(InvStockOrderLine).where(InvStockOrderLine.stock_order_id == order.id))
        await session.flush()
        for line in lines:
            line.stock_order_id = order.id
            session.add(line)
        await session.flush()

    async def delete_order(self, session: AsyncSession, order: InvStockOrder) -> None:
        await session.exec(delete(InvStockOrderLine).where(InvStockOrderLine.stock_order_id == order.id))
        await session.exec(delete(InvStockOrder).where(InvStockOrder.id == order.id))
        await session.flush()

    def scope_condition(self, current_user: AuthenticatedUser, permission_key: str):
        return table_scope_condition(InvStockOrder, current_user, permission_key)

    def _order_conditions(self, query: OrderListQuery, type_ids_by_scope: list[tuple[list[UUID], Any]], current_user=None) -> list[Any]:
        conditions: list[Any] = []
        scope_parts = []
        for type_ids, scope in type_ids_by_scope:
            part = InvStockOrder.order_type_id.in_(type_ids) if type_ids else false()
            scope_parts.append(part if scope is None else and_(part, scope))
        conditions.append(or_(*scope_parts) if scope_parts else false())
        system_warehouses = (
            select(InvWarehouse.id)
            .where(
                warehouse_condition(getattr(query, "warehouse_scope_key", None), current_user),
            )
        )
        system_line = InvStockOrderLine.__table__.alias("system_warehouse_line")
        conditions.append(
            or_(
                InvStockOrder.from_warehouse_id.in_(system_warehouses),
                InvStockOrder.to_warehouse_id.in_(system_warehouses),
                exists(
                    select(system_line.c.id).where(
                        system_line.c.stock_order_id == InvStockOrder.id,
                        or_(
                            system_line.c.from_warehouse_id.in_(system_warehouses),
                            system_line.c.to_warehouse_id.in_(system_warehouses),
                        ),
                    )
                ),
            )
        )
        if query.order_type_id is not None:
            conditions.append(InvStockOrder.order_type_id == query.order_type_id)
        if query.status_code:
            conditions.append(InvStockOrder.status_code.in_([item for item in query.status_code.split(",") if item]))
        if query.org_id is not None:
            conditions.append(InvStockOrder.org_id == query.org_id)
        if query.warehouse_id is not None:
            conditions.append(or_(InvStockOrder.from_warehouse_id == query.warehouse_id, InvStockOrder.to_warehouse_id == query.warehouse_id))
        if query.business_date_start is not None:
            conditions.append(InvStockOrder.business_date >= query.business_date_start)
        if query.business_date_end is not None:
            conditions.append(InvStockOrder.business_date <= query.business_date_end)
        line_alias = InvStockOrderLine.__table__.alias("filter_line")
        if query.item_id is not None:
            conditions.append(
                exists(
                    select(line_alias.c.id).where(line_alias.c.stock_order_id == InvStockOrder.id, line_alias.c.item_id == query.item_id)
                )
            )
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    InvStockOrder.order_no.ilike(pattern),
                    InvStockOrder.counterparty_name_snapshot.ilike(pattern),
                    InvStockOrder.remark.ilike(pattern),
                    InvStockOrder.reason.ilike(pattern),
                    InvStockOrder.purpose.ilike(pattern),
                )
            )
        if query.has_unreturned is not None:
            lent = (
                select(line_alias.c.id)
                .where(line_alias.c.stock_order_id == InvStockOrder.id)
                .where(line_alias.c.quantity > self._returned_subquery(line_alias.c.id))
            )
            conditions.append(exists(lent) if query.has_unreturned else ~exists(lent))
        return conditions

    def _returned_subquery(self, line_id_column):
        returned = InvStockOrderLine.__table__.alias("returned_line")
        returned_order = InvStockOrder.__table__.alias("returned_order")
        return (
            select(func.coalesce(func.sum(returned.c.quantity), 0))
            .select_from(returned.join(returned_order, returned_order.c.id == returned.c.stock_order_id))
            .where(returned.c.source_line_id == line_id_column, returned_order.c.status_code == ORDER_CONFIRMED)
            .scalar_subquery()
        )

    async def list_orders(
        self, session: AsyncSession, query: OrderListQuery, type_ids_by_scope: list[tuple[list[UUID], Any]], current_user: AuthenticatedUser
    ) -> tuple[int, list[InvStockOrder]]:
        conditions = self._order_conditions(query, type_ids_by_scope, current_user)
        total = (await session.exec(select(func.count()).select_from(InvStockOrder).where(*conditions))).one()
        rows = (
            await session.exec(
                select(InvStockOrder)
                .where(*conditions)
                .order_by(InvStockOrder.business_date.desc(), InvStockOrder.created_at.desc())
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        return total or 0, list(rows)

    async def list_lines(
        self,
        session: AsyncSession,
        query: OrderListQuery,
        type_ids_by_scope: list[tuple[list[UUID], Any]],
        item_keyword: str | None,
        current_user: AuthenticatedUser,
    ) -> tuple[int, list[tuple[InvStockOrderLine, InvStockOrder]]]:
        conditions = self._order_conditions(query, type_ids_by_scope, current_user)
        base = select(InvStockOrderLine, InvStockOrder).join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
        count = select(func.count()).select_from(InvStockOrderLine).join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
        if query.item_id is not None:
            conditions.append(InvStockOrderLine.item_id == query.item_id)
        if item_keyword:
            pattern = f"%{item_keyword.strip()}%"
            base = base.join(MdItem, MdItem.id == InvStockOrderLine.item_id)
            count = count.join(MdItem, MdItem.id == InvStockOrderLine.item_id)
            conditions.append(or_(MdItem.item_name.ilike(pattern), MdItem.item_no.ilike(pattern)))
        total = (await session.exec(count.where(*conditions))).one()
        rows = (
            await session.exec(
                base.where(*conditions)
                .order_by(InvStockOrder.business_date.desc(), InvStockOrder.created_at.desc(), InvStockOrderLine.line_no)
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        return total or 0, [(row[0], row[1]) for row in rows]

    async def line_stats(self, session: AsyncSession, order_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        if not order_ids:
            return {}
        rows = (
            await session.exec(
                select(
                    InvStockOrderLine.stock_order_id,
                    InvStockOrderLine.line_no,
                    MdItem.item_name,
                    InvStockOrderLine.quantity,
                    InvStockOrderLine.unit_code,
                )
                .join(MdItem, MdItem.id == InvStockOrderLine.item_id)
                .where(InvStockOrderLine.stock_order_id.in_(order_ids))
                .order_by(InvStockOrderLine.stock_order_id, InvStockOrderLine.line_no)
            )
        ).all()
        stats: dict[UUID, dict[str, Any]] = {}
        for order_id, line_no, item_name, quantity, unit_code in rows:
            item = stats.setdefault(order_id, {"line_count": 0, "total_quantity": Decimal("0"), "item_summaries": []})
            item["line_count"] += 1
            # 保留旧字段供兼容；展示使用逐行摘要，不能把不同单位合计为业务数量。
            item["total_quantity"] += quantity
            item["item_summaries"].append({
                "line_no": line_no,
                "item_name": item_name,
                "quantity": quantity,
                "unit_code": unit_code,
            })
        for item in stats.values():
            item["item_names"] = "、".join(line["item_name"] for line in item["item_summaries"])
        return stats

    async def order_no_exists(self, session: AsyncSession, order_no: str) -> bool:
        return (await session.exec(select(InvStockOrder.id).where(InvStockOrder.order_no == order_no))).first() is not None

    # ───────── 借出与归还 ─────────
    async def returned_quantities(self, session: AsyncSession, source_line_ids: set[UUID], *, confirmed_only: bool = True) -> dict[UUID, Decimal]:
        if not source_line_ids:
            return {}
        statement = (
            select(InvStockOrderLine.source_line_id, func.sum(InvStockOrderLine.quantity))
            .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
            .where(InvStockOrderLine.source_line_id.in_(source_line_ids))
            .group_by(InvStockOrderLine.source_line_id)
        )
        statement = statement.where(InvStockOrder.status_code == ORDER_CONFIRMED) if confirmed_only else statement.where(
            InvStockOrder.status_code != "voided"
        )
        rows = (await session.exec(statement)).all()
        return {row[0]: Decimal(row[1] or 0) for row in rows}

    async def outstanding_lends_for_party(
        self, session: AsyncSession, *, org_id: UUID, party_id: UUID
    ) -> list[tuple[InvStockOrderLine, InvStockOrder, MdItem, Decimal]]:
        """公开查询契约的数据层：读取某主体已确认借出且尚未归还的明细。"""
        rows = (
            await session.exec(
                select(InvStockOrderLine, InvStockOrder, MdItem)
                .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
                .join(InvStockOrderType, InvStockOrderType.id == InvStockOrder.order_type_id)
                .join(MdItem, MdItem.id == InvStockOrderLine.item_id)
                .where(
                    InvStockOrder.org_id == org_id,
                    InvStockOrder.counterparty_party_id == party_id,
                    InvStockOrder.status_code == ORDER_CONFIRMED,
                    InvStockOrderType.type_no == "LEND",
                    InvStockOrderLine.quantity > self._returned_subquery(InvStockOrderLine.id),
                )
                .order_by(InvStockOrder.business_date, InvStockOrderLine.line_no)
            )
        ).all()
        result = []
        for line, order, item in rows:
            returned = (
                await session.exec(
                    select(func.coalesce(func.sum(InvStockOrderLine.quantity), 0))
                    .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
                    .where(
                        InvStockOrderLine.source_line_id == line.id,
                        InvStockOrder.status_code == ORDER_CONFIRMED,
                    )
                )
            ).one()
            result.append((line, order, item, Decimal(line.quantity) - Decimal(returned or 0)))
        return result

    async def return_orders_of(self, session: AsyncSession, line_ids: set[UUID]) -> list[InvStockOrder]:
        if not line_ids:
            return []
        rows = (
            await session.exec(
                select(InvStockOrder)
                .where(
                    exists(
                        select(InvStockOrderLine.id).where(
                            InvStockOrderLine.stock_order_id == InvStockOrder.id, InvStockOrderLine.source_line_id.in_(line_ids)
                        )
                    )
                )
                .order_by(InvStockOrder.created_at)
            )
        ).all()
        return list(rows)

    async def line_transactions(self, session: AsyncSession, line_ids: set[UUID]) -> list[InvStockTransaction]:
        if not line_ids:
            return []
        rows = (
            await session.exec(
                select(InvStockTransaction).where(InvStockTransaction.stock_order_line_id.in_(line_ids)).order_by(InvStockTransaction.created_at)
            )
        ).all()
        return list(rows)

    async def order_transactions(self, session: AsyncSession, order_id: UUID) -> list[InvStockTransaction]:
        rows = (
            await session.exec(
                select(InvStockTransaction).where(InvStockTransaction.stock_order_id == order_id).order_by(InvStockTransaction.transaction_no)
            )
        ).all()
        return list(rows)

    async def returned_by_lot(self, session: AsyncSession, source_line_id: UUID) -> dict[UUID | None, Decimal]:
        """已确认的归还行按批次汇总的归还数量（来源状态的流水）。"""
        rows = (
            await session.exec(
                select(InvStockTransaction.lot_id, func.sum(InvStockTransaction.quantity))
                .join(InvStockOrderLine, InvStockOrderLine.id == InvStockTransaction.stock_order_line_id)
                .where(InvStockOrderLine.source_line_id == source_line_id)
                .group_by(InvStockTransaction.lot_id)
            )
        ).all()
        return {row[0]: Decimal(row[1] or 0) for row in rows}

    # ───────── 批次 ─────────
    async def find_lot(self, session: AsyncSession, item_id: UUID, lot_no: str) -> InvLot | None:
        return (
            await session.exec(select(InvLot).where(InvLot.item_id == item_id, InvLot.lot_no == lot_no, InvLot.deleted_at.is_(None)))
        ).first()

    async def add_lot(self, session: AsyncSession, lot: InvLot) -> InvLot:
        session.add(lot)
        await session.flush()
        return lot

    async def get_lots(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, InvLot]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        return {row.id: row for row in (await session.exec(select(InvLot).where(InvLot.id.in_(ids)))).all()}

    # ───────── 记账：锁、余额、流水（只由 posting 调用） ─────────
    async def validate_balance_organizations(
        self,
        session: AsyncSession,
        *,
        item_ids: set[UUID],
        warehouse_ids: set[UUID],
    ) -> None:
        """记账前锁定并检查涉及的异常余额，不把旧余额静默转移到其他组织。"""
        if not item_ids or not warehouse_ids:
            return
        mismatch = (
            await session.exec(
                select(InvStockBalance.id, InvWarehouse.warehouse_name)
                .join(InvWarehouse, InvWarehouse.id == InvStockBalance.warehouse_id)
                .where(
                    InvStockBalance.item_id.in_(item_ids),
                    InvStockBalance.warehouse_id.in_(warehouse_ids),
                    InvStockBalance.org_id != InvWarehouse.org_id,
                )
                .order_by(InvStockBalance.id)
                .limit(1)
                .with_for_update(of=InvStockBalance)
            )
        ).first()
        if mismatch is not None:
            raise AppException(
                f"仓库“{mismatch[1]}”的库存余额所属组织与仓库不一致，请联系管理员核对修正后再记账",
                status_code=status.HTTP_409_CONFLICT,
            )

    async def lock_items(self, session: AsyncSession, item_ids: list[UUID]) -> None:
        """按物料加事务级咨询锁（排序后依次加锁，避免死锁）：同一物料的记账串行执行。"""
        for item_id in sorted(set(item_ids), key=str):
            await session.exec(text("select pg_advisory_xact_lock(hashtextextended(:key, 0))").bindparams(key=f"inv_stock:{item_id}"))

    async def lock_balances(
        self,
        session: AsyncSession,
        *,
        item_id: UUID,
        warehouse_id: UUID,
        stock_status_code: str,
        lot_id: UUID | None = None,
        any_lot: bool = False,
    ) -> list[tuple[InvStockBalance, InvLot | None]]:
        """锁定可扣减的余额行；先无批次，再按有效期、批次创建时间（先进先出）。"""
        statement = (
            select(InvStockBalance, InvLot)
            .join(InvLot, InvLot.id == InvStockBalance.lot_id, isouter=True)
            .where(
                InvStockBalance.item_id == item_id,
                InvStockBalance.warehouse_id == warehouse_id,
                InvStockBalance.stock_status_code == stock_status_code,
                InvStockBalance.owner_party_id.is_(None),
            )
            .order_by(
                InvStockBalance.lot_id.is_not(None),
                InvLot.expiry_date.nulls_last(),
                InvLot.created_at,
                InvStockBalance.id,
            )
            .with_for_update(of=InvStockBalance)
            .execution_options(populate_existing=True)
        )
        if not any_lot:
            statement = statement.where(InvStockBalance.lot_id.is_(None) if lot_id is None else InvStockBalance.lot_id == lot_id)
        rows = (await session.exec(statement)).all()
        return [(row[0], row[1]) for row in rows]

    async def ensure_balance(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        lot_id: UUID | None,
        stock_status_code: str,
        user_id: UUID | None,
    ) -> InvStockBalance:
        table = InvStockBalance.__table__
        await session.exec(
            pg_insert(table)
            .values(
                org_id=org_id,
                item_id=item_id,
                warehouse_id=warehouse_id,
                lot_id=lot_id,
                stock_status_code=stock_status_code,
                owner_party_id=None,
                quantity=0,
                reserved_quantity=0,
                version_no=0,
                created_by=user_id,
                updated_by=user_id,
            )
            .on_conflict_do_nothing(index_elements=["item_id", "warehouse_id", "lot_id", "stock_status_code", "owner_party_id"])
        )
        statement = (
            select(InvStockBalance)
            .where(
                InvStockBalance.item_id == item_id,
                InvStockBalance.warehouse_id == warehouse_id,
                InvStockBalance.lot_id.is_(None) if lot_id is None else InvStockBalance.lot_id == lot_id,
                InvStockBalance.stock_status_code == stock_status_code,
                InvStockBalance.owner_party_id.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        balance = (await session.exec(statement)).one()
        if balance.org_id != org_id:
            raise AppException(
                "库存余额所属组织与仓库不一致，请联系管理员核对修正后再记账",
                status_code=status.HTTP_409_CONFLICT,
            )
        return balance

    async def change_balance(self, session: AsyncSession, balance: InvStockBalance, delta: Decimal, user_id: UUID | None) -> Decimal:
        """按版本号更新余额（乐观锁）；返回更新后的数量。"""
        result = await session.exec(
            update(InvStockBalance)
            .where(InvStockBalance.id == balance.id, InvStockBalance.version_no == balance.version_no)
            .values(
                quantity=InvStockBalance.quantity + delta,
                version_no=InvStockBalance.version_no + 1,
                updated_at=utc_now(),
                updated_by=user_id,
            )
            .returning(InvStockBalance.quantity, InvStockBalance.version_no)
            .execution_options(synchronize_session=False)
        )
        row = result.first()
        if row is None:
            raise AppException("库存余额已被其他操作修改，请重试", status_code=status.HTTP_409_CONFLICT)
        set_committed_value(balance, "quantity", row[0])
        set_committed_value(balance, "version_no", row[1])
        return row[0]

    async def add_transactions(self, session: AsyncSession, transactions: list[InvStockTransaction]) -> None:
        for transaction in transactions:
            session.add(transaction)
        await session.flush()

    async def book_quantity(
        self, session: AsyncSession, *, item_id: UUID, warehouse_id: UUID, lot_id: UUID | None, stock_status_code: str
    ) -> Decimal:
        value = (
            await session.exec(
                select(func.coalesce(func.sum(InvStockBalance.quantity), 0)).where(
                    InvStockBalance.item_id == item_id,
                    InvStockBalance.warehouse_id == warehouse_id,
                    InvStockBalance.lot_id.is_(None) if lot_id is None else InvStockBalance.lot_id == lot_id,
                    InvStockBalance.stock_status_code == stock_status_code,
                    InvStockBalance.owner_party_id.is_(None),
                )
            )
        ).one()
        return Decimal(value or 0)

    async def available_by_item_warehouse(
        self,
        session: AsyncSession,
        keys: set[tuple[UUID, UUID, UUID]],
    ) -> dict[tuple[UUID, UUID, UUID], Decimal]:
        """物料 × 组织 × 仓库的可用数量（预警口径）。"""
        if not keys:
            return {}
        item_ids = {key[0] for key in keys}
        org_ids = {key[1] for key in keys}
        warehouse_ids = {key[2] for key in keys}
        rows = (
            await session.exec(
                select(
                    InvStockBalance.item_id,
                    InvStockBalance.org_id,
                    InvStockBalance.warehouse_id,
                    func.sum(InvStockBalance.quantity - InvStockBalance.reserved_quantity),
                )
                .where(
                    InvStockBalance.item_id.in_(item_ids),
                    InvStockBalance.org_id.in_(org_ids),
                    InvStockBalance.warehouse_id.in_(warehouse_ids),
                    InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                )
                .group_by(InvStockBalance.item_id, InvStockBalance.org_id, InvStockBalance.warehouse_id)
            )
        ).all()
        result = {key: Decimal("0") for key in keys}
        for item_id, org_id, warehouse_id, quantity in rows:
            key = (item_id, org_id, warehouse_id)
            if key in result:
                result[key] = Decimal(quantity or 0)
        return result

    async def available_by_item_org(
        self,
        session: AsyncSession,
        pairs: set[tuple[UUID, UUID]],
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """物料 × 组织的可用数量；保留给入库积压预览使用。"""
        if not pairs:
            return {}
        item_ids = {pair[0] for pair in pairs}
        org_ids = {pair[1] for pair in pairs}
        rows = (
            await session.exec(
                select(
                    InvStockBalance.item_id,
                    InvStockBalance.org_id,
                    func.sum(InvStockBalance.quantity - InvStockBalance.reserved_quantity),
                )
                .where(
                    InvStockBalance.item_id.in_(item_ids),
                    InvStockBalance.org_id.in_(org_ids),
                    InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                )
                .group_by(InvStockBalance.item_id, InvStockBalance.org_id)
            )
        ).all()
        result = {pair: Decimal("0") for pair in pairs}
        for item_id, org_id, quantity in rows:
            key = (item_id, org_id)
            if key in result:
                result[key] = Decimal(quantity or 0)
        return result

    async def add_outbox_event(self, session: AsyncSession, *, payload: dict[str, Any], user_id: UUID | None) -> None:
        enqueue_event(
            session,
            producer_module_code="inventory",
            event_type_code="inv_stock_order_confirmed",
            routing_key="inv.stock_order.confirmed",
            payload=payload,
            header_meta={"source": "inventory"},
            created_by=user_id,
        )
        await session.flush()

    async def source_document_item_quantities(
        self,
        session: AsyncSession,
        *,
        source_doc_type_code: str,
        source_doc_id: UUID,
        confirmed_only: bool,
    ) -> dict[UUID, Decimal]:
        """按来源单据汇总库存单据净数量，冲销单按负数扣减。"""

        original_order = aliased(InvStockOrder)
        signed_quantity = case(
            (
                InvStockOrder.reversal_of_order_id.is_not(None),
                -InvStockOrderLine.quantity,
            ),
            else_=InvStockOrderLine.quantity,
        )
        source_condition = or_(
            and_(
                InvStockOrder.source_doc_type_code == source_doc_type_code,
                InvStockOrder.source_doc_id == source_doc_id,
            ),
            and_(
                InvStockOrder.reversal_of_order_id.is_not(None),
                original_order.source_doc_type_code == source_doc_type_code,
                original_order.source_doc_id == source_doc_id,
            ),
        )
        status_condition = (
            InvStockOrder.status_code == ORDER_CONFIRMED
            if confirmed_only
            else InvStockOrder.status_code != ORDER_VOIDED
        )
        rows = (
            await session.exec(
                select(InvStockOrderLine.item_id, func.sum(signed_quantity))
                .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
                .join(InvStockOrderType, InvStockOrderType.id == InvStockOrder.order_type_id)
                .join(
                    original_order,
                    original_order.id == InvStockOrder.reversal_of_order_id,
                    isouter=True,
                )
                .where(
                    source_condition,
                    status_condition,
                    InvStockOrderType.direction_code == "in",
                )
                .group_by(InvStockOrderLine.item_id)
            )
        ).all()
        return {row[0]: Decimal(row[1] or 0) for row in rows}

    async def source_document_order_stats(
        self,
        session: AsyncSession,
        *,
        source_doc_type_code: str,
        source_doc_ids: set[UUID],
    ) -> dict[UUID, dict[str, int]]:
        """批量统计来源单据关联的库存原单与冲销单状态。"""

        if not source_doc_ids:
            return {}
        original_order = aliased(InvStockOrder)
        effective_source_doc_id = case(
            (
                InvStockOrder.source_doc_type_code == source_doc_type_code,
                InvStockOrder.source_doc_id,
            ),
            else_=original_order.source_doc_id,
        ).label("effective_source_doc_id")
        source_condition = or_(
            and_(
                InvStockOrder.source_doc_type_code == source_doc_type_code,
                InvStockOrder.source_doc_id.in_(source_doc_ids),
            ),
            and_(
                InvStockOrder.reversal_of_order_id.is_not(None),
                original_order.source_doc_type_code == source_doc_type_code,
                original_order.source_doc_id.in_(source_doc_ids),
            ),
        )
        rows = (
            await session.exec(
                select(
                    effective_source_doc_id,
                    InvStockOrder.status_code,
                    InvStockOrder.reversal_of_order_id,
                )
                .join(InvStockOrderType, InvStockOrderType.id == InvStockOrder.order_type_id)
                .join(
                    original_order,
                    original_order.id == InvStockOrder.reversal_of_order_id,
                    isouter=True,
                )
                .where(
                    source_condition,
                    InvStockOrderType.direction_code == "in",
                )
            )
        ).all()
        result: dict[UUID, dict[str, int]] = {}
        for source_doc_id, status_code, reversal_of_order_id in rows:
            stats = result.setdefault(
                source_doc_id,
                {
                    "original_count": 0,
                    "active_original_count": 0,
                    "voided_original_count": 0,
                    "confirmed_reversal_count": 0,
                },
            )
            if reversal_of_order_id is not None:
                if status_code == ORDER_CONFIRMED:
                    stats["confirmed_reversal_count"] += 1
                continue
            stats["original_count"] += 1
            if status_code == ORDER_VOIDED:
                stats["voided_original_count"] += 1
            else:
                stats["active_original_count"] += 1
        return result

    async def unit_names(self, session: AsyncSession) -> dict[str, str]:
        rows = (
            await session.exec(
                select(SysDictItem.item_code, SysDictItem.item_name)
                .join(SysDict, SysDict.id == SysDictItem.dict_id)
                .where(SysDict.dict_code == "md_unit", SysDictItem.deleted_at.is_(None))
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    # ───────── 展示用名称 ─────────
    async def warehouse_labels(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, dict[str, Any]]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (
            await session.exec(
                select(InvWarehouse, SysOrg.org_name)
                .join(SysOrg, SysOrg.id == InvWarehouse.org_id)
                .where(InvWarehouse.id.in_(ids))
            )
        ).all()
        return {
            warehouse.id: {
                "org_id": warehouse.org_id,
                "org_name": org_name,
                "warehouse_id": warehouse.id,
                "warehouse_name": warehouse_name,
                "label": f"{org_name} / {warehouse_name}",
            }
            for warehouse, org_name in rows
            for warehouse_name in [warehouse.warehouse_name]
        }

    async def get_warehouses(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, InvWarehouse]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (await session.exec(select(InvWarehouse).where(
            InvWarehouse.id.in_(ids), InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
        ).order_by(InvWarehouse.id).with_for_update(read=True, of=InvWarehouse))).all()
        return {row.id: row for row in rows}

    async def org_names(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, str]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (await session.exec(select(SysOrg.id, SysOrg.org_name).where(SysOrg.id.in_(ids)))).all()
        return {row[0]: row[1] for row in rows}

    async def warehouse_names(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, str]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (
            await session.exec(
                select(InvWarehouse.id, InvWarehouse.warehouse_name).where(
                    InvWarehouse.id.in_(ids),
                )
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    async def department_names(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, str]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (await session.exec(select(SysDepartment.id, SysDepartment.department_name).where(SysDepartment.id.in_(ids)))).all()
        return {row[0]: row[1] for row in rows}

    async def user_names(self, session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, str]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        rows = (await session.exec(select(SysUser.id, SysUser.display_name).where(SysUser.id.in_(ids)))).all()
        return {row[0]: row[1] for row in rows}

    async def items(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, MdItem]:
        if not ids:
            return {}
        rows = (await session.exec(select(MdItem).where(MdItem.id.in_(ids)))).all()
        return {row.id: row for row in rows}

    async def user_party(self, session: AsyncSession, user_id: UUID) -> tuple[UUID | None, str | None]:
        row = (
            await session.exec(
                select(MdPerson.party_id, MdPerson.full_name, SysUser.display_name)
                .select_from(SysUser)
                .join(MdPerson, and_(MdPerson.user_id == SysUser.id, MdPerson.deleted_at.is_(None)), isouter=True)
                .where(SysUser.id == user_id, SysUser.deleted_at.is_(None))
            )
        ).first()
        if row is None:
            raise AppException("用户不存在", status_code=status.HTTP_400_BAD_REQUEST)
        return row[0], row[1] or row[2]

    async def department_exists(self, session: AsyncSession, department_id: UUID) -> bool:
        return (
            await session.exec(select(SysDepartment.id).where(SysDepartment.id == department_id, SysDepartment.deleted_at.is_(None)))
        ).first() is not None

    async def personnel_options(self, session: AsyncSession, org_id: UUID | None) -> dict[str, list[dict[str, Any]]]:
        departments = select(SysDepartment).where(SysDepartment.deleted_at.is_(None), SysDepartment.is_active.is_(True))
        users = (
            select(SysUser, MdPerson.party_id, MdPerson.full_name)
            .join(MdPerson, and_(MdPerson.user_id == SysUser.id, MdPerson.deleted_at.is_(None)), isouter=True)
            .where(SysUser.deleted_at.is_(None), SysUser.is_active.is_(True))
        )
        if org_id is not None:
            departments = departments.where(SysDepartment.org_id == org_id)
            users = users.where(SysUser.org_id == org_id)
        dept_rows = (await session.exec(departments.order_by(SysDepartment.sort_no.nulls_last(), SysDepartment.department_name))).all()
        dept_names = {row.id: row.department_name for row in dept_rows}
        user_rows = (await session.exec(users.order_by(SysUser.display_name).limit(2000))).all()
        return {
            "departments": [{"id": str(row.id), "department_name": row.department_name} for row in dept_rows],
            "users": [
                {
                    "user_id": str(user.id),
                    "party_id": str(party_id) if party_id else None,
                    "display_name": full_name or user.display_name,
                    "department_id": str(user.department_id) if user.department_id else None,
                    "department_name": dept_names.get(user.department_id) if user.department_id else None,
                }
                for user, party_id, full_name in user_rows
            ],
        }

    # ───────── 成本 ─────────
    async def average_costs(self, session: AsyncSession, item_ids: set[UUID]) -> dict[UUID, tuple[Decimal, Decimal]]:
        """已确认入库明细的数量与金额合计（加权平均成本用）。"""
        if not item_ids:
            return {}
        rows = (
            await session.exec(
                select(InvStockOrderLine.item_id, func.sum(InvStockOrderLine.quantity), func.sum(InvStockOrderLine.amount))
                .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id)
                .join(InvStockOrderType, InvStockOrderType.id == InvStockOrder.order_type_id)
                .where(
                    InvStockOrderLine.item_id.in_(item_ids),
                    InvStockOrder.status_code == ORDER_CONFIRMED,
                    InvStockOrder.reversal_of_order_id.is_(None),
                    InvStockOrderType.direction_code == "in",
                    InvStockOrderLine.amount.is_not(None),
                )
                .group_by(InvStockOrderLine.item_id)
            )
        ).all()
        return {row[0]: (Decimal(row[1] or 0), Decimal(row[2] or 0)) for row in rows}


repository = StockOrderRepository()
