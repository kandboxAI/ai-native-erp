from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.framework.db.session import get_session_context

from .favorite_repository import UserFavoriteRepository, favorite_repository
from .favorite_schemas import UserFavoriteConfig, UserFavoriteSave

SessionGetter = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class UserFavoriteService:
    def __init__(
        self,
        repository: UserFavoriteRepository,
        session_getter: SessionGetter,
    ) -> None:
        self.repository = repository
        self.session_getter = session_getter

    async def config(self, current_user: AuthenticatedUser) -> UserFavoriteConfig:
        async with self.session_getter() as session:
            config, removed_count = await self.repository.config(session, current_user)
            if removed_count:
                await session.commit()
            return config

    async def save(
        self,
        payload: UserFavoriteSave,
        current_user: AuthenticatedUser,
    ) -> UserFavoriteConfig:
        async with self.session_getter() as session:
            config = await self.repository.replace(
                session,
                payload.menu_ids,
                current_user,
            )
            await session.commit()
            return config


service = UserFavoriteService(
    repository=favorite_repository,
    session_getter=get_session_context,
)
