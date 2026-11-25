from typing import Any

from app.auth.schemas import AuthenticatedUser
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import repository


class MenuService(CrudService):
    async def authorized_paths_in_session(self, session, current_user, menu_keys):
        """供业务跳转复用当前账号已授权目录，仅返回指定站内页面的路径。"""
        rows = await self.repository.authorized_rows_for_user(session, current_user)
        return {row.menu_key: row.path for row in rows
                if row.menu_key in menu_keys and row.path and row.path.startswith("/")
                and not row.path.startswith("//") and not row.is_external and row.menu_type_code == "menu"}

    async def tree(self, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        return await self._call("tree", current_user)

    async def tree_for_user(self, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        return await self._call("tree_for_user", current_user)


service = MenuService(repository=repository, session_getter=get_session_context)
