from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.framework.db.session import get_session_context

from .favorite_repository import MiniappFavoriteRepository, favorite_repository
from .favorite_schemas import MiniappFavoriteConfig, MiniappFavoriteSave

SessionGetter = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class MiniappFavoriteService:
    def __init__(
        self,
        repository: MiniappFavoriteRepository,
        session_getter: SessionGetter,
    ) -> None:
        self.repository = repository
        self.session_getter = session_getter

    async def config(
        self,
        current_user: AuthenticatedUser,
        portal_code: str,
    ) -> MiniappFavoriteConfig:
        async with self.session_getter() as session:
            config, removed_count = await self.repository.config(
                session,
                current_user,
                portal_code,
            )
            if removed_count:
                await session.commit()
            return config

    async def save(
        self,
        payload: MiniappFavoriteSave,
        current_user: AuthenticatedUser,
        portal_code: str,
    ) -> MiniappFavoriteConfig:
        async with self.session_getter() as session:
            config = await self.repository.replace(
                session,
                payload.menu_ids,
                current_user,
                portal_code,
            )
            await session.commit()
            return config


favorite_service = MiniappFavoriteService(
    repository=favorite_repository,
    session_getter=get_session_context,
)
