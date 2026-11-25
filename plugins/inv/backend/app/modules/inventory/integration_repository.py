"""上层业务集成的最小读写契约实现；不导入任何上层业务模块。"""
from sqlalchemy import select
from app.auth.scope_filters import scoped_conditions
from .models import InvStockOrder, InvStockOrderLine, InvStockOrderType, InvStockTransaction, InvWarehouse, InvLot
from .constants import SYSTEM_WAREHOUSE_NOS
from .warehouse_scope import get_scope, warehouse_condition
from app.core.exceptions import AppException
from app.framework.db.models import utc_now


async def ensure_zero_positions(session, warehouse_id, item_ids, user, scope_key):
    """只建立缺失的零余额位置，不改已有数量、不创建零金额/零数量流水。"""
    from .models import MdItem
    from .stock_order.repository import repository as stock_repository
    warehouse = (await session.execute(select(InvWarehouse).where(InvWarehouse.id == warehouse_id,
        InvWarehouse.is_active.is_(True), warehouse_condition(scope_key, user),
        *scoped_conditions(InvWarehouse, user, "inventory_inbound:list")))).scalar_one_or_none()
    if warehouse is None:
        raise AppException("目标仓库不存在、已停用或不在入库范围内", 403)
    identifiers = set(item_ids)
    items = (await session.execute(select(MdItem.id).where(MdItem.id.in_(identifiers),
        MdItem.is_active.is_(True), MdItem.deleted_at.is_(None), MdItem.is_lot_controlled.is_(False)))).scalars().all()
    if set(items) != identifiers:
        raise AppException("零余额位置只能引用启用且不按批次管理的物料", 422)
    for identifier in sorted(identifiers, key=str):
        row = await stock_repository.ensure_balance(session, org_id=warehouse.org_id, item_id=identifier,
            warehouse_id=warehouse.id, lot_id=None, stock_status_code="available", user_id=user.user_id)
        if row.org_id != warehouse.org_id:
            raise AppException("已有库存位置组织与仓库不一致，未覆盖", 409)
    return len(identifiers)


async def order_briefs(session, ids):
    if not ids: return {}
    rows = (await session.execute(select(InvStockOrder).where(InvStockOrder.id.in_(ids)))).scalars().all()
    reversals = (await session.execute(select(InvStockOrder.reversal_of_order_id, InvStockOrder.id).where(
        InvStockOrder.reversal_of_order_id.in_(ids), InvStockOrder.status_code == "confirmed"))).all()
    reversed_ids = dict(reversals)
    return {row.id: dict(id=row.id, order_no=row.order_no, status_code=row.status_code, business_date=row.business_date,
        org_id=row.org_id, reversal_id=reversed_ids.get(row.id), is_reversed=row.id in reversed_ids) for row in rows}


async def order_lots(session, order_id):
    rows = (await session.execute(select(InvStockTransaction, InvStockOrderLine.unit_price, InvLot.lot_no).join(InvStockOrderLine,
        InvStockOrderLine.id == InvStockTransaction.stock_order_line_id).outerjoin(InvLot, InvLot.id == InvStockTransaction.lot_id)
        .where(InvStockTransaction.stock_order_id == order_id))).all()
    return [dict(lot_id=row.lot_id, lot_no=number, item_id=row.item_id, quantity=row.quantity,
        warehouse_id=row.from_warehouse_id or row.to_warehouse_id, unit_price=price) for row, price, number in rows]


async def stock_type(session, number):
    return (await session.execute(select(InvStockOrderType).where(InvStockOrderType.type_no == number,
        InvStockOrderType.deleted_at.is_(None)))).scalars().first()


async def warehouses(session, user, permission, scope_key=None):
    rows = (await session.execute(select(InvWarehouse).where(*scoped_conditions(InvWarehouse, user, permission),
        InvWarehouse.is_active.is_(True), warehouse_condition(scope_key, user)).order_by(InvWarehouse.warehouse_no))).scalars().all()
    return [dict(id=row.id, org_id=row.org_id, warehouse_no=row.warehouse_no, warehouse_type_code=row.warehouse_type_code, label=f"{row.warehouse_name}（{row.warehouse_no}）") for row in rows]


