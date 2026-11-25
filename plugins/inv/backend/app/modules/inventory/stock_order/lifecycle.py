"""库存单据状态变化后的来源单据扩展点。

库存模块只负责通用记账与调用扩展点，不反向依赖采购、食堂等上游业务模块。
上游模块按 ``source_doc_type_code`` 注册处理器，并与库存状态流转共用事务。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser

from ..models import InvStockOrder, InvStockOrderLine, InvStockOrderType


SourceDocumentHandler = Callable[
    [AsyncSession, InvStockOrder, InvStockOrderType, list[InvStockOrderLine], AuthenticatedUser],
    Awaitable[None],
]

_handlers: dict[str, list[SourceDocumentHandler]] = {}
_mutation_guards: dict[str, list] = {}


def register_source_mutation_guard(source_doc_type_code: str, guard) -> None:
    """可选来源保护；在加锁、鉴权后且修改字段前运行，不影响未登记的来源。"""
    guards = _mutation_guards.setdefault(source_doc_type_code, [])
    if guard not in guards:
        guards.append(guard)


async def run_source_mutation_guards(session, order, user, action):
    for guard in _mutation_guards.get(order.source_doc_type_code, ()):
        await guard(session, order, user, action)


def register_source_document_handler(
    source_doc_type_code: str,
    handler: SourceDocumentHandler,
) -> None:
    """幂等登记来源单据处理器。"""

    handlers = _handlers.setdefault(source_doc_type_code, [])
    if handler not in handlers:
        handlers.append(handler)


async def run_source_document_handlers(
    session: AsyncSession,
    order: InvStockOrder,
    order_type: InvStockOrderType,
    lines: list[InvStockOrderLine],
    current_user: AuthenticatedUser,
) -> None:
    """在库存状态流转事务内通知对应来源单据模块。"""

    if not order.source_doc_type_code or order.source_doc_id is None:
        return
    for handler in _handlers.get(order.source_doc_type_code, []):
        await handler(session, order, order_type, lines, current_user)


__all__ = [
    "register_source_mutation_guard",
    "run_source_mutation_guards",
    "register_source_document_handler",
    "run_source_document_handlers",
]
