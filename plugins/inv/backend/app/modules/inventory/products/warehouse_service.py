"""普通入库的物料适用仓库规则；保存、更新和确认复用同一校验。"""
from app.core.exceptions import AppException
from ..constants import type_form
from ..stock_order.repository import repository as stock_repository
from .warehouse_repository import repository


async def validate_inbound_warehouses(session, order, order_type, lines):
    config = getattr(order_type, "required_field_config", None) or {}
    if order_type.direction_code != "in" or type_form(order_type) != "inbound" or config.get("warehouse_scope_key"):
        return
    if getattr(order, "reversal_of_order_id", None):
        return
    pairs = [(line.item_id, line.to_warehouse_id or order.to_warehouse_id) for line in lines]
    if not pairs:
        return
    await stock_repository.lock_items(session, [item_id for item_id, _ in pairs])
    invalid = await repository.disallowed(session, pairs)
    if invalid:
        invalid_set = set(invalid)
        numbers = [str(index) for index, pair in enumerate(pairs, 1) if pair in invalid_set]
        raise AppException(f"第 {'、'.join(numbers)} 行物料未配置为目标仓库的适用物料，请先在物料档案中配置适用仓库", 409)
