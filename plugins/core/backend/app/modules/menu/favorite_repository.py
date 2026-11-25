from __future__ import annotations

from uuid import UUID

from fastapi import status
from sqlalchemy import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.catalog import menu_display_icon

from .favorite_schemas import FavoriteMenuItem, UserFavoriteConfig
from .models import SysMenu, SysUserFavorite
from .repository import repository as menu_repository


def build_favorite_candidates(rows: list[SysMenu]) -> list[FavoriteMenuItem]:
    """从授权菜单中提取可见、启用、内部且可直接打开的叶子页面。"""

    by_id = {row.id: row for row in rows}
    visible_ids = {row.id for row in rows if row.is_visible}
    parent_ids = {
        row.parent_id
        for row in rows
        if row.is_visible and row.parent_id in visible_ids
    }
    candidates: list[FavoriteMenuItem] = []
    order_keys: dict[UUID, tuple[tuple[int, str], ...]] = {}
    for row in rows:
        if (
            row.id in parent_ids
            or row.menu_type_code != "menu"
            or not row.is_visible
            or row.is_external
            or not row.path
            or not row.component
        ):
            continue

        ancestor_names: list[str] = []
        order_parts = [(row.sort_no if row.sort_no is not None else 2**31, row.menu_key)]
        parent = by_id.get(row.parent_id) if row.parent_id else None
        seen: set[UUID] = set()
        while parent is not None and parent.id not in seen:
            seen.add(parent.id)
            if parent.is_visible:
                ancestor_names.append(parent.menu_name)
                order_parts.append(
                    (
                        parent.sort_no if parent.sort_no is not None else 2**31,
                        parent.menu_key,
                    )
                )
            parent = by_id.get(parent.parent_id) if parent.parent_id else None
        ancestor_names.reverse()
        order_keys[row.id] = tuple(reversed(order_parts))
        candidates.append(
            FavoriteMenuItem(
                menu_id=row.id,
                menu_key=row.menu_key,
                menu_name=row.menu_name,
                path=row.path,
                icon=menu_display_icon(row.menu_key, row.icon),
                ancestor_names=ancestor_names,
            )
        )
    return sorted(candidates, key=lambda item: order_keys[item.menu_id])


class UserFavoriteRepository:
    async def _candidates(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
    ) -> list[FavoriteMenuItem]:
        rows = await menu_repository.authorized_rows_for_user(session, current_user)
        return build_favorite_candidates(rows)

    async def config(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
    ) -> tuple[UserFavoriteConfig, int]:
        candidates = await self._candidates(session, current_user)
        candidate_by_id = {item.menu_id: item for item in candidates}
        stored = list(
            (
                await session.exec(
                    select(SysUserFavorite)
                    .where(SysUserFavorite.user_id == current_user.user_id)
                    .order_by(SysUserFavorite.sort_no, SysUserFavorite.id)
                )
            )
            .scalars()
            .all()
        )
        invalid_ids = [row.id for row in stored if row.menu_id not in candidate_by_id]
        if invalid_ids:
            await session.exec(
                delete(SysUserFavorite).where(SysUserFavorite.id.in_(invalid_ids))
            )
        items = [
            candidate_by_id[row.menu_id]
            for row in stored
            if row.menu_id in candidate_by_id
        ]
        return UserFavoriteConfig(items=items, candidates=candidates), len(invalid_ids)

    async def replace(
        self,
        session: AsyncSession,
        menu_ids: list[UUID],
        current_user: AuthenticatedUser,
    ) -> UserFavoriteConfig:
        candidates = await self._candidates(session, current_user)
        candidate_by_id = {item.menu_id: item for item in candidates}
        unauthorized = [menu_id for menu_id in menu_ids if menu_id not in candidate_by_id]
        if unauthorized:
            raise AppException(
                "收藏中包含当前账号无权访问的菜单，请刷新后重新选择",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        await session.exec(
            delete(SysUserFavorite).where(
                SysUserFavorite.user_id == current_user.user_id
            )
        )
        session.add_all(
            [
                SysUserFavorite(
                    user_id=current_user.user_id,
                    menu_id=menu_id,
                    sort_no=sort_no,
                    created_by=current_user.user_id,
                    updated_by=current_user.user_id,
                )
                for sort_no, menu_id in enumerate(menu_ids)
            ]
        )
        return UserFavoriteConfig(
            items=[candidate_by_id[menu_id] for menu_id in menu_ids],
            candidates=candidates,
        )


favorite_repository = UserFavoriteRepository()
