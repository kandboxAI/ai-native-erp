"""事件出站（int_outbox_event）：业务在同一事务内写入事件，再由后台任务发布到消息总线。

- 写入：``enqueue_event(session, ...)``，只 add 不提交，随业务事务一起提交。
- 发布：``publish_pending(session, publisher)`` 处理当前租户；定时任务（jobs.py）按租户调用 ``publish_pending_current_tenant()``；
  ``publish_pending_all_tenants()`` 供测试、手工补发遍历全部租户。未配置发布器（message_bus_enabled=false）时不发布，事件保持待发送。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.db.tenant import use_tenant_schema

from .models import IntOutboxEvent

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead"

# 发布器：await publisher(exchange, routing_key, payload, header_meta)；失败时抛异常
Publisher = Callable[[str, str, dict[str, Any], dict[str, Any]], Awaitable[None]]


def enqueue_event(
    session: AsyncSession,
    *,
    producer_module_code: str,
    event_type_code: str,
    routing_key: str,
    payload: dict[str, Any],
    exchange: str | None = None,
    header_meta: dict[str, Any] | None = None,
    max_retries: int | None = None,
    created_by: UUID | None = None,
) -> IntOutboxEvent:
    """在当前事务中登记一个待发布事件（不提交）。"""
    settings = get_settings()
    row = IntOutboxEvent(
        producer_module_code=producer_module_code,
        event_type_code=event_type_code,
        exchange=exchange or settings.message_bus_default_exchange,
        routing_key=routing_key,
        payload=payload,
        header_meta=header_meta or {},
        status_code=STATUS_PENDING,
        retry_count=0,
        max_retries=max_retries or settings.message_bus_max_retries,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(row)
    return row


def enqueue_message(
    session: AsyncSession,
    *,
    producer: str,
    event_type: str,
    payload: dict[str, Any],
    routing_key: str,
    exchange: str | None = None,
    headers: dict[str, Any] | None = None,
    max_retries: int | None = None,
) -> IntOutboxEvent:
    """兼容旧调用（producer / event_type / headers）；新代码请用 enqueue_event。"""
    return enqueue_event(
        session,
        producer_module_code=producer,
        event_type_code=event_type,
        routing_key=routing_key,
        payload=payload,
        exchange=exchange,
        header_meta=headers,
        max_retries=max_retries,
    )


async def publish_pending(session: AsyncSession, publisher: Publisher, *, limit: int | None = None) -> dict[str, int]:
    """发布当前租户的待发送事件；失败按指数退避重试，超过次数记为死信。"""
    settings = get_settings()
    now = utc_now()
    rows = (
        await session.exec(
            select(IntOutboxEvent)
            .where(
                IntOutboxEvent.status_code.in_([STATUS_PENDING, STATUS_FAILED]),
                (IntOutboxEvent.next_attempt_at.is_(None)) | (IntOutboxEvent.next_attempt_at <= now),
            )
            .order_by(IntOutboxEvent.created_at)
            .limit(limit or settings.message_bus_publish_batch_size)
            .with_for_update(skip_locked=True)
        )
    ).all()
    result = {"scanned": len(rows), "published": 0, "failed": 0, "dead": 0}
    for row in rows:
        try:
            await publisher(row.exchange, row.routing_key, row.payload or {}, row.header_meta or {})
        except Exception as exc:  # noqa: BLE001 - 失败记录在事件上
            row.retry_count = int(row.retry_count or 0) + 1
            row.last_error = str(exc)[:2000]
            if row.retry_count >= row.max_retries:
                row.status_code = STATUS_DEAD
                result["dead"] += 1
            else:
                row.status_code = STATUS_FAILED
                row.next_attempt_at = utc_now() + timedelta(seconds=min(3600, 2 ** row.retry_count * 10))
                result["failed"] += 1
        else:
            row.status_code = STATUS_PUBLISHED
            row.published_at = utc_now()
            row.last_error = None
            result["published"] += 1
        session.add(row)
    await session.commit()
    return result


_publisher: Publisher | None = None


def set_publisher(publisher: Publisher | None) -> None:
    """注册消息总线发布器（如 RabbitMQ 客户端）；未注册时后台任务不发布。"""
    global _publisher
    _publisher = publisher


async def publish_pending_all_tenants(publisher: Publisher | None = None) -> dict[str, int]:
    """遍历全部租户发布待发送事件。显式传入 publisher 时不看 message_bus_enabled（测试、手工补发用）。"""
    total = {"scanned": 0, "published": 0, "failed": 0, "dead": 0}
    if publisher is None:
        if not get_settings().message_bus_enabled or _publisher is None:
            return total
        publisher = _publisher
    from app.auth.tenants import list_tenants

    for tenant in await list_tenants():
        with use_tenant_schema(tenant.schema_name):
            async with get_session_context() as session:
                result = await publish_pending(session, publisher)
        for key, value in result.items():
            total[key] += value
    return total


async def publish_pending_current_tenant() -> dict[str, int] | None:
    """定时任务（见 jobs.py）：发布当前租户的待发送事件；未启用消息总线或未注册发布器时不发布。"""
    if not get_settings().message_bus_enabled or _publisher is None:
        return None
    async with get_session_context() as session:
        return await publish_pending(session, _publisher)
