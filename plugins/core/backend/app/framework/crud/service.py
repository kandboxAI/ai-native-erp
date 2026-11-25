from __future__ import annotations

from collections.abc import Callable
from typing import Any, AsyncContextManager

from app.auth.schemas import AuthenticatedUser
class CrudService:
    def __init__(
        self,
        repository,
        pool_getter: Callable[[], Any] | None = None,
        session_getter: Callable[[], AsyncContextManager[Any]] | None = None,
    ) -> None:
        if pool_getter is None and session_getter is None:
            raise ValueError("pool_getter or session_getter is required")
        self.repository = repository
        self.pool_getter = pool_getter
        self.session_getter = session_getter

    async def _call(self, method_name: str, *args):
        method = getattr(self.repository, method_name)
        if self.session_getter is not None:
            async with self.session_getter() as session:
                return await method(session, *args)
        if self.pool_getter is None:
            raise RuntimeError("pool_getter is not configured")
        return await method(self.pool_getter(), *args)

    async def list(self, params: Any, current_user: AuthenticatedUser) -> dict[str, Any]:
        return await self._call("list", params, current_user)

    async def detail(self, item_id: str, current_user: AuthenticatedUser) -> Any:
        return await self._call("detail", item_id, current_user)

    async def create(self, payload: dict[str, Any], current_user: AuthenticatedUser) -> Any:
        return await self._call("create", payload, current_user)

    async def update(self, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser) -> Any:
        return await self._call("update", item_id, payload, current_user)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        return await self._call("delete", item_id, current_user)

    async def export_rows(self, params: Any, current_user: AuthenticatedUser, *, limit: int) -> list[dict[str, Any]]:
        method = getattr(self.repository, "export_rows")
        if self.session_getter is not None:
            async with self.session_getter() as session:
                return await method(session, params, current_user, limit=limit)
        if self.pool_getter is None:
            raise RuntimeError("pool_getter is not configured")
        return await method(self.pool_getter(), params, current_user, limit=limit)
