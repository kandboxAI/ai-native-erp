"""制造仓库用途及可见范围，由 MES 主动登记到库存扩展点。"""
from app.core.exceptions import AppException
from app.modules.inventory.warehouse_scope import WarehouseScope, register_warehouse_scope

WAREHOUSE_TYPES = {"mes_raw": "制造原料仓", "mes_wip": "制造在制品仓", "mes_finished": "制造成品仓", "mes_tool": "制造刀具仓"}
register_warehouse_scope(WarehouseScope("mes", "mes", frozenset(WAREHOUSE_TYPES), "mes:warehouse:list", "mes:warehouse:manage", ("HQ-01",)))


def allows(warehouse, purpose):
    if warehouse["warehouse_no"] == "HQ-01": return True  # 保留原单仓历史，不迁移库存。
    types = {"mes_finished"} if purpose in {"receipt", "shipment"} else {"mes_raw", "mes_wip"}
    return warehouse["warehouse_type_code"] in types


async def validate_warehouse(session, row):
    from app.modules.inventory import public as stock
    warehouse = await stock.get_stock_warehouse(session, row.warehouse_id)
    if warehouse is None or warehouse["org_id"] != row.org_id or not allows(warehouse, row.posting_type_code):
        raise AppException("仓库已停用、组织不符或用途不符；领退料请选择原料/在制品仓，成品入库和出货请选择成品仓", 409)
