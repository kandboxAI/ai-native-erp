from __future__ import annotations

from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.user_profile.service import scope_condition

from .repository import repository
from .schemas import UserOrgCreate, UserOrgListQuery


class UserAuthorizationService:
    """用户组织授权：维护用户除主组织外可访问的组织。"""

    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def list(self, params: UserOrgListQuery, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            return await repository.list(session, params, scope_condition(current_user, "user_authorization:list"))

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def create(self, payload: UserOrgCreate, current_user: AuthenticatedUser):
        permission_key = "user_authorization:create"
        async with self.session_getter() as session:
            if await repository.get_user(session, payload.user_id, scope_condition(current_user, permission_key)) is None:
                raise AppException("用户不存在", status_code=status.HTTP_404_NOT_FOUND)
            if await repository.get_org(session, payload.org_id) is None:
                raise AppException("组织不存在或已停用")
            ensure_org_access(current_user, payload.org_id, permission_key)
            if await repository.exists(session, payload.user_id, payload.org_id):
                raise AppException("该用户已可访问此组织", status_code=status.HTTP_409_CONFLICT)
            row = await repository.add(session, payload.user_id, payload.org_id, current_user)
            await session.commit()
            return await repository.detail(session, row.id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        permission_key = "user_authorization:delete"
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None or await repository.get_user(session, binding.user_id, scope_condition(current_user, permission_key)) is None:
                return False
            if binding.is_primary:
                raise AppException("主组织不能删除，请在用户管理中修改所属组织")
            ensure_org_access(current_user, binding.org_id, permission_key)
            await repository.delete_binding(session, binding)
            await session.commit()
            return True


service = UserAuthorizationService(session_getter=get_session_context)
