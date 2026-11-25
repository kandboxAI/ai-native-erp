"""旧库位结构的受审迁移辅助；仅由显式迁移调用，不在启动时运行。"""
from sqlalchemy import MetaData, Table, func, or_, select


LOCATION_COLUMNS = {
    "inv_stock_balance": (("location_id", "warehouse_id"),),
    "inv_stock_order": (("from_location_id", "from_warehouse_id"), ("to_location_id", "to_warehouse_id")),
    "inv_stock_order_line": (("from_location_id", "from_warehouse_id"), ("to_location_id", "to_warehouse_id")),
    "inv_stock_transaction": (("from_location_id", "from_warehouse_id"), ("to_location_id", "to_warehouse_id")),
}


def _table(connection, name):
    # 使用迁移连接当前 schema；不固定租户，不反射其他模块的外键目标。
    return Table(name, MetaData(), autoload_with=connection, resolve_fks=False)


def backfill_location_warehouses(connection, table_name: str) -> None:
    """先回填并检查，再允许迁移删除旧列；不随意选择默认仓库。"""
    if table_name not in LOCATION_COLUMNS:
        raise ValueError("不支持的库存库位转换表")
    table = _table(connection, table_name)
    location = _table(connection, "inv_location")
    warehouse = _table(connection, "inv_warehouse")
    for old, new in LOCATION_COLUMNS[table_name]:
        old_column, new_column = table.c[old], table.c[new]
        mapping = select(location.c.warehouse_id).where(location.c.id == old_column).correlate(table).scalar_subquery()
        valid = select(location.c.id).join(warehouse, warehouse.c.id == location.c.warehouse_id).where(
            location.c.id == old_column, location.c.org_id == warehouse.c.org_id,
            table.c.org_id == warehouse.c.org_id,
        ).correlate(table).exists()
        if connection.scalar(select(func.count()).select_from(table).where(old_column.is_not(None), ~valid)):
            raise ValueError(f"{table_name}.{old} 存在失效或跨组织库位；请审核映射，不会自动指定仓库")
        if connection.scalar(select(func.count()).select_from(table).where(
            old_column.is_not(None), new_column.is_not(None), new_column != mapping,
        )):
            raise ValueError(f"{table_name}.{new} 与旧库位映射冲突，已停止转换")
        connection.execute(table.update().where(old_column.is_not(None), new_column.is_(None)).values({new: mapping}))
    if table_name == "inv_stock_balance":
        if connection.scalar(select(func.count()).select_from(table).where(table.c.warehouse_id.is_(None))):
            raise ValueError("库存余额存在无法确定仓库的记录")
        keys = [table.c[key] for key in ("item_id", "warehouse_id", "lot_id", "stock_status_code", "owner_party_id")]
        duplicate = select(func.count()).select_from(table).group_by(*keys).having(func.count() > 1).limit(1)
        if connection.scalar(duplicate):
            raise ValueError("多个库位映射到同一库存余额键；需审核聚合方案，未自动删除或合并余额")


def backfill_requisition_warehouses(connection) -> None:
    """保留旧申请编号为独立提交批次；已发放申请从原出库单推导仓库。"""
    request = _table(connection, "inv_material_requisition")
    if not connection.scalar(select(func.count()).select_from(request)):
        return
    order = _table(connection, "inv_stock_order")
    location = _table(connection, "inv_location")
    warehouse = _table(connection, "inv_warehouse")
    mapping = select(location.c.warehouse_id).select_from(order).join(
        location, location.c.id == order.c.from_location_id,
    ).join(warehouse, warehouse.c.id == location.c.warehouse_id).where(
        order.c.id == request.c.stock_order_id, warehouse.c.org_id == request.c.org_id,
        location.c.org_id == warehouse.c.org_id,
    ).correlate(request).scalar_subquery()
    connection.execute(request.update().where(request.c.submission_batch_no.is_(None)).values(
        submission_batch_no=request.c.request_no,
    ))
    connection.execute(request.update().where(request.c.warehouse_id.is_(None)).values(warehouse_id=mapping))
    if connection.scalar(select(func.count()).select_from(request).where(or_(
        request.c.warehouse_id.is_(None), request.c.submission_batch_no.is_(None),
    ))):
        raise ValueError("旧领用申请缺少可核对的出库仓库；请先确认申请仓库，未自动指定或拆分")
