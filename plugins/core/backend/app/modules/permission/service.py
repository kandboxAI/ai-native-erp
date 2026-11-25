from typing import Any

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.framework.deployment import blocked_plugin_module_codes

from .repository import repository
from .schemas import PermissionListQuery


class PermissionService:
    """权限由各模块 catalog 定义、开通租户时生成；这里只提供查询与改名、启停。"""

    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def list(self, params: PermissionListQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        blocked = blocked_plugin_module_codes(current_user.enabled_plugin_keys)
        async with self.session_getter() as session:
            return await repository.list(session, params, blocked)

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def update(self, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        if "permission_name" in payload and not str(payload["permission_name"] or "").strip():
            raise AppException("权限名称不能为空")
        async with self.session_getter() as session:
            entity = await repository.get(session, item_id)
            if entity is None:
                return None
            if "permission_name" in payload and payload["permission_name"] is not None:
                payload["permission_name"] = str(payload["permission_name"]).strip()
            await repository.update(session, entity, payload, current_user)
            return await repository.detail(session, item_id)


service = PermissionService(session_getter=get_session_context)
