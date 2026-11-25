"""仓库账号授权及关联数据范围；只发布当前有效的仓库引用。"""
from sqlalchemy import and_, or_
from sqlmodel import select

from app.auth.scope_filters import accessible_org_ids, register_related_scope, table_scope_condition, resolve_effective_data_scope, has_all_organization_access
from app.framework.db.models import utc_now
from app.modules.user_profile.models import SysUser
from ..models import InvWarehouse, InvWarehouseUser, InvStockOrderLine

AUTHORIZE = "inventory_warehouse:authorize"


def authorized_warehouse_ids(user):
    conditions = [
        InvWarehouseUser.user_id == user.user_id,
        InvWarehouseUser.warehouse_id == InvWarehouse.id,
        InvWarehouseUser.org_id == InvWarehouse.org_id,
        InvWarehouseUser.valid_from <= utc_now(),
        InvWarehouseUser.valid_to.is_(None),
        InvWarehouse.deleted_at.is_(None),
        InvWarehouse.is_active.is_(True),
    ]
    if user.org_access_mode_code != "all":
        conditions.append(InvWarehouse.org_id.in_(accessible_org_ids(user)))
    return select(InvWarehouse.id).join(
        InvWarehouseUser, InvWarehouseUser.warehouse_id == InvWarehouse.id
    ).where(*conditions)


def related_warehouse_condition(model, user):
    """关联范围必须有显式账号授权；调拨须同时拥有两端及所有明细仓库。"""
    ids = authorized_warehouse_ids(user)
    if model.__tablename__ == "inv_warehouse":
        return model.id.in_(ids)
    if hasattr(model, "warehouse_id"):
        return model.warehouse_id.in_(ids)
    columns = [model.from_warehouse_id, model.to_warehouse_id]
    any_warehouse = or_(*(column.is_not(None) for column in columns))
    permitted = and_(*(or_(column.is_(None), column.in_(ids)) for column in columns))
    if model.__tablename__ == "inv_stock_order":
        line = InvStockOrderLine.__table__.alias("access_line")
        refs = [line.c.from_warehouse_id, line.c.to_warehouse_id]
        has_line = select(line.c.id).where(line.c.stock_order_id == model.id,
            or_(*(column.is_not(None) for column in refs))).exists()
        forbidden_line = select(line.c.id).where(line.c.stock_order_id == model.id,
            or_(*(and_(column.is_not(None), column.not_in(ids)) for column in refs))).exists()
        return and_(or_(any_warehouse, has_line), permitted, ~forbidden_line)
    return and_(any_warehouse, permitted)


for _table in ("inv_warehouse", "inv_stock_balance", "inv_stock_transaction", "inv_stock_order",
               "inv_item_warehouse_setting", "inv_material_requisition"):
    register_related_scope(_table, related_warehouse_condition)


class WarehouseAccessRepository:
    async def managed(self, session, warehouse_id, user, *, lock=False):
        query = select(InvWarehouse).where(InvWarehouse.id == warehouse_id, InvWarehouse.deleted_at.is_(None))
        scope = table_scope_condition(InvWarehouse, user, AUTHORIZE)
        if scope is not None:
            query = query.where(scope)
        if lock:
            query = query.with_for_update()
        return (await session.exec(query)).first()

    async def user_options(self, session, warehouse, user):
        # 授权人只读取其组织范围内有效租户账号的 ID、名称；不发布认证、联系方式等字段。
        conditions = [SysUser.deleted_at.is_(None), SysUser.is_active.is_(True)]
        if not has_all_organization_access(user, AUTHORIZE):
            conditions.append(SysUser.org_id.in_(accessible_org_ids(user)))
        rows = (await session.exec(select(SysUser.id, SysUser.display_name, SysUser.org_id, SysUser.department_id)
            .where(*conditions).order_by(SysUser.display_name, SysUser.id))).all()
        result = [{"id": row.id, "display_name": row.display_name or str(row.id), "org_id": row.org_id,
            "is_recommended": (bool(warehouse.default_asset_department_id) and row.department_id == warehouse.default_asset_department_id)
                or row.id == warehouse.default_asset_custodian_user_id} for row in rows]
        return sorted(result, key=lambda row: (not row["is_recommended"], row["display_name"], str(row["id"])))

    async def current(self, session, warehouse_id):
        return list((await session.exec(select(InvWarehouseUser).where(
            InvWarehouseUser.warehouse_id == warehouse_id, InvWarehouseUser.valid_to.is_(None)
        ).order_by(InvWarehouseUser.id))).all())

    async def replace(self, session, warehouse, current, wanted, user):
        now = utc_now()
        retained = set()
        for row in current:
            if row.user_id in wanted:
                retained.add(row.user_id)
            else:
                row.valid_to = now
                row.updated_at = now
                row.updated_by = user.user_id
                session.add(row)
        for user_id in sorted(wanted - retained, key=str):
            session.add(InvWarehouseUser(org_id=warehouse.org_id, warehouse_id=warehouse.id,
                user_id=user_id, valid_from=now, created_by=user.user_id, updated_by=user.user_id))
        warehouse.updated_at = now
        warehouse.updated_by = user.user_id
        session.add(warehouse)
        await session.flush()

    async def can_access(self, session, warehouse_id, user, permission):
        # 调用方已加载并锁定有效仓库、检查原组织授权；只有关联范围需要额外账号关系查询。
        if resolve_effective_data_scope(user, permission) != "related":
            return True
        query = select(InvWarehouse.id).where(InvWarehouse.id == warehouse_id,
            InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True))
        scope = table_scope_condition(InvWarehouse, user, permission)
        if scope is not None:
            query = query.where(scope)
        return (await session.exec(query)).first() is not None


repository = WarehouseAccessRepository()
