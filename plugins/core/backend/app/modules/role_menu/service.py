from __future__ import annotations

from uuid import UUID

from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.menu.repository import repository as menu_repository
from app.modules.role.repository import is_builtin_admin

from .repository import repository
from .schemas import RoleMenuBatchSync, RoleMenuCreate, RoleMenuListQuery

BUILTIN_ADMIN_MESSAGE = "内置管理员可见全部菜单，不能减少"


class RoleMenuService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def grant_for_permission(self, session, menu_key: str, permission_key: str, *, actor_id=None) -> int:
        """配置同步按已有权限补齐指定菜单，随调用方事务提交。"""
        return await repository.grant_for_permission(session, menu_key, permission_key, actor_id=actor_id)

    async def reconcile_permission_grants(self, session, requirements: dict[str, tuple[str, ...]], *, actor_id=None) -> None:
        """插件显式调整页面权限时，同步指定页面的角色菜单绑定，不改接口权限。"""
        await repository.reconcile_permission_grants(session, requirements, actor_id=actor_id)

    async def _require_role(self, session, role_id: UUID):
        role = await repository.get_role(session, role_id)
        if role is None:
            raise AppException("角色不存在", status_code=status.HTTP_404_NOT_FOUND)
        return role

    async def list(self, params: RoleMenuListQuery, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            visible = await menu_repository.visible_menu_ids(session, set(current_user.enabled_plugin_keys))
            return await repository.list(session, params, allowed_menu_ids=visible)

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def create(self, payload: RoleMenuCreate, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            if payload.menu_id not in await menu_repository.visible_menu_ids(session, set(current_user.enabled_plugin_keys)):
                raise AppException("菜单不存在或所属能力包未启用")
            if payload.menu_id in await repository.menu_ids_for_role(session, role.id):
                raise AppException("该角色已有此菜单", status_code=status.HTTP_409_CONFLICT)
            rows = await repository.add(session, role.id, [payload.menu_id], current_user)
            await session.commit()
            return await repository.detail(session, rows[0].id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        del current_user
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None:
                return False
            role = await self._require_role(session, binding.role_id)
            if is_builtin_admin(role):
                raise AppException(BUILTIN_ADMIN_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.delete_binding(session, binding)
            await session.commit()
            return True

    async def batch_sync(self, payload: RoleMenuBatchSync, current_user: AuthenticatedUser) -> dict[str, int]:
        targets = set(payload.menu_ids)
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            valid = await menu_repository.visible_menu_ids(session, set(current_user.enabled_plugin_keys))
            missing = [str(mid) for mid in targets if mid not in valid]
            if missing:
                raise AppException(f"有 {len(missing)} 项菜单已不在当前可授权目录中，请刷新页面后重试；本次未保存")
            existing = await repository.menu_ids_for_role(session, role.id)
            to_remove = (existing & valid) - targets
            to_add = targets - existing
            if is_builtin_admin(role) and to_remove:
                raise AppException(BUILTIN_ADMIN_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.remove(session, role.id, to_remove)
            await repository.add(session, role.id, to_add, current_user)
            await session.commit()
            return {"added": len(to_add), "removed": len(to_remove), "total": len(targets)}


service = RoleMenuService(session_getter=get_session_context)
