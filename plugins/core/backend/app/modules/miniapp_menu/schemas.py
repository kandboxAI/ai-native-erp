from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin

MiniappPortal = str  # 字典 sys_miniapp_portal
MINIAPP_PORTALS: tuple[str, ...] = ("standard",)


class MiniappMenuBase(BaseModel):
    portal_code: MiniappPortal
    menu_key: str = Field(..., min_length=1, max_length=128)
    menu_name: str = Field(..., min_length=1, max_length=128)
    group_key: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)
    sort_no: int | None = Field(default=None, ge=0, le=999999)
    is_active: bool = True


class MiniappMenuCreate(MiniappMenuBase):
    pass


class MiniappMenuUpdate(BaseModel):
    """portal_code、menu_key 创建后不可修改。"""

    menu_name: str | None = Field(default=None, min_length=1, max_length=128)
    group_key: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)
    sort_no: int | None = Field(default=None, ge=0, le=999999)
    is_active: bool | None = None


class MiniappMenuListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=500)
    portal_code: MiniappPortal | None = None
    group_key: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class MiniappMenuItem(DisplayDatetimeJsonMixin, MiniappMenuBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None


class MiniappMenuPickerItem(BaseModel):
    id: UUID
    menu_key: str
    menu_name: str
    path: str | None = None


class MiniappMenuGroup(BaseModel):
    group_key: str | None = None
    group_name: str | None = None
    items: list[MiniappMenuPickerItem] = Field(default_factory=list)
