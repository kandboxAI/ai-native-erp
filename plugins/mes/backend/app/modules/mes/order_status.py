"""工单业务状态投影；保留既有执行状态码，不改写历史或迁移链。"""

ORDER_STATUS_LABELS = {
    "unconfigured": "未配置", "ready": "待下单", "ordered": "已下单",
    "paused": "已暂停", "completed": "已完结", "cancelled": "已取消",
}


def work_order_status(status_code, operation_count):
    if status_code == "draft":
        return "ready" if operation_count else "unconfigured"
    if status_code in {"released", "in_progress"}:
        return "ordered"
    return status_code


def project_order_status(orders, configured_ids):
    """仅汇总调用方已授权的货品。部分下单由下单数量同时说明。"""
    states = {work_order_status(row.status_code, row.id in configured_ids) for row in orders}
    for state in ("ordered", "paused", "unconfigured", "ready", "completed", "cancelled"):
        if state in states:
            return state
    return "unconfigured"
