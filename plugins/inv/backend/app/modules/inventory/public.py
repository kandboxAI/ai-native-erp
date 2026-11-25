"""库存对其他模块的公开契约；写操作复用审批、记账和来源校验。

调用方先校验来源业务范围，库存服务继续校验库存权限和仓库范围。
传入的会话由调用方提交，保证同库业务关联、库存流水和事件共同回滚。
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import MdItem
from .item_repository import active_item_options
from .item_repository import active_items_by_numbers


async def list_active_item_options(session: AsyncSession, keyword: str = "", limit: int = 50) -> list[dict]:
    """租户共享物料目录。调用方须先鉴权；只返回单据选料所需的公开字段。"""
    return [dict(row) for row in await active_item_options(session, keyword, min(max(limit, 1), 50))]


async def find_active_items_by_numbers(session: AsyncSession, item_numbers: list[str]) -> list[dict]:
    """按外部单据提供的编号精确匹配共享物料；调用方先鉴权并限定来源单据范围。

    仅返回选料所需字段，不创建物料、不读取价格/库存；大小写重复编号由调用方明确处理。
    """
    numbers = list(dict.fromkeys(value.strip().lower() for value in item_numbers if value.strip()))
    if len(numbers) > 500:
        raise ValueError("单次最多匹配 500 个物料编号")
    return [dict(row) for row in await active_items_by_numbers(session, numbers)]


async def ensure_active_item(session, *, item_no: str, item_name: str, unit_code: str, specification: str | None, user):
    """按调用方确认的稳定编号幂等建档；不提交、不初始化库存、不覆盖已有物料。

    调用方必须校验业务来源和单位字典；真正新增还须拥有 inventory_product:create。
    业务批量调用按 item_no 排序，避免相反顺序持锁。
    """
    from app.core.exceptions import AppException
    from .item_repository import lock_item_number, items_by_number
    from .products.repository import item_repository
    from .products.schemas import ItemCreate
    payload = ItemCreate(item_no=item_no, item_name=item_name, unit_code=unit_code, specification=specification).model_dump(exclude_unset=True)
    await lock_item_number(session, item_no)
    existing = await items_by_number(session, item_no)
    if len(existing) > 1:
        raise AppException("物料编号存在大小写重复，请先核对档案", 409)
    if existing:
        item = existing[0]
        if not item.is_active or item.unit_code != unit_code:
            raise AppException("对应货品档案已停用或单位不一致，请核对后再安排生产", 409)
        return item
    if "inventory_product:create" not in user.permissions:
        raise AppException("当前货品尚未建档，需要新增物料权限，或选择已有生产物料", 403)
    return await item_repository.create_in_session(session, payload, user)

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from .products.repository import item_repository
from .products.schemas import ItemOption
from .warehouse.schemas import WarehouseDepartmentReference
from .stock_order.rules import StockOrderRule, register_stock_order_rule


async def first_active_item(session: AsyncSession) -> MdItem | None:
    return (
        await session.exec(
            select(MdItem)
            .where(MdItem.deleted_at.is_(None), MdItem.is_active.is_(True))
            .order_by(MdItem.item_no)
        )
    ).first()


async def get_active_item(session: AsyncSession, item_id: UUID) -> MdItem | None:
    """读取可用于业务单据快照的物料；不暴露库存内部余额。"""
    return (
        await session.exec(
            select(MdItem).where(
                MdItem.id == item_id,
                MdItem.deleted_at.is_(None),
                MdItem.is_active.is_(True),
            )
        )
    ).first()


async def lock_inventory_items(session: AsyncSession, item_ids: set[UUID]) -> None:
    """已授权组合动作的事务锁契约：与库存过账统一物料锁，调用方不得提前提交。"""
    from .stock_order.repository import repository
    await repository.lock_items(session, sorted(item_ids, key=str))


async def warehouse_department_reference(session: AsyncSession, *, owner_org_id: UUID, department_id: UUID) -> WarehouseDepartmentReference | None:
    """已授权组合动作的目录引用契约：本级及有效下级组织的启用部门，仅返回 ID/名称和归属。

    调用方须先校验 owner_org_id 的实际操作权限；该引用不扩大下级组织的业务数据权限。
    与仓库下拉、保存使用同一查询，避免入库自动登记采用不同资格规则。
    """
    from .warehouse.repository import warehouse_repository
    return await warehouse_repository.department_reference(session, department_id, owner_org_id)


async def warehouse_custodian_reference(session, *, owner_org_id, user_id):
    """调用方先授权根组织；仅提供有效组织子树的保管人目录引用。"""
    from .warehouse.repository import warehouse_repository
    return await warehouse_repository.custodian_reference(session, user_id, owner_org_id)


async def asset_registration_directory(session, user, org_id):
    """已授权资产新增动作的责任目录；不授予下级业务数据访问权。"""
    from app.auth.scope_filters import ensure_org_access
    from .warehouse.repository import warehouse_repository
    if "asset_register:create" not in user.permissions:
        raise AppException("无权选择资产责任信息", status_code=403)
    ensure_org_access(user, org_id, "asset_register:create")
    return {
        "departments": await warehouse_repository.department_options(session, user, "asset_register:create", org_id=org_id),
        "users": await warehouse_repository.custodian_options(session, user, "asset_register:create", org_id=org_id),
    }


async def asset_registration_warehouses(session, user, org_id):
    """按真实入库新增范围发布当前组织的仓库引用，仓库以外的数据不返回。"""
    from .warehouse.repository import warehouse_repository
    if not {"inventory_inbound:create", "inventory_inbound:confirm"}.issubset(user.permissions):
        return []
    return [row for row in await warehouse_repository.options(session, user, "inventory_inbound:create",
        additional_permissions=("inventory_inbound:confirm",)) if row.org_id == org_id]


async def asset_registration_warehouse(session, user, warehouse_id, org_id):
    from app.auth.scope_filters import ensure_org_access
    from .warehouse.repository import warehouse_repository
    for permission in ("inventory_inbound:create", "inventory_inbound:confirm"):
        if permission not in user.permissions:
            raise AppException("指定仓库登记需要入库新增和确认权限", status_code=403)
        ensure_org_access(user, org_id, permission)
    warehouse = await warehouse_repository.asset_registration_target(session, warehouse_id, user)
    if warehouse is None or warehouse.org_id != org_id:
        raise AppException("目标仓库不存在、已停用或不属于所选组织", status_code=400)
    return {key: getattr(warehouse, key) for key in (
        "id", "org_id", "location_id", "default_asset_department_id", "default_asset_custodian_user_id")}


async def receive_registered_assets(session, user, *, org_id, warehouse_id, item_id, quantity, registration, remark):
    """简洁资产登记的库存写入契约；复用其他入库，在调用方事务内确认，不提交。"""
    from .stock_order.repository import type_repository
    from .stock_order.service import service
    from .stock_order.schemas import OrderCreate, OrderLineWrite
    await asset_registration_warehouse(session, user, warehouse_id, org_id)
    order_type = await type_repository.find_by_no(session, "OTHER_IN")
    if order_type is None or not order_type.is_active:
        raise AppException("缺少启用的其他入库类型，请检查库存基础配置", status_code=409)
    order = await service.create_in_session(session, OrderCreate(order_type_id=order_type.id,
        org_id=org_id, to_warehouse_id=warehouse_id, reason="资产登记入库", remark=remark,
        lines=[OrderLineWrite(item_id=item_id, quantity=quantity, unit_price=registration.get("original_amount"),
            remark=remark, tracking={"asset": {"registration": registration}})], confirm=True), user, use_reference_price=False)
    return order.id


from .stock_order.schemas import OrderCreate as StockOrderCreate, OrderLineWrite as StockOrderLine
from .stock_order.service import service as _orders
from .stock_order.confirmation import register_confirmation_validator
from .stock_order.write_validation import register_write_validator
from .stock_order.lifecycle import register_source_document_handler, register_source_mutation_guard
from . import integration_repository as _integration


async def create_stock_order(session, payload: StockOrderCreate, user) -> dict:
    """调用方已校验来源业务；库存仍检查本模块权限、仓库、审批。事务由调用方提交。"""
    order = await _orders.create_in_session(session, payload, user)
    return dict(id=order.id, status_code=order.status_code, order_no=order.order_no)


async def confirm_stock_order(session, order_id: UUID, user) -> dict:
    order = await _orders.confirm_in_session(session, order_id, user)
    return dict(id=order.id, status_code=order.status_code, order_no=order.order_no)


async def cancel_stock_order(session, order_id: UUID, reason: str, user) -> dict:
    briefs = await _integration.order_briefs(session, {order_id})
    source = briefs.get(order_id)
    if source is None: raise AppException("库存来源单据不存在", 404)
    if source["is_reversed"] or source["status_code"] == "voided": return source
    if source["status_code"] == "confirmed":
        row = await _orders.reverse_in_session(session, order_id, reason, user)
    else:
        row = await _orders.void_in_session(session, order_id, reason, user)
    return dict(id=row.id, status_code=row.status_code, order_no=row.order_no)


async def get_stock_order_states(session, ids) -> dict:
    """内部来源查询：只接受已通过调用方业务范围校验的库存单据 ID，禁止直接对外发布。"""
    return await _integration.order_briefs(session, set(ids))


async def get_stock_order_lots(session, order_id: UUID) -> list[dict]:
    """来源业务查询实际记账批次及数量，调用方先校验来源可读范围。"""
    return await _integration.order_lots(session, order_id)


async def get_stock_order_type(session, type_no: str) -> dict:
    row = await _integration.stock_type(session, type_no)
    if row is None or not row.is_active: raise AppException("所需库存单据类型未配置或已停用，请同步租户配置")
    return dict(id=row.id, direction_code=row.direction_code, is_approval_required=row.is_approval_required,
        is_negative_allowed=row.is_negative_allowed, default_from_status_code=row.default_from_status_code, default_to_status_code=row.default_to_status_code)


async def ensure_stock_order_types(session, specifications, user_id) -> None:
    """显式租户开通时幂等补齐调用方拥有的类型，不覆盖已有客户配置。"""
    await _integration.ensure_types(session, specifications, user_id)


async def list_stock_warehouses(session, user, permission: str, *, scope_key=None) -> list[dict]:
    if permission not in user.permissions: raise AppException("缺少库存操作权限", 403)
    return await _integration.warehouses(session, user, permission, scope_key)


async def get_stock_order_allocations(session, ids):
    """已授权来源单据的计划扣减批次；待审批单据也按此占用业务额度。"""
    return await _integration.order_allocations(session, set(ids))


async def list_configured_warehouses(session, scope_key, user):
    from .warehouse_scope import get_scope
    spec = get_scope(scope_key, user)
    if spec.list_permission not in user.permissions: raise AppException("缺少仓库配置查询权限", 403)
    rows = await _integration.warehouse_records(session, scope_key, user)
    return [dict(id=row.id, org_id=row.org_id, warehouse_no=row.warehouse_no, warehouse_name=row.warehouse_name,
        warehouse_type_code=row.warehouse_type_code, is_active=row.is_active, can_manage=row.warehouse_type_code in spec.types) for row in rows]


async def configure_warehouse(session, scope_key, payload, user, *, warehouse_id=None):
    row = await _integration.configure_warehouse(session, scope_key, payload, user, warehouse_id)
    return dict(id=row.id, org_id=row.org_id, warehouse_no=row.warehouse_no, warehouse_name=row.warehouse_name,
        warehouse_type_code=row.warehouse_type_code, is_active=row.is_active)


async def get_stock_warehouse(session, warehouse_id):
    """内部业务校验所需最小仓库字段；不作为无鉴权查询发布。"""
    from .warehouse.repository import warehouse_repository
    rows = await warehouse_repository.get_many(session, {warehouse_id})
    row = rows.get(warehouse_id)
    return None if row is None else dict(id=row.id, org_id=row.org_id, warehouse_no=row.warehouse_no, warehouse_type_code=row.warehouse_type_code)


async def ensure_zero_stock_positions(session, warehouse_id, item_ids, user, *, scope_key=None):
    """显式初始化启用物料的仓库零余额位置；不改已有余额，事务由调用方提交。"""
    if "inventory_inbound:list" not in user.permissions:
        raise AppException("缺少库存入库权限", 403)
    return await _integration.ensure_zero_positions(session, warehouse_id, item_ids, user, scope_key)


async def list_item_lots(session, item_id: UUID) -> list[dict]:
    """共享物料的批次选择；调用方先完成业务鉴权。"""
    return await _integration.lots(session, item_id)


async def warehouse_category_item_options(
    session: AsyncSession, current_user: AuthenticatedUser, *,
    permission_key: str, category_name: str, warehouse_no: str | None = None,
    item_ids: set[UUID] | None = None,
) -> list[ItemOption]:
    """跨模块只读契约：返回已关联授权仓库、指定分类的启用物料元数据。

    查询和数据范围由库存Repository执行；不返回库存余额或审计人员等字段。
    permission_key须为调用方本次动作的真实授权，不按角色名放行。
    省略 warehouse_no 时查询全部授权仓库；保留该参数供旧调用方精确筛选。
    """
    if permission_key not in current_user.permissions:
        raise AppException("无权查询关联物料", status_code=403)
    return await item_repository.warehouse_category_options(
        session, current_user, permission_key=permission_key,
        warehouse_no=warehouse_no, category_name=category_name, item_ids=item_ids,
    )


__all__ = [
    "first_active_item",
    "get_active_item",
    "list_active_item_options",
    "StockOrderCreate",
    "StockOrderLine",
    "create_stock_order",
    "confirm_stock_order",
    "cancel_stock_order",
    "get_stock_order_states",
    "get_stock_order_lots",
    "get_stock_order_type",
    "ensure_stock_order_types",
    "list_stock_warehouses",
    "list_item_lots",
    "get_stock_order_allocations",
    "list_configured_warehouses",
    "configure_warehouse",
    "get_stock_warehouse",
    "register_confirmation_validator",
    "register_write_validator",
    "register_source_document_handler",
    "register_source_mutation_guard",
    "warehouse_category_item_options",
    "warehouse_department_reference",
    "warehouse_custodian_reference",
    "asset_registration_directory",
    "asset_registration_warehouses",
    "asset_registration_warehouse",
    "receive_registered_assets",
    "StockOrderRule",
    "register_stock_order_rule",
    "find_active_items_by_numbers",
    "ensure_active_item",
    "ensure_zero_stock_positions",
    "lock_inventory_items",
]
async def save_catalog_item(session, values, item_id, user, *, permission_key):
    """行业扩展维护物料的事务内公开入口；调用方先校验行业档案范围。

    只接受物料基础字段，不接受库存、资产配置或行业属性。共用调用方事务。
    """
    from app.core.exceptions import AppException
    from .material_catalog_repository import save_item
    allowed = {"item_no", "item_name", "category_name", "specification", "unit_code", "is_active", "remark"}
    if permission_key not in user.permissions or set(values) - allowed:
        raise AppException("无权维护物料档案", status_code=403)
    return await save_item(session, dict(values), item_id, user.user_id, user=user)


async def toggle_catalog_item(session, item_id, is_active, user, *, permission_key):
    from app.core.exceptions import AppException
    from .material_catalog_repository import toggle_item
    if permission_key not in user.permissions:
        raise AppException("无权维护物料档案", status_code=403)
    return await toggle_item(session, item_id, is_active, user.user_id, user=user)
