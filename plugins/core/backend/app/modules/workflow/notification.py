"""审批流事件：待办到达、办理完成、抄送、流程结束等。

审批流不直接依赖通知中心：通知中心（或其他模块）在导入时调用 ``register_workflow_event_listener``，
在同一事务中收到事件（每个监听器在独立的保存点中执行，失败不影响审批本身）。
事件类型：task.ready、task.completed、task.rejected、cc.ready、instance.completed、instance.rejected、instance.cancelled。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.datetime_local import local_now

logger = logging.getLogger(__name__)

WorkflowEventListener = Callable[[AsyncSession, str, dict[str, Any]], Awaitable[None]]
_LISTENERS: list[WorkflowEventListener] = []


def register_workflow_event_listener(listener: WorkflowEventListener) -> None:
    if listener not in _LISTENERS:
        _LISTENERS.append(listener)


def build_workflow_event_payload(
    *,
    event_type: str,
    instance_id: UUID,
    business_type_code: str,
    business_id: UUID,
    org_id: UUID | None,
    task_id: UUID | None = None,
    task_key: str | None = None,
    task_name: str | None = None,
    actor_user_id: UUID | None = None,
    recipient_user_ids: list[UUID] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_type": event_type,
        "instance_id": str(instance_id),
        "business_type_code": business_type_code,
        "business_id": str(business_id),
        "org_id": str(org_id) if org_id else None,
        "task_id": str(task_id) if task_id else None,
        "task_key": task_key,
        "task_name": task_name,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "recipient_user_ids": [str(i) for i in (recipient_user_ids or [])],
        "occurred_at": local_now().isoformat(),
    }
    if extra:
        payload["extra"] = extra
    return payload


async def emit_workflow_event(session: AsyncSession, *, event_type: str, payload: dict[str, Any]) -> None:
    for listener in list(_LISTENERS):
        try:
            async with session.begin_nested():
                await listener(session, event_type, payload)
        except Exception:  # noqa: BLE001 通知失败不影响审批
            logger.exception("workflow event listener failed: %s", event_type)


async def send_notification(session: AsyncSession, **kwargs: Any) -> None:
    """调用通知中心 notify（只 flush，随审批事务提交）；在保存点中执行，通知失败不影响审批。"""
    from app.modules.notification_center.service import notify

    try:
        async with session.begin_nested():
            await notify(session, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("workflow notify failed: %s", kwargs.get("scene_key"))
