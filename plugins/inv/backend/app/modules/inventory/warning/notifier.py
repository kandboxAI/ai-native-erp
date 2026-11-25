"""库存预警通知：缺货 / 不足使用专用补货预警场景，积压保留原库存预警场景。

接收人由通知模块的场景路由决定：补货预警发送给事件组织内拥有 inventory_stock_alert:list
权限的用户；原积压预警保留既有路由。只 flush，随业务事务一起提交。
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.notification_center.service import notify

STOCK_ALERT_SCENE_KEY = "inventory.stock_alert"
LOW_STOCK_ALERT_SCENE_KEY = "inventory.low_stock_alert"
LOW_STOCK_RECOVERED_SCENE_KEY = "inventory.low_stock_recovered"


def _notification_event_key(
    *,
    scene_key: str,
    alert: dict[str, Any],
    business_type_code: str,
    business_id: UUID | None,
    stock_order_id: UUID | None,
    event_id: str | None,
) -> str:
    """生成不超过通知表 128 字符限制的稳定幂等键。"""

    operation_id = event_id or stock_order_id or business_id or alert["item_id"]
    raw_key = "|".join(
        (
            scene_key,
            str(alert["item_id"]),
            str(alert["warehouse_id"]),
            str(alert["current_status"]),
            business_type_code,
            str(business_id or stock_order_id or alert["item_id"]),
            str(operation_id),
        )
    )
    digest = sha256(raw_key.encode("utf-8")).hexdigest()
    return f"inv-alert:{scene_key}:{alert['current_status']}:{digest}"


async def notify_stock_alerts(
    session: AsyncSession,
    *,
    alerts: list[dict[str, Any]],
    operator_user_id: UUID | None,
    org_names: dict[UUID, str],
    warehouse_names: dict[UUID, str],
    unit_names: dict[str, str],
    stock_order_id: UUID | None = None,
    business_type_code: str = "inventory_order",
    business_id: UUID | None = None,
    event_id: str | None = None,
) -> None:
    for alert in alerts:
        org_id = UUID(alert["org_id"])
        warehouse_id = UUID(alert["warehouse_id"])
        unit = unit_names.get(alert["unit_code"], alert["unit_code"])
        is_replenishment = alert["current_status"] in {"out_of_stock", "low_stock"}
        is_recovered = (
            alert.get("previous_status") in {"out_of_stock", "low_stock"}
            and alert["current_status"] == "normal"
        )
        scene_key = (
            LOW_STOCK_ALERT_SCENE_KEY
            if is_replenishment
            else LOW_STOCK_RECOVERED_SCENE_KEY
            if is_recovered
            else STOCK_ALERT_SCENE_KEY
        )
        if is_replenishment:
            threshold_text = f"下限 {alert['min_quantity']}{unit}"
        elif is_recovered:
            threshold_text = f"安全范围 {alert['min_quantity']}～{alert['max_quantity']}{unit}"
        else:
            threshold_text = f"上限 {alert['max_quantity']}{unit}"
        await notify(
            session,
            scene_key=scene_key,
            actors={"operator": [operator_user_id] if operator_user_id else []},
            business_type_code=business_type_code,
            business_id=business_id or stock_order_id or UUID(alert["item_id"]),
            payload={
                **alert,
                "product_name": alert["item_name"],
                "organization_name": org_names.get(org_id, ""),
                "warehouse_name": warehouse_names.get(warehouse_id, ""),
                "unit": unit,
                "threshold_text": threshold_text,
                "redirect_url": (
                    f"/logistics-management/warehouse/stock-alerts?item_id={alert['item_id']}&warehouse_id={warehouse_id}"
                    if is_replenishment or is_recovered
                    else f"/logistics-management/warehouse/ledger?item_id={alert['item_id']}&warehouse_id={warehouse_id}"
                ),
            },
            org_id=org_id,
            event_key=_notification_event_key(
                scene_key=scene_key,
                alert=alert,
                business_type_code=business_type_code,
                business_id=business_id,
                stock_order_id=stock_order_id,
                event_id=event_id,
            ),
            source_module_code="inventory",
            created_by=operator_user_id,
        )
