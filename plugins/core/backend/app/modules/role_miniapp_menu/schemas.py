from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams
from app.modules.miniapp_menu.schemas import MiniappMenuGroup, MiniappPortal


class RoleMiniappMenuCreate(BaseModel):
    role_id: UUID
    miniapp_menu_id: UUID


class RoleMiniappMenuBatchSync(BaseModel):
    """把角色在小程序中可见的菜单对齐为提交的集合（跨全部门户）。"""

    role_id: UUID
    miniapp_menu_ids: list[UUID] = Field(default_factory=list)


class RoleMiniappMenuListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    role_id: UUID | None = None
    portal_code: MiniappPortal | None = None


class RoleMiniappMenuItem(BaseModel):
    id: UUID
    role_id: UUID
    miniapp_menu_id: UUID
    role_no: str
    role_name: str
    portal_code: str
    menu_key: str
    menu_name: str
    created_at: datetime


class RoleMiniappMenuRoleConfig(BaseModel):
    role_id: UUID
    miniapp_menu_ids: list[UUID] = Field(default_factory=list)
    menu_keys_by_portal: dict[str, list[str]] = Field(default_factory=dict)


class CurrentMiniappMenuConfig(BaseModel):
    portal_code: str
    menu_keys: list[str] = Field(default_factory=list)
    groups: list[MiniappMenuGroup] = Field(default_factory=list)
