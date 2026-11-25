"""库存单保存前的业务扩展校验。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser

from ..models import InvStockOrder, InvStockOrderLine, InvStockOrderType

WriteValidator = Callable[
    [AsyncSession, InvStockOrder, InvStockOrderType, list[InvStockOrderLine], AuthenticatedUser],
    Awaitable[None],
]

_validators: list[WriteValidator] = []


def register_write_validator(validator: WriteValidator) -> None:
    if validator not in _validators:
        _validators.append(validator)


async def run_write_validators(
    session: AsyncSession,
    order: InvStockOrder,
    order_type: InvStockOrderType,
    lines: list[InvStockOrderLine],
    current_user: AuthenticatedUser,
) -> None:
    for validator in _validators:
        await validator(session, order, order_type, lines, current_user)


__all__ = ["register_write_validator", "run_write_validators"]
