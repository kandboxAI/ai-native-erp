from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


MAX_FAVORITES = 6


class FavoriteMenuItem(BaseModel):
    """当前用户可收藏或已经收藏的叶子菜单。"""

    menu_id: UUID
    menu_key: str
    menu_name: str
    path: str
    icon: str | None = None
    ancestor_names: list[str] = Field(default_factory=list)


class UserFavoriteConfig(BaseModel):
    """当前用户的收藏结果及允许选择的菜单目录。"""

    items: list[FavoriteMenuItem] = Field(default_factory=list)
    candidates: list[FavoriteMenuItem] = Field(default_factory=list)
    max_count: int = MAX_FAVORITES


class UserFavoriteSave(BaseModel):
    """按展示顺序完整替换当前用户的收藏。"""

    menu_ids: list[UUID] = Field(default_factory=list, max_length=MAX_FAVORITES)

    @field_validator("menu_ids")
    @classmethod
    def menu_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("收藏菜单不能重复")
        return value
