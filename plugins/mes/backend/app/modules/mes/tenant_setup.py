"""MES 租户初始化。

MES P0 的基础字典来自 catalog.DICT_ITEMS；后续工作中心、日历和状态策略
会在此以幂等配置补齐，不覆盖工厂已经调整的配置。
"""


async def setup_tenant(session, ctx) -> None:
    from app.modules.inventory.public import ensure_stock_order_types
    from .inventory_service import TYPES
    from .warehouse_scenes import type_specifications
    specifications = []
    for index, (_, (number, name, direction)) in enumerate(TYPES.items()):
        specifications.append(dict(type_no=number, type_name=name, direction_code=direction,
            default_from_status_code="available" if direction == "out" else None,
            default_to_status_code="available" if direction == "in" else None,
            is_approval_required=False, required_field_config={"form": "inbound" if direction == "in" else "outbound", "source_managed": True, "no_prefix": "MESRK" if direction == "in" else "MESCK"}, sort_no=200+index))
    await ensure_stock_order_types(session, specifications + type_specifications(), ctx.admin_user_id)
    from app.modules.menu.public import retire_empty_directory, hide_legacy_entry, upgrade_legacy_page
    await retire_empty_directory(session, menu_key="Mes", expected_path="/mes", user_id=ctx.admin_user_id)
    await hide_legacy_entry(session, menu_key="MesInventory", expected_path="/mes/inventory", user_id=ctx.admin_user_id)
    await upgrade_legacy_page(session, menu_key="MesQuality", expected_path="/mes/quality",
        previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
        obsolete_route_meta={"mes_domain": "quality"}, user_id=ctx.admin_user_id)
    await upgrade_legacy_page(session, menu_key="MesScheduling", expected_path="/mes/scheduling",
        previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
        obsolete_route_meta={"mes_domain": "scheduling"}, user_id=ctx.admin_user_id)
