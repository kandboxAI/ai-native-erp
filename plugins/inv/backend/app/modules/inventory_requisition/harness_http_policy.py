"""领用交接给模型的最小投影：不发布照片链接、姓名快照和自由文本。"""

HEADER_FIELDS = ("id", "request_no", "submission_batch_no", "warehouse_id", "status_code", "created_at", "approved_at", "issued_at", "received_at", "stock_order_id", "stock_order_no", "version_no")
LINE_FIELDS = ("id", "item_id", "item_no_snapshot", "quantity", "issued_quantity", "unit_code_snapshot")
RECEIPT_FIELDS = ("line_id", "received_quantity", "exception_quantity", "exception_type_code")
EVENT_FIELDS = ("id", "event_type_code", "from_status_code", "to_status_code", "created_at")


def _pick(row, fields):
    return {key: row[key] for key in fields if key in row}


def project_requisition(_body, data):
    if not isinstance(data, dict):
        return None
    if "items" in data:
        items = data["items"]
        if not isinstance(items, list) or len(items) > 100:
            return None
        projected = [project_requisition(None, item) for item in items]
        if any(item is None for item in projected):
            return None
        return {**_pick(data, ("total", "page", "page_size")), "items": projected}
    if "id" not in data or "status_code" not in data:
        return None
    result = _pick(data, HEADER_FIELDS)
    lines, events = data.get("lines", []), data.get("events", [])
    if not isinstance(lines, list) or not isinstance(events, list):
        return None
    if any(not isinstance(line, dict) for line in lines) or any(not isinstance(event, dict) for event in events):
        return None
    result["lines"] = [_pick(line, LINE_FIELDS) for line in lines]
    result["events"] = []
    for event in events:
        checks = event.get("receipt_lines", [])
        if not isinstance(checks, list) or any(not isinstance(check, dict) for check in checks):
            return None
        result["events"].append({**_pick(event, EVENT_FIELDS), "receipt_lines": [_pick(check, RECEIPT_FIELDS) for check in checks]})
    return result


READ_ROUTES = {
    ("GET", "/api/inventory_requisition/detail/{request_id}"): (project_requisition, None),
    ("GET", "/api/inventory_requisition/my"): (project_requisition, "inventory_requisition:create"),
    ("GET", "/api/inventory_requisition/list"): (project_requisition, "inventory_requisition:list"),
}
