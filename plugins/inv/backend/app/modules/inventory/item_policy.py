"""库存物料业务范围扩展点。

库存模块不反向依赖食堂等上层业务模块。上层模块可注册受限物料提供器，供物料候选、
库存导入和领用申请使用同一套业务范围规则。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

GENERAL_WAREHOUSE_SCOPE = "general_warehouse"
CANTEEN_WAREHOUSE_SCOPE = "canteen_warehouse"

RestrictedItemProvider = Callable[
    [AsyncSession, str, set[UUID] | None],
    Awaitable[set[UUID]],
]

_providers: list[RestrictedItemProvider] = []
_candidate_providers: list[RestrictedItemProvider] = []


def register_restricted_item_provider(provider: RestrictedItemProvider) -> None:
    if provider not in _providers:
        _providers.append(provider)


def register_candidate_item_provider(provider: RestrictedItemProvider) -> None:
    if provider not in _candidate_providers:
        _candidate_providers.append(provider)


async def restricted_item_ids(
    session: AsyncSession,
    scope_code: str | None,
    item_ids: set[UUID] | None = None,
) -> set[UUID]:
    if not scope_code:
        return set()
    result: set[UUID] = set()
    for provider in _providers:
        result.update(await provider(session, scope_code, item_ids))
    return result


async def candidate_item_ids(
    session: AsyncSession,
    scope_code: str | None,
    item_ids: set[UUID] | None = None,
) -> set[UUID]:
    if not scope_code:
        return set()
    result: set[UUID] = set()
    for provider in _candidate_providers:
        result.update(await provider(session, scope_code, item_ids))
    return result


__all__ = [
    "CANTEEN_WAREHOUSE_SCOPE",
    "GENERAL_WAREHOUSE_SCOPE",
    "candidate_item_ids",
    "register_candidate_item_provider",
    "register_restricted_item_provider",
    "restricted_item_ids",
]
