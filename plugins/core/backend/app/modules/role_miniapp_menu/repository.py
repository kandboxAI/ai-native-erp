from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.miniapp_menu.models import SysMiniappMenu
from app.modules.rbac_repository_utils import normalize_uuid
from app.modules.role.models import SysRole
from app.modules.user_role.models import SysUserRole

from .models import SysRoleMiniappMenu
from .schemas import RoleMiniappMenuItem, RoleMiniappMenuListQuery


def _base_statement():
    return (
        select(
            SysRoleMiniappMenu.id,
            SysRoleMiniappMenu.role_id,
            SysRoleMiniappMenu.miniapp_menu_id,
            SysRole.role_no,
            SysRole.role_name,
            SysMiniappMenu.portal_code,
            SysMiniappMenu.menu_key,
            SysMiniappMenu.menu_name,
            SysRoleMiniappMenu.created_at,
        )
        .join(SysRole, SysRole.id == SysRoleMiniappMenu.role_id)
        .join(SysMiniappMenu, SysMiniappMenu.id == SysRoleMiniappMenu.miniapp_menu_id)
        .where(SysRole.deleted_at.is_(None), SysMiniappMenu.deleted_at.is_(None))
    )


def _active_menus():
    return (
        select(SysMiniappMenu)
        .where(SysMiniappMenu.deleted_at.is_(None), SysMiniappMenu.is_active.is_(True))
        .order_by(SysMiniappMenu.portal_code, SysMiniappMenu.sort_no.nulls_last(), SysMiniappMenu.menu_key)
    )


class RoleMiniappMenuRepository:
    async def list(self, session: AsyncSession, params: RoleMiniappMenuListQuery) -> dict[str, Any]:
        statement = _base_statement()
        if params.role_id:
            statement = statement.where(SysRoleMiniappMenu.role_id == params.role_id)
        if params.portal_code:
            statement = statement.where(SysMiniappMenu.portal_code == params.portal_code)
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                statement.order_by(SysRole.role_no, SysMiniappMenu.portal_code, SysMiniappMenu.sort_no.nulls_last())
                .limit(params.page_size)
                .offset((params.page - 1) * params.page_size)
            )
        ).all()
        return {
            "items": [RoleMiniappMenuItem(**row._mapping).model_dump(mode="json") for row in rows],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }

    async def detail(self, session: AsyncSession, item_id: str | UUID) -> RoleMiniappMenuItem | None:
        row = (await session.execute(_base_statement().where(SysRoleMiniappMenu.id == normalize_uuid(item_id)))).one_or_none()
        return RoleMiniappMenuItem(**row._mapping) if row else None

    async def get(self, session: AsyncSession, item_id: str | UUID) -> SysRoleMiniappMenu | None:
        return await session.get(SysRoleMiniappMenu, normalize_uuid(item_id))

    async def get_role(self, session: AsyncSession, role_id: UUID) -> SysRole | None:
        role = await session.get(SysRole, role_id)
        return role if role is not None and role.deleted_at is None else None

    async def active_menus(self, session: AsyncSession) -> list[SysMiniappMenu]:
        return list((await session.execute(_active_menus())).scalars().all())

    async def existing_menu_ids(self, session: AsyncSession, menu_ids: list[UUID]) -> set[UUID]:
        if not menu_ids:
            return set()
        statement = select(SysMiniappMenu.id).where(SysMiniappMenu.id.in_(menu_ids), SysMiniappMenu.deleted_at.is_(None))
        return set((await session.execute(statement)).scalars().all())

    async def menu_ids_for_role(self, session: AsyncSession, role_id: UUID) -> set[UUID]:
        statement = select(SysRoleMiniappMenu.miniapp_menu_id).where(SysRoleMiniappMenu.role_id == role_id)
        return set((await session.execute(statement)).scalars().all())

    async def menu_ids_for_user(self, session: AsyncSession, user_id: UUID) -> set[UUID]:
        statement = (
            select(SysRoleMiniappMenu.miniapp_menu_id)
            .join(SysUserRole, SysUserRole.role_id == SysRoleMiniappMenu.role_id)
            .join(SysRole, SysRole.id == SysRoleMiniappMenu.role_id)
            .where(SysUserRole.user_id == user_id, SysRole.is_active.is_(True), SysRole.deleted_at.is_(None))
        )
        return set((await session.execute(statement)).scalars().all())

    async def add(self, session: AsyncSession, role_id: UUID, menu_ids, user: AuthenticatedUser) -> list[SysRoleMiniappMenu]:
        rows = [
            SysRoleMiniappMenu(role_id=role_id, miniapp_menu_id=mid, created_by=user.user_id, updated_by=user.user_id)
            for mid in menu_ids
        ]
        session.add_all(rows)
        await session.flush()
        return rows

    async def remove(self, session: AsyncSession, role_id: UUID, menu_ids) -> None:
        if menu_ids:
            await session.execute(
                delete(SysRoleMiniappMenu).where(
                    SysRoleMiniappMenu.role_id == role_id, SysRoleMiniappMenu.miniapp_menu_id.in_(menu_ids)
                )
            )

    async def delete_binding(self, session: AsyncSession, binding: SysRoleMiniappMenu) -> None:
        await session.delete(binding)


repository = RoleMiniappMenuRepository()


async def ensure_default_grants(session, menu_id, role_nos):
    """开通配置按明确角色编号补齐菜单，仅新增绑定，不改变业务权限。"""
    roles = (await session.execute(select(SysRole.id).where(
        SysRole.role_no.in_(role_nos), SysRole.is_active.is_(True), SysRole.deleted_at.is_(None),
    ))).scalars().all()
    for role_id in roles:
        if menu_id not in await repository.menu_ids_for_role(session, role_id):
            session.add(SysRoleMiniappMenu(role_id=role_id, miniapp_menu_id=menu_id))
    await session.flush()


async def grant_for_permission(session, menu_id, permission_key):
    """配置时按已有有效权限补齐菜单绑定，不增加业务权限、不删除已有绑定。"""
    from app.modules.permission.models import SysPermission
    from app.modules.role_permission.models import SysRolePermission
    role_ids = (await session.execute(select(SysRole.id).join(
        SysRolePermission, SysRolePermission.role_id == SysRole.id).join(
        SysPermission, SysPermission.id == SysRolePermission.permission_id).where(
        SysRole.is_active.is_(True), SysRole.deleted_at.is_(None),
        SysPermission.permission_key == permission_key, SysPermission.is_active.is_(True),
        SysPermission.deleted_at.is_(None)))).scalars().all()
    for role_id in role_ids:
        if menu_id not in await repository.menu_ids_for_role(session, role_id):
            session.add(SysRoleMiniappMenu(role_id=role_id, miniapp_menu_id=menu_id))
    await session.flush()
