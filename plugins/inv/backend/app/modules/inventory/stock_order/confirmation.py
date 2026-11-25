"""库存单据确认前的业务扩展点。

库存模块只负责通用记账规则；上层业务可注册确认校验器，但库存模块不反向依赖业务模块。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser

from ..models import InvStockOrder, InvStockOrderLine, InvStockOrderType


ConfirmationValidator = Callable[
    [AsyncSession, InvStockOrder, InvStockOrderType, list[InvStockOrderLine], AuthenticatedUser],
    Awaitable[None],
]

_validators: list[ConfirmationValidator] = []


def register_confirmation_validator(validator: ConfirmationValidator) -> None:
    """幂等登记一个确认前校验器。"""
    if validator not in _validators:
        _validators.append(validator)


async def run_confirmation_validators(
    session: AsyncSession,
    order: InvStockOrder,
    order_type: InvStockOrderType,
    lines: list[InvStockOrderLine],
    current_user: AuthenticatedUser,
) -> None:
    for validator in _validators:
        await validator(session, order, order_type, lines, current_user)


__all__ = ["register_confirmation_validator", "run_confirmation_validators"]
