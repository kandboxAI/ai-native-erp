from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.menu.models import SysMenu
from app.modules.permission.models import SysPermission
from app.modules.rbac_repository_utils import normalize_uuid
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission

from .models import SysRoleMenu
from .schemas import RoleMenuItem, RoleMenuListQuery


def _base_statement():
    return (
        select(
            SysRoleMenu.id,
            SysRoleMenu.role_id,
            SysRoleMenu.menu_id,
            SysRole.role_no,
            SysRole.role_name,
            SysMenu.menu_key,
            SysMenu.menu_name,
            SysMenu.menu_type_code,
            SysRoleMenu.created_at,
        )
        .join(SysRole, SysRole.id == SysRoleMenu.role_id)
        .join(SysMenu, SysMenu.id == SysRoleMenu.menu_id)
        .where(SysRole.deleted_at.is_(None), SysMenu.deleted_at.is_(None))
    )


class RoleMenuRepository:
    async def reconcile_permission_grants(self, session, requirements: dict[str, tuple[str, ...]], *, actor_id=None) -> None:
        """显式同步指定页面的菜单授权；保留满足任一权限的角色及内置管理员。"""
        from app.modules.role.repository import is_builtin_admin

        roles = (await session.execute(select(SysRole).where(SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)))).scalars().all()
        owned: dict[UUID, set[str]] = {}
        for role_id, key in (await session.execute(
            select(SysRolePermission.role_id, SysPermission.permission_key)
            .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
            .where(SysPermission.deleted_at.is_(None), SysPermission.is_active.is_(True))
        )).all():
            owned.setdefault(role_id, set()).add(key)
        menus = (await session.execute(select(SysMenu).where(SysMenu.menu_key.in_(requirements), SysMenu.deleted_at.is_(None)))).scalars().all()
        existing = set((await session.execute(select(SysRoleMenu.role_id, SysRoleMenu.menu_id).where(SysRoleMenu.menu_id.in_([m.id for m in menus])))).all())
        for menu in menus:
            for role in roles:
                eligible = is_builtin_admin(role) or bool(owned.get(role.id, set()).intersection(requirements[menu.menu_key]))
                if eligible and (role.id, menu.id) not in existing:
                    session.add(SysRoleMenu(role_id=role.id, menu_id=menu.id, created_by=actor_id, updated_by=actor_id))
                elif not eligible and (role.id, menu.id) in existing:
                    await self.remove(session, role.id, {menu.id})
        await session.flush()

    async def grant_for_permission(self, session, menu_key: str, permission_key: str, *, actor_id=None) -> int:
        """仅给已有有效权限的角色补指定菜单；不增业务权限，不改既有菜单绑定。"""
        pairs = (await session.execute(
            select(SysRole.id, SysMenu.id).select_from(SysRole)
            .join(SysRolePermission, SysRolePermission.role_id == SysRole.id)
            .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
            .join(SysMenu, SysMenu.permission_id == SysPermission.id)
            .where(SysRole.is_active.is_(True), SysRole.deleted_at.is_(None),
                SysPermission.permission_key == permission_key, SysPermission.is_active.is_(True),
                SysPermission.deleted_at.is_(None), SysMenu.menu_key == menu_key,
                SysMenu.is_active.is_(True), SysMenu.deleted_at.is_(None))
        )).all()
        if not pairs:
            return 0
        existing = set((await session.execute(
            select(SysRoleMenu.role_id, SysRoleMenu.menu_id)
            .join(SysMenu, SysMenu.id == SysRoleMenu.menu_id).where(SysMenu.menu_key == menu_key)
        )).all())
        added = 0
        for role_id, menu_id in pairs:
            if (role_id, menu_id) not in existing:
                session.add(SysRoleMenu(role_id=role_id, menu_id=menu_id,
                    created_by=actor_id, updated_by=actor_id))
                existing.add((role_id, menu_id))
                added += 1
        await session.flush()
        return added

    async def list(self, session: AsyncSession, params: RoleMenuListQuery, *, allowed_menu_ids: set[UUID]) -> dict[str, Any]:
        # 与菜单树/保存校验共用当前部署和租户启用范围，不回传不可编辑的历史绑定。
        statement = _base_statement().where(SysMenu.id.in_(allowed_menu_ids))
        if params.role_id:
            statement = statement.where(SysRoleMenu.role_id == params.role_id)
        if params.menu_id:
            statement = statement.where(SysRoleMenu.menu_id == params.menu_id)
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            statement = statement.where(or_(SysMenu.menu_key.ilike(keyword), SysMenu.menu_name.ilike(keyword), SysRole.role_name.ilike(keyword)))
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                statement.order_by(SysRole.role_no, SysMenu.sort_no.nulls_last(), SysMenu.menu_key)
                .limit(params.page_size)
                .offset((params.page - 1) * params.page_size)
            )
        ).all()
        return {
            "items": [RoleMenuItem(**row._mapping).model_dump(mode="json") for row in rows],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }

    async def detail(self, session: AsyncSession, item_id: str | UUID) -> RoleMenuItem | None:
        row = (await session.execute(_base_statement().where(SysRoleMenu.id == normalize_uuid(item_id)))).one_or_none()
        return RoleMenuItem(**row._mapping) if row else None

    async def get(self, session: AsyncSession, item_id: str | UUID) -> SysRoleMenu | None:
        return await session.get(SysRoleMenu, normalize_uuid(item_id))

    async def get_role(self, session: AsyncSession, role_id: UUID) -> SysRole | None:
        role = await session.get(SysRole, role_id)
        return role if role is not None and role.deleted_at is None else None

    async def existing_menu_ids(self, session: AsyncSession, menu_ids: list[UUID]) -> set[UUID]:
        if not menu_ids:
            return set()
        statement = select(SysMenu.id).where(SysMenu.id.in_(menu_ids), SysMenu.deleted_at.is_(None))
        return set((await session.execute(statement)).scalars().all())

    async def menu_ids_for_role(self, session: AsyncSession, role_id: UUID) -> set[UUID]:
        return set((await session.execute(select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id))).scalars().all())

    async def add(self, session: AsyncSession, role_id: UUID, menu_ids, user: AuthenticatedUser) -> list[SysRoleMenu]:
        rows = [SysRoleMenu(role_id=role_id, menu_id=mid, created_by=user.user_id, updated_by=user.user_id) for mid in menu_ids]
        session.add_all(rows)
        await session.flush()
        return rows

    async def remove(self, session: AsyncSession, role_id: UUID, menu_ids) -> None:
        if menu_ids:
            await session.execute(delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id, SysRoleMenu.menu_id.in_(menu_ids)))

    async def delete_binding(self, session: AsyncSession, binding: SysRoleMenu) -> None:
        await session.delete(binding)


repository = RoleMenuRepository()
