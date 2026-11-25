from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MiniappFavoriteItem(BaseModel):
    """当前用户可设置为常用的已授权小程序入口。"""

    miniapp_menu_id: UUID
    menu_key: str
    menu_name: str
    path: str
    group_key: str | None = None
    group_name: str | None = None


class MiniappFavoriteConfig(BaseModel):
    """当前用户的小程序常用入口及可选目录。"""

    items: list[MiniappFavoriteItem] = Field(default_factory=list)
    candidates: list[MiniappFavoriteItem] = Field(default_factory=list)


class MiniappFavoriteSave(BaseModel):
    """按展示顺序完整替换当前用户的小程序常用入口。"""

    menu_ids: list[UUID] = Field(default_factory=list)

    @field_validator("menu_ids")
    @classmethod
    def menu_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("常用菜单不能重复")
        return value