async def order_allocations(session, ids):
    if not ids: return {}
    rows = (await session.execute(select(InvStockOrderLine).where(InvStockOrderLine.stock_order_id.in_(ids)).order_by(InvStockOrderLine.line_no))).scalars().all()
    result = {}
    for row in rows:
        result.setdefault(row.stock_order_id, []).append(dict(item_id=row.item_id, lot_id=row.lot_id, quantity=row.quantity,
            warehouse_id=row.from_warehouse_id, unit_code=row.unit_code))
    return result


async def warehouse_records(session, scope_key, user):
    spec = get_scope(scope_key, user)
    return (await session.execute(select(InvWarehouse).where(*scoped_conditions(InvWarehouse, user, spec.list_permission),
        warehouse_condition(scope_key, user)).order_by(InvWarehouse.warehouse_no))).scalars().all()


async def configure_warehouse(session, scope_key, payload, user, warehouse_id=None):
    from app.auth.scope_filters import resolve_write_org_id
    from sqlalchemy import or_
    spec = get_scope(scope_key, user)
    if spec.manage_permission not in user.permissions: raise AppException("缺少仓库配置权限", 403)
    if warehouse_id:
        row = (await session.execute(select(InvWarehouse).where(InvWarehouse.id == warehouse_id,
            *scoped_conditions(InvWarehouse, user, spec.manage_permission)).with_for_update())).scalars().first()
        if row is None or row.warehouse_type_code not in spec.types: raise AppException("仓库不存在或不属于可维护的业务仓库", 404)
        if set(payload) - {"warehouse_name", "warehouse_type_code", "is_active"}: raise AppException("仓库编号和组织创建后不能变更")
        history = select(InvStockOrder.id).where(or_(InvStockOrder.from_warehouse_id == row.id, InvStockOrder.to_warehouse_id == row.id,
            InvStockOrder.id.in_(select(InvStockOrderLine.stock_order_id).where(or_(InvStockOrderLine.from_warehouse_id == row.id, InvStockOrderLine.to_warehouse_id == row.id))))).limit(1)
        if payload.get("warehouse_type_code", row.warehouse_type_code) != row.warehouse_type_code and (await session.execute(history)).first():
            raise AppException("已有库存单据，不能改变仓库用途", 409)
        if payload.get("is_active") is False:
            from .models import InvStockBalance
            stock = (await session.execute(select(InvStockBalance.id).where(InvStockBalance.warehouse_id == row.id,
                or_(InvStockBalance.quantity != 0, InvStockBalance.reserved_quantity != 0)).limit(1))).first()
            pending = (await session.execute(history.where(InvStockOrder.status_code.in_(["draft", "submitted", "approved"])))).first()
            if stock or pending: raise AppException("仓库仍有库存、预留或未记账单据，不能停用", 409)
    else:
        if payload["warehouse_no"] in SYSTEM_WAREHOUSE_NOS: raise AppException("该仓库编号由系统保留")
        row = InvWarehouse(**{**payload, "org_id": resolve_write_org_id(user, payload["org_id"], spec.manage_permission)}, created_by=user.user_id, updated_by=user.user_id)
    if payload.get("warehouse_type_code", row.warehouse_type_code) not in spec.types: raise AppException("不支持的业务仓库用途")
    for key, value in payload.items():
        if key != "org_id": setattr(row, key, value)
    row.updated_at, row.updated_by = utc_now(), user.user_id
    session.add(row)
    await session.flush()
    return row


async def lots(session, item_id):
    rows = (await session.execute(select(InvLot).where(InvLot.item_id == item_id).order_by(InvLot.lot_no).limit(100))).scalars().all()
    return [dict(id=row.id, label=row.lot_no) for row in rows]


async def ensure_types(session, specifications, user_id):
    for specification in specifications:
        if await stock_type(session, specification["type_no"]) is None:
            session.add(InvStockOrderType(**specification, is_builtin=True, is_active=True, is_negative_allowed=False,
                created_by=user_id, updated_by=user_id))
    await session.flush()
