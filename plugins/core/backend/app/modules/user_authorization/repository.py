"""用户可访问的组织（sys_user_org）。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.organization.models import SysOrg
from app.modules.rbac_repository_utils import normalize_uuid
from app.modules.user_profile.models import SysUser, SysUserOrg

from .schemas import UserOrgItem, UserOrgListQuery


def _base_statement():
    return (
        select(
            SysUserOrg.id,
            SysUserOrg.user_id,
            SysUserOrg.org_id,
            SysUser.display_name,
            SysOrg.org_name,
            SysUserOrg.access_type_code,
            SysUserOrg.is_primary,
            SysUserOrg.created_at,
        )
        .join(SysUser, SysUser.id == SysUserOrg.user_id)
        .join(SysOrg, SysOrg.id == SysUserOrg.org_id)
        .where(SysUser.deleted_at.is_(None))
    )


class UserOrgRepository:
    async def list(self, session: AsyncSession, params: UserOrgListQuery, scope_condition) -> dict[str, Any]:
        statement = _base_statement()
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        if params.user_id:
            statement = statement.where(SysUserOrg.user_id == params.user_id)
        if params.org_id:
            statement = statement.where(SysUserOrg.org_id == params.org_id)
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            statement = statement.where(or_(SysUser.display_name.ilike(keyword), SysOrg.org_name.ilike(keyword)))
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                statement.order_by(SysUser.display_name, SysUserOrg.is_primary.desc()).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        return {"items": [UserOrgItem(**r._mapping).model_dump(mode="json") for r in rows], "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, session: AsyncSession, item_id: str | UUID) -> UserOrgItem | None:
        row = (await session.execute(_base_statement().where(SysUserOrg.id == normalize_uuid(item_id)))).one_or_none()
        return UserOrgItem(**row._mapping) if row else None

    async def get(self, session: AsyncSession, item_id: str | UUID) -> SysUserOrg | None:
        return await session.get(SysUserOrg, normalize_uuid(item_id))

    async def get_user(self, session: AsyncSession, user_id: UUID, scope_condition=None) -> SysUser | None:
        statement = select(SysUser).where(SysUser.id == user_id, SysUser.deleted_at.is_(None))
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        return (await session.execute(statement)).scalar_one_or_none()

    async def get_org(self, session: AsyncSession, org_id: UUID) -> SysOrg | None:
        org = await session.get(SysOrg, org_id)
        return org if org is not None and org.deleted_at is None and org.is_active else None

    async def exists(self, session: AsyncSession, user_id: UUID, org_id: UUID) -> bool:
        statement = select(SysUserOrg.id).where(SysUserOrg.user_id == user_id, SysUserOrg.org_id == org_id)
        return (await session.execute(statement)).scalar_one_or_none() is not None

    async def add(self, session: AsyncSession, user_id: UUID, org_id: UUID, current_user: AuthenticatedUser) -> SysUserOrg:
        row = SysUserOrg(
            user_id=user_id,
            org_id=org_id,
            access_type_code="assigned",
            is_primary=False,
            created_by=current_user.user_id,
            updated_by=current_user.user_id,
        )
        session.add(row)
        await session.flush()
        return row

    async def delete_binding(self, session: AsyncSession, binding: SysUserOrg) -> None:
        await session.delete(binding)


repository = UserOrgRepository()
