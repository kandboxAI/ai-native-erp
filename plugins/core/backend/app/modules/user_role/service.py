from __future__ import annotations

from fastapi import status

from app.auth.data_scope import DATA_SCOPE_ALL
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import has_global_access
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.user_profile.service import scope_condition

from .repository import repository
from .schemas import UserRoleCreate, UserRoleListQuery


class UserRoleService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    @staticmethod
    def _check_role_scope(role, current_user: AuthenticatedUser, permission_key: str) -> None:
        if role.data_scope_code == DATA_SCOPE_ALL and not has_global_access(current_user, permission_key):
            raise AppException("只有数据范围为全部的管理员可以分配或解除数据范围为全部的角色", status_code=status.HTTP_403_FORBIDDEN)

    async def list(self, params: UserRoleListQuery, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            return await repository.list(session, params, scope_condition(current_user, "user_role:list"))

    async def detail(self, item_id: str, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id, scope_condition(current_user, "user_role:detail"))

    async def create(self, payload: UserRoleCreate, current_user: AuthenticatedUser):
        permission_key = "user_role:create"
        async with self.session_getter() as session:
            if await repository.get_user(session, payload.user_id, scope_condition(current_user, permission_key)) is None:
                raise AppException("用户不存在", status_code=status.HTTP_404_NOT_FOUND)
            role = await repository.get_role(session, payload.role_id)
            if role is None:
                raise AppException("角色不存在", status_code=status.HTTP_404_NOT_FOUND)
            self._check_role_scope(role, current_user, permission_key)
            if await repository.exists(session, payload.user_id, payload.role_id):
                raise AppException("该用户已拥有此角色", status_code=status.HTTP_409_CONFLICT)
            row = await repository.add(session, payload.user_id, payload.role_id, current_user)
            await session.commit()
            return await repository.detail(session, row.id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        permission_key = "user_role:delete"
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None or await repository.get_user(session, binding.user_id, scope_condition(current_user, permission_key)) is None:
                return False
            role = await repository.get_role(session, binding.role_id)
            if role is not None:
                self._check_role_scope(role, current_user, permission_key)
            if binding.user_id == current_user.user_id and role is not None and role.data_scope_code == DATA_SCOPE_ALL:
                raise AppException("不能解除自己的管理员角色")
            await repository.delete_binding(session, binding)
            await session.commit()
            return True


service = UserRoleService(session_getter=get_session_context)
