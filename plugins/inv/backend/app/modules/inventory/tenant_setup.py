"""物资模块的租户开通数据：内置库存单据类型（MES 领域数据模型 §7.4）。

类型记录保留单据关联；处理方式、审批与必填项由代码固定。
这里只在类型编号不存在时新增（可重复执行），不覆盖历史类型记录。
"""

from __future__ import annotations

from sqlmodel import select

from app.modules.miniapp_menu.service import ensure_catalog_entries
from app.modules.role_miniapp_menu.service import grant_for_permission

from .catalog import MINIAPP_MENUS
from .constants import CANTEEN_WAREHOUSE_NO, GENERAL_WAREHOUSE_NO
from .models import InvStockOrderType, InvWarehouse
from .stock_order.rules import BUILTIN_RULES

SYSTEM_WAREHOUSES = (
    (GENERAL_WAREHOUSE_NO, "总仓库"),
    (CANTEEN_WAREHOUSE_NO, "食堂仓库"),
)


async def ensure_system_warehouse(session, ctx, warehouse_no: str) -> InvWarehouse:
    config = next((item for item in SYSTEM_WAREHOUSES if item[0] == warehouse_no), None)
    if config is None:
        raise ValueError(f"unknown system warehouse: {warehouse_no}")
    _, warehouse_name = config
    warehouse = (
        await session.exec(
            select(InvWarehouse).where(
                InvWarehouse.org_id == ctx.root_org_id,
                InvWarehouse.warehouse_no == warehouse_no,
            ).order_by(InvWarehouse.deleted_at.is_(None).desc(), InvWarehouse.created_at.desc(), InvWarehouse.id.desc())
        )
    ).first()
    if warehouse is None:
        warehouse = InvWarehouse(
            org_id=ctx.root_org_id,
            warehouse_no=warehouse_no,
            warehouse_name=warehouse_name,
            created_by=ctx.admin_user_id,
            updated_by=ctx.admin_user_id,
        )
        session.add(warehouse)
        await session.flush()
    return warehouse

# 初始化和运行时共用一份代码规则；保留原导出供既有种子调用。
BUILTIN_ORDER_TYPES = [
    (rule.type_no, rule.name, rule.direction, rule.from_status, rule.to_status, rule.approval,
     {"form": rule.form, "no_prefix": rule.no_prefix, "required": list(rule.required)}, rule.sort_no)
    for rule in BUILTIN_RULES
]


async def setup_tenant(session, ctx) -> None:
    for warehouse_no, *_ in SYSTEM_WAREHOUSES:
        await ensure_system_warehouse(session, ctx, warehouse_no)
    existing = set((await session.exec(select(InvStockOrderType.type_no))).all())
    for type_no, name, direction, from_status, to_status, approval, config, sort_no in BUILTIN_ORDER_TYPES:
        if type_no in existing:
            continue
        session.add(
            InvStockOrderType(
                type_no=type_no,
                type_name=name,
                direction_code=direction,
                default_from_status_code=from_status,
                default_to_status_code=to_status,
                is_approval_required=approval,
                required_field_config=config,
                is_negative_allowed=False,
                is_builtin=True,
                is_active=True,
                sort_no=sort_no,
            )
        )
    for menu in await ensure_catalog_entries(session, MINIAPP_MENUS):
        await grant_for_permission(session, menu.id, "inventory_stock_alert:list")
    await session.flush()
