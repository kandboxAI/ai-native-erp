from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.framework.deployment import blocked_plugin_module_codes
from app.modules.role.repository import is_builtin_admin

from .repository import repository
from .schemas import RolePermissionBatchSync, RolePermissionCreate, RolePermissionListQuery

BUILTIN_ADMIN_REDUCE_MESSAGE = "内置管理员拥有全部权限，不能减少"


class RolePermissionService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def ensure_default_grants(self, session, defaults, *, actor_id=None):
        """模块开通的公开授权入口，随调用方事务提交；运行时鉴权仍按权限与数据范围。"""
        return await repository.ensure_default_grants(session,defaults,actor_id)

    @staticmethod
    def _scope(role, data_scope_code: str | None) -> str | None:
        """与角色默认数据范围相同的不单独保存（为空表示取角色的）。"""
        return None if data_scope_code in (None, role.data_scope_code) else data_scope_code

    async def _require_role(self, session, role_id: UUID):
        role = await repository.get_role(session, role_id)
        if role is None:
            raise AppException("角色不存在", status_code=status.HTTP_404_NOT_FOUND)
        return role

    async def list(self, params: RolePermissionListQuery) -> dict:
        async with self.session_getter() as session:
            return await repository.list(session, params)

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def create(self, payload: RolePermissionCreate, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            blocked = blocked_plugin_module_codes(current_user.enabled_plugin_keys)
            if payload.permission_id not in await repository.allowed_permission_ids(session, [payload.permission_id], blocked):
                raise AppException("权限不存在或所属能力包未启用")
            if await repository.find_binding(session, role.id, payload.permission_id) is not None:
                raise AppException("该角色已拥有此权限", status_code=status.HTTP_409_CONFLICT)
            binding = await repository.add(session, role.id, payload.permission_id, self._scope(role, payload.data_scope_code), current_user)
            await session.commit()
            return await repository.detail(session, binding.id)

    async def update(self, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None:
                return None
            role = await self._require_role(session, binding.role_id)
            if "data_scope_code" in payload:
                if is_builtin_admin(role) and payload["data_scope_code"] not in (None, role.data_scope_code):
                    raise AppException(BUILTIN_ADMIN_REDUCE_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
                await repository.set_scope(session, binding, self._scope(role, payload["data_scope_code"]), current_user)
                await session.commit()
            return await repository.detail(session, binding.id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        del current_user
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None:
                return False
            role = await self._require_role(session, binding.role_id)
            if is_builtin_admin(role):
                raise AppException(BUILTIN_ADMIN_REDUCE_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.delete_binding(session, binding)
            await session.commit()
            return True

    async def batch_sync(self, payload: RolePermissionBatchSync, current_user: AuthenticatedUser) -> dict[str, int]:
        targets: dict[UUID, str | None] = {}
        if payload.permission_scopes:
            for item in payload.permission_scopes:
                targets[item.permission_id] = item.data_scope_code
        else:
            for permission_id in payload.permission_ids:
                targets[permission_id] = None
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            blocked = blocked_plugin_module_codes(current_user.enabled_plugin_keys)
            valid = await repository.allowed_permission_ids(session, list(targets), blocked)
            missing = [str(pid) for pid in targets if pid not in valid]
            if missing:
                raise AppException(f"权限不存在：{', '.join(missing)}")
            existing = {binding.permission_id: binding for binding in await repository.bindings_for_role(session, role.id)}
            visible_existing = await repository.allowed_permission_ids(session, list(existing), blocked)
            to_remove = visible_existing - set(targets)
            if is_builtin_admin(role):
                if to_remove:
                    raise AppException(BUILTIN_ADMIN_REDUCE_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
                if any(scope not in (None, role.data_scope_code) for scope in targets.values()):
                    raise AppException(BUILTIN_ADMIN_REDUCE_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.remove(session, role.id, to_remove)
            added = updated = 0
            for permission_id, scope in targets.items():
                scope = self._scope(role, scope)
                binding = existing.get(permission_id)
                if binding is None:
                    await repository.add(session, role.id, permission_id, scope, current_user)
                    added += 1
                elif binding.data_scope_code != scope:
                    await repository.set_scope(session, binding, scope, current_user)
                    updated += 1
            await session.commit()
            return {"added": added, "removed": len(to_remove), "updated": updated, "total": len(targets)}


service = RolePermissionService(session_getter=get_session_context)
