"""库存预警的评估规则（纯函数，无数据库访问）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from .schemas import StockAlertEvaluation

ALERT_LABELS = {
    "unconfigured": "未配置",
    "out_of_stock": "缺货",
    "low_stock": "库存不足",
    "normal": "正常",
    "overstock": "库存积压",
}
NOTIFY_STATUSES = {"out_of_stock", "low_stock", "overstock"}
REPLENISH_STATUSES = {"out_of_stock", "low_stock"}


def evaluate_stock_alert(
    *,
    quantity: Decimal | int | float,
    min_quantity: Decimal | int | float | None,
    max_quantity: Decimal | int | float | None,
) -> StockAlertEvaluation:
    current = Decimal(str(quantity or 0))
    lower = Decimal(str(min_quantity)) if min_quantity is not None else None
    upper = Decimal(str(max_quantity)) if max_quantity is not None else None
    if lower is None and upper is None:
        status = "unconfigured"
    elif lower is not None and current <= lower:
        status = "out_of_stock" if current <= 0 else "low_stock"
    elif upper is not None and current > upper:
        status = "overstock"
    else:
        status = "normal"
    suggested = Decimal("0")
    if status in {"out_of_stock", "low_stock"}:
        target = upper if upper is not None else lower
        if target is not None:
            suggested = max(target - current, Decimal("0"))
    return StockAlertEvaluation(status=status, label=ALERT_LABELS[status], suggested_replenishment_quantity=suggested)


def alert_transitions(
    items: dict[UUID, Any],
    thresholds: dict[tuple[UUID, UUID, UUID], tuple[Decimal, Decimal]],
    before: dict[tuple[UUID, UUID, UUID], Decimal],
    after: dict[tuple[UUID, UUID, UUID], Decimal],
) -> list[dict[str, Any]]:
    """记账前后预警状态发生变化、且进入缺货 / 不足 / 积压的物料 × 仓库。"""
    result: list[dict[str, Any]] = []
    for key, quantity in after.items():
        item = items.get(key[0])
        if item is None:
            continue
        threshold = thresholds.get(key)
        if threshold is None:
            continue
        min_quantity, max_quantity = threshold
        old = evaluate_stock_alert(quantity=before.get(key, Decimal("0")), min_quantity=min_quantity, max_quantity=max_quantity)
        new = evaluate_stock_alert(quantity=quantity, min_quantity=min_quantity, max_quantity=max_quantity)
        is_recovered = old.status in REPLENISH_STATUSES and new.status == "normal"
        if old.status == new.status or (new.status not in NOTIFY_STATUSES and not is_recovered):
            continue
        result.append(
            {
                "item_id": str(item.id),
                "item_no": item.item_no,
                "item_name": item.item_name,
                "unit_code": item.unit_code,
                "org_id": str(key[1]),
                "warehouse_id": str(key[2]),
                "quantity": str(quantity),
                "min_quantity": str(min_quantity),
                "max_quantity": str(max_quantity),
                "previous_status": old.status,
                "current_status": new.status,
                "status_label": new.label,
                "suggested_replenishment_quantity": str(new.suggested_replenishment_quantity),
            }
        )
    return result


def threshold_alert_transitions(
    item: Any,
    *,
    org_id: UUID,
    warehouse_id: UUID,
    quantity: Decimal,
    min_quantity: Decimal,
    max_quantity: Decimal,
    previous_min_quantity: Decimal | None,
    previous_max_quantity: Decimal | None,
) -> list[dict[str, Any]]:
    """单个物料仓库阈值修改后，返回新进入补货预警的状态变化。"""
    old = evaluate_stock_alert(
        quantity=quantity,
        min_quantity=previous_min_quantity,
        max_quantity=previous_max_quantity,
    )
    new = evaluate_stock_alert(
        quantity=quantity,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
    )
    if old.status == new.status or new.status not in REPLENISH_STATUSES:
        return []
    return [{
        "item_id": str(item.id),
        "item_no": item.item_no,
        "item_name": item.item_name,
        "unit_code": item.unit_code,
        "org_id": str(org_id),
        "warehouse_id": str(warehouse_id),
        "quantity": str(quantity),
        "min_quantity": str(min_quantity),
        "max_quantity": str(max_quantity),
        "previous_status": old.status,
        "current_status": new.status,
        "status_label": new.label,
        "suggested_replenishment_quantity": str(new.suggested_replenishment_quantity),
    }]
