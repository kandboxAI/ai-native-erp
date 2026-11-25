"""制造普通收发场景；单据、审批、余额与流水全部归 inv。"""
from app.core.exceptions import AppException
from app.modules.inventory import public as stock
from app.modules.inventory.warehouse_scope import get_scope

# type_no -> 名称、方向、允许仓库用途。生产关联单据仍由 inventory_service 编排。
SCENES = {
    "MES_RAW_IN": ("原料入库", "in", "mes_raw"),
    "MES_TOOL_IN": ("刀具入库", "in", "mes_tool"),
    "MES_RAW_OUT": ("原料出库", "out", "mes_raw"),
    "MES_TOOL_OUT": ("刀具出库", "out", "mes_tool"),
}

for _index, (_number, (_name, _direction, _warehouse_type)) in enumerate(SCENES.items()):
    stock.register_stock_order_rule(stock.StockOrderRule(
        type_no=_number, name=_name, direction=_direction,
        from_status="available" if _direction == "out" else None,
        to_status="available" if _direction == "in" else None, approval=False,
        form="inbound" if _direction == "in" else "outbound", no_prefix=_number,
        sort_no=220 + _index, warehouse_scope_key="mes", warehouse_type_codes=(_warehouse_type,)))


def type_specifications():
    return [dict(
        type_no=number, type_name=name, direction_code=direction,
        default_from_status_code="available" if direction == "out" else None,
        default_to_status_code="available" if direction == "in" else None,
        is_approval_required=False, sort_no=220 + index,
        required_field_config={
            "form": "inbound" if direction == "in" else "outbound",
            "no_prefix": number, "warehouse_scope_key": "mes",
            "warehouse_type_codes": [warehouse_type],
        },
    ) for index, (number, (name, direction, warehouse_type)) in enumerate(SCENES.items())]


async def validate_scene(session, order, order_type, lines, user):
    scene = SCENES.get(order_type.type_no)
    if scene is None:
        return
    get_scope("mes", user)
    name, direction, warehouse_type = scene
    if order_type.direction_code != direction or order_type.is_negative_allowed:
        raise AppException(f"{name}的方向或负库存配置不正确", 409)
    # 冲销也核对所有仓库，但不把原方向套用到反向明细。
    ids = {order.from_warehouse_id, order.to_warehouse_id}
    for line in lines:
        ids.update({line.from_warehouse_id, line.to_warehouse_id})
    ids.discard(None)
    if not ids:
        raise AppException(f"{name}必须选择仓库", 409)
    for identifier in ids:
        warehouse = await stock.get_stock_warehouse(session, identifier)
        if warehouse is None or warehouse["org_id"] != order.org_id or warehouse["warehouse_type_code"] != warehouse_type:
            raise AppException(f"{name}请选择同一组织的{'原料' if warehouse_type == 'mes_raw' else '刀具'}仓库", 409)


stock.register_write_validator(validate_scene)
stock.register_confirmation_validator(validate_scene)
