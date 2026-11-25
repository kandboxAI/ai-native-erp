from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.rbac_repository_utils import normalize_uuid
from app.modules.role.models import SysRole
from app.modules.user_profile.models import SysUser

from .models import SysUserRole
from .schemas import UserRoleItem, UserRoleListQuery


def _base_statement():
    return (
        select(
            SysUserRole.id,
            SysUserRole.user_id,
            SysUserRole.role_id,
            SysUser.display_name,
            SysRole.role_no,
            SysRole.role_name,
            SysUserRole.created_at,
        )
        .join(SysUser, SysUser.id == SysUserRole.user_id)
        .join(SysRole, SysRole.id == SysUserRole.role_id)
        .where(SysUser.deleted_at.is_(None), SysRole.deleted_at.is_(None))
    )


class UserRoleRepository:
    async def list(self, session: AsyncSession, params: UserRoleListQuery, scope_condition) -> dict[str, Any]:
        statement = _base_statement()
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        if params.user_id:
            statement = statement.where(SysUserRole.user_id == params.user_id)
        if params.role_id:
            statement = statement.where(SysUserRole.role_id == params.role_id)
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            statement = statement.where(or_(SysUser.display_name.ilike(keyword), SysRole.role_name.ilike(keyword), SysRole.role_no.ilike(keyword)))
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                statement.order_by(SysUser.display_name, SysRole.role_no).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        return {"items": [UserRoleItem(**r._mapping).model_dump(mode="json") for r in rows], "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, session: AsyncSession, item_id: str | UUID, scope_condition=None) -> UserRoleItem | None:
        statement = _base_statement().where(SysUserRole.id == normalize_uuid(item_id))
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        row = (await session.execute(statement)).one_or_none()
        return UserRoleItem(**row._mapping) if row else None

    async def get(self, session: AsyncSession, item_id: str | UUID) -> SysUserRole | None:
        return await session.get(SysUserRole, normalize_uuid(item_id))

    async def get_role(self, session: AsyncSession, role_id: UUID) -> SysRole | None:
        role = await session.get(SysRole, role_id)
        return role if role is not None and role.deleted_at is None else None

    async def get_user(self, session: AsyncSession, user_id: UUID, scope_condition=None) -> SysUser | None:
        statement = select(SysUser).where(SysUser.id == user_id, SysUser.deleted_at.is_(None))
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        return (await session.execute(statement)).scalar_one_or_none()

    async def exists(self, session: AsyncSession, user_id: UUID, role_id: UUID) -> bool:
        statement = select(SysUserRole.id).where(SysUserRole.user_id == user_id, SysUserRole.role_id == role_id)
        return (await session.execute(statement)).scalar_one_or_none() is not None

    async def add(self, session: AsyncSession, user_id: UUID, role_id: UUID, current_user: AuthenticatedUser) -> SysUserRole:
        row = SysUserRole(user_id=user_id, role_id=role_id, created_by=current_user.user_id, updated_by=current_user.user_id)
        session.add(row)
        await session.flush()
        return row

    async def delete_binding(self, session: AsyncSession, binding: SysUserRole) -> None:
        await session.delete(binding)


repository = UserRoleRepository()
