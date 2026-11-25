"""资产交接扩展点；业务模块在此登记同事务校验与完成回调。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser

from .handover_models import AssetHandover

CompletedHandler = Callable[[AsyncSession, AssetHandover, AuthenticatedUser], Awaitable[None]]
ReceiverValidator = Callable[[AsyncSession, UUID, UUID], Awaitable[bool]]
_COMPLETED_HANDLERS: dict[str, CompletedHandler] = {}
_RECEIVER_VALIDATORS: list[ReceiverValidator] = []
SourceContextHandler = Callable[[AsyncSession, AssetHandover, AuthenticatedUser], Awaitable[dict | None]]
SourceLockHandler = Callable[[AsyncSession, AssetHandover], Awaitable[None]]
_SOURCE_CONTEXT_HANDLERS: dict[str, SourceContextHandler] = {}
_SOURCE_LOCK_HANDLERS: dict[str, SourceLockHandler] = {}


def register_handover_source(source_type_code, *, context, lock) -> None:
    """来源模块提供授权后的来源摘要和锁；资产模块不反向依赖来源业务。"""
    _SOURCE_CONTEXT_HANDLERS[source_type_code] = context
    _SOURCE_LOCK_HANDLERS[source_type_code] = lock


async def handover_source_context(session, handover, user) -> dict | None:
    if handover.source_id is None:
        return None
    handler = _SOURCE_CONTEXT_HANDLERS.get(handover.source_type_code)
    return await handler(session, handover, user) if handler and user else None


async def lock_handover_source(session, handover) -> None:
    if handover.source_id is None:
        return
    handler = _SOURCE_LOCK_HANDLERS.get(handover.source_type_code)
    if handler:
        await handler(session, handover)


def register_handover_completed(source_type_code: str, handler: CompletedHandler) -> None:
    _COMPLETED_HANDLERS[source_type_code] = handler


def register_handover_receiver_validator(validator: ReceiverValidator) -> None:
    """登记接任人员资格校验器；至少一个业务提供器确认有效才允许移交。"""
    if validator not in _RECEIVER_VALIDATORS:
        _RECEIVER_VALIDATORS.append(validator)


async def validate_handover_receiver(
    session: AsyncSession, user_id: UUID, org_id: UUID
) -> bool:
    for validator in _RECEIVER_VALIDATORS:
        if await validator(session, user_id, org_id):
            return True
    return False


async def dispatch_handover_completed(
    session: AsyncSession, handover: AssetHandover, user: AuthenticatedUser
) -> None:
    handler = _COMPLETED_HANDLERS.get(handover.source_type_code)
    if handler is not None:
        await handler(session, handover, user)


__all__ = [
    "register_handover_source",
    "handover_source_context",
    "lock_handover_source",
    "dispatch_handover_completed",
    "register_handover_completed",
    "register_handover_receiver_validator",
    "validate_handover_receiver",
]
