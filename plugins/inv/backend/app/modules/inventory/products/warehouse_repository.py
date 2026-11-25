"""物料适用仓库的范围查询与有效期持久化；不修改库存或安全阈值。"""
from sqlalchemy import func, inspect, text, union
from sqlmodel import select
from app.auth.scope_filters import scoped_conditions, register_related_scope, resolve_effective_data_scope
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.organization.models import SysOrg
from ..models import InvItemWarehouse, InvWarehouse, InvStockBalance, InvStockTransaction
from ..warehouse.access_repository import authorized_warehouse_ids

SHARED_PERMISSION = "inventory_product:manage_shared"


def related_material_condition(model, user):
    """物料归属按有效适用关系及明确管理账号，不按建档人或角色名称。"""
    now = utc_now()
    return select(InvItemWarehouse.id).join(InvWarehouse, InvWarehouse.id == InvItemWarehouse.warehouse_id).where(
        InvItemWarehouse.item_id == model.id, InvItemWarehouse.warehouse_id.in_(authorized_warehouse_ids(user)),
        InvItemWarehouse.org_id == InvWarehouse.org_id, InvItemWarehouse.valid_from <= now,
        (InvItemWarehouse.valid_to.is_(None) | (InvItemWarehouse.valid_to > now))).exists()


register_related_scope("md_item", related_material_condition)


