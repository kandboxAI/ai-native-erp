from __future__ import annotations

from uuid import UUID

from fastapi import status
from sqlalchemy import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.catalog import can_access_miniapp_menu, miniapp_menu_display_group, miniapp_menu_display_name
from app.framework.deployment import miniapp_menu_plugin_owner
from app.modules.role.models import SysRole
from app.modules.role_miniapp_menu.models import SysRoleMiniappMenu
from app.modules.user_role.models import SysUserRole

from .favorite_schemas import MiniappFavoriteConfig, MiniappFavoriteItem
from .models import SysMiniappMenu, SysUserMiniappFavorite


EXCLUDED_SHELL_PATHS = frozenset(
    {
        "/pages/home/index",
        "/pages/xiaohang/index",
        "/pages/messages/index",
        "/pages/profile/index",
    }
)


def build_favorite_item(menu: SysMiniappMenu) -> MiniappFavoriteItem:
    group_key, group_name = miniapp_menu_display_group(menu.menu_key, menu.group_key, menu.group_name)
    return MiniappFavoriteItem(
        miniapp_menu_id=menu.id, menu_key=menu.menu_key,
        menu_name=miniapp_menu_display_name(menu.menu_key, menu.menu_name),
        path=menu.path, group_key=group_key, group_name=group_name,
    )


class MiniappFavoriteRepository:
    async def _candidates(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
        portal_code: str,
    ) -> list[MiniappFavoriteItem]:
        allowed_ids = set(
            (
                await session.execute(
                    select(SysRoleMiniappMenu.miniapp_menu_id)
                    .join(SysUserRole, SysUserRole.role_id == SysRoleMiniappMenu.role_id)
                    .join(SysRole, SysRole.id == SysRoleMiniappMenu.role_id)
                    .where(
                        SysUserRole.user_id == current_user.user_id,
                        SysRole.is_active.is_(True),
                        SysRole.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not allowed_ids:
            return []

        menus = list(
            (
                await session.execute(
                    select(SysMiniappMenu)
                    .where(
                        SysMiniappMenu.id.in_(allowed_ids),
                        SysMiniappMenu.portal_code == portal_code,
                        SysMiniappMenu.is_active.is_(True),
                        SysMiniappMenu.deleted_at.is_(None),
                        SysMiniappMenu.path.is_not(None),
                    )
                    .order_by(
                        SysMiniappMenu.sort_no.nulls_last(),
                        SysMiniappMenu.menu_key,
                    )
                )
            )
            .scalars()
            .all()
        )
        enabled_plugins = set(current_user.enabled_plugin_keys)
        return [
            build_favorite_item(menu)
            for menu in menus
            if menu.path not in EXCLUDED_SHELL_PATHS
            and can_access_miniapp_menu(
                menu.portal_code,
                menu.menu_key,
                current_user.permissions,
            )
            and (
                (owner := miniapp_menu_plugin_owner(menu.menu_key)) is None
                or owner in enabled_plugins
            )
        ]

    async def config(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
        portal_code: str,
    ) -> tuple[MiniappFavoriteConfig, int]:
        candidates = await self._candidates(session, current_user, portal_code)
        candidate_by_id = {item.miniapp_menu_id: item for item in candidates}
        stored = list(
            (
                await session.execute(
                    select(SysUserMiniappFavorite)
                    .where(SysUserMiniappFavorite.user_id == current_user.user_id)
                    .order_by(
                        SysUserMiniappFavorite.sort_no,
                        SysUserMiniappFavorite.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        invalid_ids = [
            row.id for row in stored if row.miniapp_menu_id not in candidate_by_id
        ]
        if invalid_ids:
            await session.execute(
                delete(SysUserMiniappFavorite).where(
                    SysUserMiniappFavorite.id.in_(invalid_ids)
                )
            )
        items = [
            candidate_by_id[row.miniapp_menu_id]
            for row in stored
            if row.miniapp_menu_id in candidate_by_id
        ]
        return MiniappFavoriteConfig(items=items, candidates=candidates), len(invalid_ids)

    async def replace(
        self,
        session: AsyncSession,
        menu_ids: list[UUID],
        current_user: AuthenticatedUser,
        portal_code: str,
    ) -> MiniappFavoriteConfig:
        candidates = await self._candidates(session, current_user, portal_code)
        candidate_by_id = {item.miniapp_menu_id: item for item in candidates}
        unauthorized = [menu_id for menu_id in menu_ids if menu_id not in candidate_by_id]
        if unauthorized:
            raise AppException(
                "常用菜单中包含当前账号无权访问的入口，请刷新后重新选择",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        await session.execute(
            delete(SysUserMiniappFavorite).where(
                SysUserMiniappFavorite.user_id == current_user.user_id
            )
        )
        session.add_all(
            [
                SysUserMiniappFavorite(
                    user_id=current_user.user_id,
                    miniapp_menu_id=menu_id,
                    sort_no=sort_no,
                    created_by=current_user.user_id,
                    updated_by=current_user.user_id,
                )
                for sort_no, menu_id in enumerate(menu_ids)
            ]
        )
        return MiniappFavoriteConfig(
            items=[candidate_by_id[menu_id] for menu_id in menu_ids],
            candidates=candidates,
        )


favorite_repository = MiniappFavoriteRepository()
