"""导入用的数据访问：下拉选项、按名称查找、物料分类与物料的新增或更新。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now
from app.auth.scope_filters import scoped_conditions
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.organization.models import SysOrg
from app.modules.masterdata.models import MdParty
from app.modules.supplier.models import MdSupplier

from ..models import InvStockBalance, InvWarehouse, MdItem, MdItemCategory
from ..products.repository import new_item_no

ITEM_SELECTION_SEPARATOR = "｜"


def item_selection_label(item: MdItem) -> str:
    return ITEM_SELECTION_SEPARATOR.join([item.item_no, item.item_name, item.specification or ""])


class ImportRepository:
    async def dict_items(self, session: AsyncSession, dict_code: str) -> list[tuple[str, str]]:
        rows = (
            await session.exec(
                select(SysDictItem.item_code, SysDictItem.item_name)
                .join(SysDict, SysDict.id == SysDictItem.dict_id)
                .where(
                    SysDict.dict_code == dict_code,
                    SysDictItem.deleted_at.is_(None),
                    SysDictItem.is_active.is_(True),
                )
                .order_by(SysDictItem.sort_no.nulls_last(), SysDictItem.item_code)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def categories(self, session: AsyncSession) -> dict[str, MdItemCategory]:
        rows = (await session.exec(select(MdItemCategory).where(MdItemCategory.deleted_at.is_(None)))).all()
        return {row.category_name: row for row in rows}

    async def suppliers(self, session: AsyncSession, *, include_inactive: bool = False) -> dict[str, UUID]:
        conditions = [MdSupplier.deleted_at.is_(None), MdParty.deleted_at.is_(None)]
        if not include_inactive:
            conditions.append(MdSupplier.is_active.is_(True))
        rows = (
            await session.exec(
                select(MdParty.display_name, MdSupplier.id).join(MdParty, MdParty.id == MdSupplier.party_id)
                .where(*conditions)
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    async def items(self, session: AsyncSession, *, active_only: bool = False) -> list[MdItem]:
        statement = select(MdItem).where(MdItem.deleted_at.is_(None))
        if active_only:
            statement = statement.where(MdItem.is_active.is_(True))
        return list((await session.exec(statement.order_by(MdItem.item_name))).all())

    async def lock_item_import(self, session, schema: str) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"inventory-item-import:{schema}"},
        )

    async def matching_items(self, session, names, numbers, *, lock=False):
        statement = select(MdItem).where(
            MdItem.deleted_at.is_(None),
            or_(MdItem.item_name.in_(names), MdItem.item_no.in_(numbers)),
        ).order_by(MdItem.id)
        if lock:
            statement = statement.with_for_update()
        return list((await session.exec(statement)).all())

    async def importable_item_ids(self, session, user, ids):
        statement = select(MdItem.id).where(
            MdItem.id.in_(ids), *scoped_conditions(MdItem, user, "inventory_product:import"),
        )
        return set((await session.exec(statement)).all())

    async def warehouses(self, session: AsyncSession, org_ids: list[UUID] | None, *, user=None) -> dict[str, InvWarehouse]:
        statement = (
            select(InvWarehouse, SysOrg.org_name)
            .join(SysOrg, SysOrg.id == InvWarehouse.org_id)
            .where(InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True))
        )
        if org_ids:
            statement = statement.where(InvWarehouse.org_id.in_(org_ids))
        if user is not None:
            statement = statement.where(*scoped_conditions(InvWarehouse, user, "inventory_item:import"))
        rows = (await session.exec(statement)).all()
        return {f"{org_name} / {warehouse.warehouse_name}（{warehouse.warehouse_no}）": warehouse for warehouse, org_name in rows}

    async def book_quantity(self, session: AsyncSession, *, item_id: UUID, warehouse_id: UUID, lot_no: str | None) -> Decimal:
        from ..models import InvLot

        statement = select(func.coalesce(func.sum(InvStockBalance.quantity), 0)).where(
            InvStockBalance.item_id == item_id,
            InvStockBalance.warehouse_id == warehouse_id,
            InvStockBalance.stock_status_code == "available",
        )
        if lot_no:
            statement = statement.join(InvLot, InvLot.id == InvStockBalance.lot_id).where(InvLot.lot_no == lot_no)
        else:
            statement = statement.where(InvStockBalance.lot_id.is_(None))
        return Decimal((await session.exec(statement)).one() or 0)

    async def upsert_category(self, session: AsyncSession, existing: MdItemCategory | None, data: dict[str, Any], user_id: UUID) -> bool:
        if existing is None:
            session.add(MdItemCategory(**data, created_by=user_id, updated_by=user_id))
            await session.flush()
            return True
        for key, value in data.items():
            setattr(existing, key, value)
        existing.updated_by = user_id
        existing.updated_at = utc_now()
        session.add(existing)
        await session.flush()
        return False

    async def upsert_item(self, session: AsyncSession, existing: MdItem | None, data: dict[str, Any], user_id: UUID) -> bool:
        if existing is None:
            data = dict(data)
            number = data.pop("item_no", None) or new_item_no()
            session.add(MdItem(item_no=number, **data, created_by=user_id, updated_by=user_id))
            await session.flush()
            return True
        for key, value in data.items():
            setattr(existing, key, value)
        existing.updated_by = user_id
        existing.updated_at = utc_now()
        session.add(existing)
        await session.flush()
        return False


repository = ImportRepository()
