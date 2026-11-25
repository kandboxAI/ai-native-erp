"""仓库删除扩展校验；业务模块在自身 Repository 检查未完成的仓库引用。"""
from collections.abc import Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import InvWarehouse

WarehouseDeleteValidator = Callable[[AsyncSession, InvWarehouse], Awaitable[None]]
_validators: list[WarehouseDeleteValidator] = []


def register_warehouse_delete_validator(validator: WarehouseDeleteValidator) -> None:
    if validator not in _validators:
        _validators.append(validator)


async def validate_warehouse_delete(session: AsyncSession, warehouse: InvWarehouse) -> None:
    for validator in _validators:
        await validator(session, warehouse)
