from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.permission.models import SysPermission
from app.modules.rbac_repository_utils import normalize_uuid, utc_now
from app.modules.role.models import SysRole

from .models import SysRolePermission
from .schemas import RolePermissionItem, RolePermissionListQuery


def _base_statement():
    return (
        select(
            SysRolePermission.id,
            SysRolePermission.role_id,
            SysRolePermission.permission_id,
            SysRolePermission.data_scope_code,
            func.coalesce(SysRolePermission.data_scope_code, SysRole.data_scope_code).label("effective_data_scope_code"),
            SysRole.role_no,
            SysRole.role_name,
            SysPermission.permission_key,
            SysPermission.permission_name,
            SysPermission.module_code,
            SysRolePermission.created_at,
            SysRolePermission.updated_at,
        )
        .join(SysRole, SysRole.id == SysRolePermission.role_id)
        .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
        .where(SysRole.deleted_at.is_(None), SysPermission.deleted_at.is_(None))
    )


class RolePermissionRepository:
    async def ensure_default_grants(self, session, defaults, actor_id=None):
        """模块开通时补齐明确声明的预置授权；不创建角色、不修改范围、不移除已有授权。"""
        permissions = (await session.execute(select(SysPermission).where(
            SysPermission.permission_key.in_(defaults),SysPermission.deleted_at.is_(None),SysPermission.is_active.is_(True)))).scalars().all()
        role_nos = set().union(*defaults.values()) if defaults else set()
        roles = (await session.execute(select(SysRole).where(
            SysRole.role_no.in_(role_nos),SysRole.deleted_at.is_(None),SysRole.is_active.is_(True)))).scalars().all()
        existing = set((await session.execute(select(SysRolePermission.role_id,SysRolePermission.permission_id))).all())
        added = 0
        for permission in permissions:
            for role in roles:
                key = (role.id,permission.id)
                if role.role_no in defaults[permission.permission_key] and key not in existing:
                    session.add(SysRolePermission(role_id=role.id,permission_id=permission.id,
                        created_by=actor_id,updated_by=actor_id))
                    existing.add(key)
                    added += 1
        await session.flush()
        return added
    async def list(self, session: AsyncSession, params: RolePermissionListQuery) -> dict[str, Any]:
        statement = _base_statement()
        if params.role_id:
            statement = statement.where(SysRolePermission.role_id == params.role_id)
        if params.permission_id:
            statement = statement.where(SysRolePermission.permission_id == params.permission_id)
        if params.module_code:
            statement = statement.where(SysPermission.module_code == params.module_code)
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            statement = statement.where(
                or_(
                    SysRole.role_no.ilike(keyword),
                    SysRole.role_name.ilike(keyword),
                    SysPermission.permission_key.ilike(keyword),
                    SysPermission.permission_name.ilike(keyword),
                )
            )
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        sort_map = {
            "updated_at": SysRolePermission.updated_at,
            "created_at": SysRolePermission.created_at,
            "role_no": SysRole.role_no,
            "permission_key": SysPermission.permission_key,
            "module_code": SysPermission.module_code,
        }
        order = sort_map[params.sort_by]
        order = order.asc() if params.sort_order == "asc" else order.desc()
        rows = (
            await session.execute(
                statement.order_by(order, SysRolePermission.id).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        items = [RolePermissionItem(**row._mapping).model_dump(mode="json") for row in rows]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, session: AsyncSession, item_id: str | UUID) -> RolePermissionItem | None:
        row = (await session.execute(_base_statement().where(SysRolePermission.id == normalize_uuid(item_id)))).one_or_none()
        return RolePermissionItem(**row._mapping) if row else None

    async def get(self, session: AsyncSession, item_id: str | UUID) -> SysRolePermission | None:
        return await session.get(SysRolePermission, normalize_uuid(item_id))

    async def get_role(self, session: AsyncSession, role_id: UUID) -> SysRole | None:
        role = await session.get(SysRole, role_id)
        return role if role is not None and role.deleted_at is None else None

    async def existing_permission_ids(self, session: AsyncSession, permission_ids: list[UUID]) -> set[UUID]:
        if not permission_ids:
            return set()
        statement = select(SysPermission.id).where(SysPermission.id.in_(permission_ids), SysPermission.deleted_at.is_(None))
        return set((await session.execute(statement)).scalars().all())

    async def allowed_permission_ids(self, session: AsyncSession, permission_ids: list[UUID], blocked_module_codes: set[str]) -> set[UUID]:
        if not permission_ids:
            return set()
        statement = select(SysPermission.id).where(SysPermission.id.in_(permission_ids), SysPermission.deleted_at.is_(None))
        if blocked_module_codes:
            statement = statement.where(SysPermission.module_code.not_in(blocked_module_codes))
        return set((await session.execute(statement)).scalars().all())

    async def find_binding(self, session: AsyncSession, role_id: UUID, permission_id: UUID) -> SysRolePermission | None:
        statement = select(SysRolePermission).where(
            SysRolePermission.role_id == role_id, SysRolePermission.permission_id == permission_id
        )
        return (await session.execute(statement)).scalar_one_or_none()

    async def bindings_for_role(self, session: AsyncSession, role_id: UUID) -> list[SysRolePermission]:
        statement = select(SysRolePermission).where(SysRolePermission.role_id == role_id)
        return list((await session.execute(statement)).scalars().all())

    async def add(self, session: AsyncSession, role_id: UUID, permission_id: UUID, data_scope_code: str | None, user: AuthenticatedUser) -> SysRolePermission:
        binding = SysRolePermission(
            role_id=role_id,
            permission_id=permission_id,
            data_scope_code=data_scope_code,
            created_by=user.user_id,
            updated_by=user.user_id,
        )
        session.add(binding)
        await session.flush()
        return binding

    async def set_scope(self, session: AsyncSession, binding: SysRolePermission, data_scope_code: str | None, user: AuthenticatedUser) -> None:
        binding.data_scope_code = data_scope_code
        binding.updated_by = user.user_id
        binding.updated_at = utc_now()
        session.add(binding)

    async def remove(self, session: AsyncSession, role_id: UUID, permission_ids: set[UUID]) -> None:
        if permission_ids:
            await session.execute(
                delete(SysRolePermission).where(
                    SysRolePermission.role_id == role_id, SysRolePermission.permission_id.in_(permission_ids)
                )
            )

    async def delete_binding(self, session: AsyncSession, binding: SysRolePermission) -> None:
        await session.delete(binding)


repository = RolePermissionRepository()
