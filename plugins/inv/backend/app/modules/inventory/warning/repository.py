"""库存预警的数据访问。"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, union
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import table_scope_condition
from app.framework.db.models import utc_now
from app.modules.organization.models import SysOrg

from ..constants import STOCK_AVAILABLE
from ..warehouse_scope import warehouse_condition
from ..warehouse.access_repository import repository as access_repository
from ..models import InvItemWarehouseSetting, InvStockBalance, InvWarehouse, MdItem, MdItemCategory
from .schemas import StockSettingQuery


class StockWarningRepository:
    async def settings(
        self,
        session: AsyncSession,
        query: StockSettingQuery,
        current_user: AuthenticatedUser,
    ) -> tuple[int, list[dict]]:
        """列出已有余额或已有设置的物料仓库组合，不生成全量笛卡尔积。"""
        balance_conditions = []
        balance_scope = table_scope_condition(InvStockBalance, current_user, "inventory_item:list")
        if balance_scope is not None:
            balance_conditions.append(balance_scope)
        setting_conditions = [InvItemWarehouseSetting.deleted_at.is_(None)]
        setting_scope = table_scope_condition(InvItemWarehouseSetting, current_user, "inventory_item:list")
        if setting_scope is not None:
            setting_conditions.append(setting_scope)

        balance_pairs = select(
            InvStockBalance.item_id.label("item_id"),
            InvStockBalance.org_id.label("org_id"),
            InvStockBalance.warehouse_id.label("warehouse_id"),
        ).where(*balance_conditions)
        setting_pairs = select(
            InvItemWarehouseSetting.item_id.label("item_id"),
            InvItemWarehouseSetting.org_id.label("org_id"),
            InvItemWarehouseSetting.warehouse_id.label("warehouse_id"),
        ).where(*setting_conditions)
        pairs = union(balance_pairs, setting_pairs).subquery("stock_setting_pair")

        available = (
            select(
                InvStockBalance.item_id.label("item_id"),
                InvStockBalance.org_id.label("org_id"),
                InvStockBalance.warehouse_id.label("warehouse_id"),
                func.sum(
                    case(
                        (
                            InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                            InvStockBalance.quantity - InvStockBalance.reserved_quantity,
                        ),
                        else_=0,
                    )
                ).label("available_quantity"),
                func.max(InvStockBalance.updated_at).label("balance_updated_at"),
            )
            .group_by(InvStockBalance.item_id, InvStockBalance.org_id, InvStockBalance.warehouse_id)
            .subquery("stock_setting_available")
        )
        current_quantity = func.coalesce(available.c.available_quantity, 0)
        lower = InvItemWarehouseSetting.min_quantity
        upper = InvItemWarehouseSetting.max_quantity
        configured = InvItemWarehouseSetting.id.is_not(None)
        out_of_stock = and_(configured, current_quantity <= lower, current_quantity <= 0)
        low_stock = and_(configured, current_quantity > 0, current_quantity <= lower)
        overstock = and_(configured, current_quantity > upper)
        normal = and_(configured, current_quantity > lower, current_quantity <= upper)

        conditions = [
            MdItem.deleted_at.is_(None),
            InvWarehouse.deleted_at.is_(None),
            warehouse_condition(getattr(query, "warehouse_scope_key", None), current_user),
        ]
        if query.org_id is not None:
            conditions.append(pairs.c.org_id == query.org_id)
        if query.warehouse_id is not None:
            conditions.append(pairs.c.warehouse_id == query.warehouse_id)
        if query.category_id is not None:
            conditions.append(MdItem.category_id == query.category_id)
        if query.item_id is not None:
            conditions.append(pairs.c.item_id == query.item_id)
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    MdItem.item_name.ilike(pattern),
                    MdItem.item_no.ilike(pattern),
                    MdItem.specification.ilike(pattern),
                )
            )
        status_conditions = {
            "configured": configured,
            "unconfigured": InvItemWarehouseSetting.id.is_(None),
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "normal": normal,
            "overstock": overstock,
        }
        if query.status_code != "all":
            conditions.append(status_conditions[query.status_code])

        base = (
            select(
                pairs.c.item_id,
                pairs.c.org_id,
                pairs.c.warehouse_id,
                MdItem.item_no,
                MdItem.item_name,
                MdItem.category_id,
                MdItemCategory.category_name,
                MdItem.specification,
                MdItem.unit_code,
                SysOrg.org_name,
                InvWarehouse.warehouse_name,
                InvItemWarehouseSetting.min_quantity,
                InvItemWarehouseSetting.max_quantity,
                current_quantity.label("available_quantity"),
                func.coalesce(
                    InvItemWarehouseSetting.updated_at,
                    available.c.balance_updated_at,
                ).label("updated_at"),
            )
            .join(MdItem, MdItem.id == pairs.c.item_id)
            .join(MdItemCategory, MdItemCategory.id == MdItem.category_id, isouter=True)
            .join(SysOrg, SysOrg.id == pairs.c.org_id)
            .join(InvWarehouse, InvWarehouse.id == pairs.c.warehouse_id)
            .join(
                InvItemWarehouseSetting,
                and_(
                    InvItemWarehouseSetting.item_id == pairs.c.item_id,
                    InvItemWarehouseSetting.warehouse_id == pairs.c.warehouse_id,
                    InvItemWarehouseSetting.deleted_at.is_(None),
                ),
                isouter=True,
            )
            .join(
                available,
                and_(
                    available.c.item_id == pairs.c.item_id,
                    available.c.org_id == pairs.c.org_id,
                    available.c.warehouse_id == pairs.c.warehouse_id,
                ),
                isouter=True,
            )
            .where(*conditions)
        )
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(SysOrg.org_name, InvWarehouse.warehouse_name, MdItem.item_name)
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        return total or 0, [dict(row._mapping) for row in rows]

    async def available_by_warehouse_for_item(
        self,
        session: AsyncSession,
        item_id: UUID,
        current_user: AuthenticatedUser,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """按物料维护权限的数据范围，汇总各组织、仓库的实时可用库存。"""
        available = func.sum(
            case(
                (
                    InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                    InvStockBalance.quantity - InvStockBalance.reserved_quantity,
                ),
                else_=0,
            )
        )
        conditions = [InvStockBalance.item_id == item_id]
        scope = table_scope_condition(InvStockBalance, current_user, "inventory_product:update")
        if scope is not None:
            conditions.append(scope)
        rows = (
            await session.exec(
                select(
                    InvStockBalance.org_id,
                    InvStockBalance.warehouse_id,
                    available.label("available_quantity"),
                )
                .where(*conditions)
                .group_by(InvStockBalance.org_id, InvStockBalance.warehouse_id)
            )
        ).all()
        return {
            (org_id, warehouse_id): Decimal(quantity or 0)
            for org_id, warehouse_id, quantity in rows
        }

    async def available_for_pair(
        self,
        session: AsyncSession,
        *,
        item_id: UUID,
        warehouse_id: UUID,
    ) -> Decimal:
        quantity = (
            await session.exec(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                                    InvStockBalance.quantity - InvStockBalance.reserved_quantity,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    )
                ).where(
                    InvStockBalance.item_id == item_id,
                    InvStockBalance.warehouse_id == warehouse_id,
                )
            )
        ).one()
        return Decimal(quantity or 0)

    async def item_warehouse_setting(
        self,
        session: AsyncSession,
        *,
        item_id: UUID,
        warehouse_id: UUID,
        current_user: AuthenticatedUser,
        for_update: bool = False,
    ):
        conditions = [
            MdItem.id == item_id,
            MdItem.deleted_at.is_(None),
            InvWarehouse.id == warehouse_id,
            InvWarehouse.deleted_at.is_(None),
        ]
        scope = table_scope_condition(InvWarehouse, current_user, "inventory_product:update")
        if scope is not None:
            conditions.append(scope)
        statement = (
            select(MdItem, InvWarehouse)
            .select_from(MdItem)
            .join(InvWarehouse, InvWarehouse.id == warehouse_id)
            .where(*conditions)
        )
        if for_update:
            statement = statement.with_for_update()
        pair = (await session.exec(statement)).first()
        if pair is None:
            return None
        setting_statement = select(InvItemWarehouseSetting).where(
            InvItemWarehouseSetting.item_id == item_id,
            InvItemWarehouseSetting.warehouse_id == warehouse_id,
            InvItemWarehouseSetting.deleted_at.is_(None),
        )
        if for_update:
            setting_statement = setting_statement.with_for_update()
        setting = (await session.exec(setting_statement)).first()
        return pair[0], pair[1], setting

    async def save_setting(
        self,
        session: AsyncSession,
        *,
        setting: InvItemWarehouseSetting | None,
        item_id: UUID,
        warehouse: InvWarehouse,
        min_quantity: Decimal,
        max_quantity: Decimal,
        user_id: UUID | None,
    ) -> InvItemWarehouseSetting:
        if setting is None:
            setting = InvItemWarehouseSetting(
                org_id=warehouse.org_id,
                item_id=item_id,
                warehouse_id=warehouse.id,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
                created_by=user_id,
                updated_by=user_id,
            )
        else:
            setting.min_quantity = min_quantity
            setting.max_quantity = max_quantity
            setting.updated_by = user_id
            setting.updated_at = utc_now()
        session.add(setting)
        await session.flush()
        return setting

    async def thresholds_for_keys(
        self,
        session: AsyncSession,
        keys: set[tuple[UUID, UUID, UUID]],
    ) -> dict[tuple[UUID, UUID, UUID], tuple[Decimal, Decimal]]:
        if not keys:
            return {}
        item_ids = {key[0] for key in keys}
        warehouse_ids = {key[2] for key in keys}
        rows = (
            await session.exec(
                select(InvItemWarehouseSetting).where(
                    InvItemWarehouseSetting.item_id.in_(item_ids),
                    InvItemWarehouseSetting.warehouse_id.in_(warehouse_ids),
                    InvItemWarehouseSetting.deleted_at.is_(None),
                )
            )
        ).all()
        return {
            (row.item_id, row.org_id, row.warehouse_id): (
                Decimal(row.min_quantity),
                Decimal(row.max_quantity),
            )
            for row in rows
            if (row.item_id, row.org_id, row.warehouse_id) in keys
        }


repository = StockWarningRepository()