class ItemWarehouseRepository:
    async def require_scope_ready(self, session, user, permission):
        if resolve_effective_data_scope(user, permission) != "related":
            return
        await self.require_ready(session)
        if session.get_bind().dialect.name == "postgresql":
            ready = bool(await session.scalar(text("SELECT to_regclass('inv_warehouse_user') IS NOT NULL")))
        else:
            ready = await session.run_sync(lambda sync: inspect(sync.connection()).has_table("inv_warehouse_user"))
        if not ready:
            raise AppException("仓库管理账号授权尚未完成数据库升级，请联系管理员", 503)

    async def shared_item_ids(self, session, item_ids):
        if not item_ids:
            return set()
        await self.require_ready(session)
        # 当前多仓适用或存在跨仓实际使用历史；撤销配置不抹去库存和流水事实。
        now = utc_now()
        uses = union(select(InvItemWarehouse.item_id, InvItemWarehouse.warehouse_id).where(InvItemWarehouse.item_id.in_(item_ids),
                InvItemWarehouse.valid_from <= now, (InvItemWarehouse.valid_to.is_(None) | (InvItemWarehouse.valid_to > now))),
            select(InvStockBalance.item_id, InvStockBalance.warehouse_id).where(InvStockBalance.item_id.in_(item_ids)),
            select(InvStockTransaction.item_id, InvStockTransaction.from_warehouse_id.label("warehouse_id")).where(
                InvStockTransaction.item_id.in_(item_ids), InvStockTransaction.from_warehouse_id.is_not(None)),
            select(InvStockTransaction.item_id, InvStockTransaction.to_warehouse_id.label("warehouse_id")).where(
                InvStockTransaction.item_id.in_(item_ids), InvStockTransaction.to_warehouse_id.is_not(None))).subquery()
        return set((await session.exec(select(uses.c.item_id).group_by(uses.c.item_id)
            .having(func.count(func.distinct(uses.c.warehouse_id)) > 1))).all())

    async def editable_base_ids(self, session, item_ids, user):
        if SHARED_PERMISSION in user.permissions:
            return set(item_ids)
        if not await self.ready(session):
            return set()
        return set(item_ids) - await self.shared_item_ids(session, item_ids)

    async def require_basic_edit(self, session, item, changes, user, *, deleting=False):
        changed = deleting or any(getattr(item, key, None) != value for key, value in changes.items())
        if changed and item.id not in await self.editable_base_ids(session, [item.id], user):
            raise AppException("该物料已被多个仓库共用，基础信息由具备共享物料维护权限的管理员统一维护；可调整本人管理仓库的适用关系", 403)

    async def lock_targets(self, session, warehouse_ids, user, permission):
        """与入库保持仓库→物料锁顺序，避免关系外键写入与记账形成反向等待。"""
        if warehouse_ids:
            await session.exec(select(InvWarehouse).where(InvWarehouse.id.in_(set(warehouse_ids)),
                *scoped_conditions(InvWarehouse, user, permission, include_deleted=True))
                .order_by(InvWarehouse.id).with_for_update().execution_options(populate_existing=True))

    async def ready(self, session):
        if session.get_bind().dialect.name == "postgresql":
            return bool(await session.scalar(text("SELECT to_regclass('inv_item_warehouse') IS NOT NULL")))
        return await session.run_sync(lambda sync: inspect(sync.connection()).has_table("inv_item_warehouse"))

    async def require_ready(self, session):
        if not await self.ready(session):
            raise AppException("物料适用仓库配置尚未完成数据库升级，请联系管理员", 503)

    @staticmethod
    def applies(item_id, warehouse_id):
        now = utc_now()
        return select(InvItemWarehouse.id).where(InvItemWarehouse.item_id == item_id,
            InvItemWarehouse.warehouse_id == warehouse_id, InvItemWarehouse.org_id == InvWarehouse.org_id,
            InvWarehouse.id == warehouse_id, InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
            InvItemWarehouse.valid_from <= now,
            (InvItemWarehouse.valid_to.is_(None) | (InvItemWarehouse.valid_to > now))).exists()

    async def warehouses(self, session, user, permission, *, include_inactive=False):
        await self.require_scope_ready(session, user, permission)
        query = select(InvWarehouse, SysOrg.org_name).join(SysOrg, SysOrg.id == InvWarehouse.org_id).where(
            *scoped_conditions(InvWarehouse, user, permission, include_deleted=include_inactive))
        if not include_inactive:
            query = query.where(InvWarehouse.is_active.is_(True), SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True))
        return list((await session.exec(query.order_by(SysOrg.org_name, InvWarehouse.warehouse_name, InvWarehouse.id))).all())

    async def references(self, session, item_ids, user, permission):
        if not item_ids or not await self.ready(session):
            return {}
        visible = {row.id: (row, org) for row, org in await self.warehouses(session, user, permission, include_inactive=True)}
        rows = (await session.exec(select(InvItemWarehouse).where(InvItemWarehouse.item_id.in_(item_ids),
            InvItemWarehouse.valid_to.is_(None), InvItemWarehouse.valid_from <= utc_now()))).all()
        result = {}
        for row in rows:
            if row.warehouse_id in visible:
                warehouse, org = visible[row.warehouse_id]
                result.setdefault(row.item_id, []).append({"id": str(warehouse.id), "warehouse_name": warehouse.warehouse_name,
                    "org_name": org, "is_available": warehouse.is_active and warehouse.deleted_at is None})
        for references in result.values():
            references.sort(key=lambda reference: (reference["org_name"], reference["warehouse_name"], reference["id"]))
        return result

    async def replace(self, session, item_id, warehouse_ids, user, permission):
        await self.require_ready(session)
        requested = set(warehouse_ids)
        manageable = {row.id: row for row, _ in await self.warehouses(session, user, permission, include_inactive=True)}
        current = list((await session.exec(select(InvItemWarehouse).where(InvItemWarehouse.item_id == item_id,
            InvItemWarehouse.valid_to.is_(None)).with_for_update())).all())
        existing = {row.warehouse_id for row in current}
        additions = requested - existing
        for warehouse_id in additions:
            warehouse = manageable.get(warehouse_id)
            if warehouse is None or not warehouse.is_active or warehouse.deleted_at is not None:
                raise AppException("适用仓库包含已停用、不存在或无权配置的仓库", 403)
        now = utc_now()
        # 当前账号不可管理的其他组织关系保留，不因局部编辑被撤销。
        for row in current:
            if row.warehouse_id in manageable and row.warehouse_id not in requested:
                row.valid_to = row.updated_at = now
                row.updated_by = user.user_id
                session.add(row)
        for warehouse_id in sorted(additions, key=str):
            session.add(InvItemWarehouse(item_id=item_id, warehouse_id=warehouse_id, org_id=manageable[warehouse_id].org_id,
                valid_from=now, created_by=user.user_id, updated_by=user.user_id))
        await session.flush()

    async def disallowed(self, session, pairs):
        """调用方已锁定物料及仓库；逐个批量检查明确的目标组合，不以余额放行。"""
        await self.require_ready(session)
        wanted = set(pairs)
        now = utc_now()
        rows = (await session.exec(select(InvItemWarehouse.item_id, InvItemWarehouse.warehouse_id).join(
            InvWarehouse, InvWarehouse.id == InvItemWarehouse.warehouse_id).where(
                InvItemWarehouse.item_id.in_({item_id for item_id, _ in wanted}),
                InvItemWarehouse.warehouse_id.in_({warehouse_id for _, warehouse_id in wanted if warehouse_id}),
                InvItemWarehouse.org_id == InvWarehouse.org_id,
                InvItemWarehouse.valid_from <= now,
                (InvItemWarehouse.valid_to.is_(None) | (InvItemWarehouse.valid_to > now)),
                InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True)))).all()
        allowed = {(item_id, warehouse_id) for item_id, warehouse_id in rows}
        return list(wanted - allowed)


repository = ItemWarehouseRepository()
