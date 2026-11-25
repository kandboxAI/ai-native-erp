from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class PermissionUpdate(BaseModel):
    """权限由代码定义（permission_key、module_code 不可修改），租户只能改名称与启停。"""

    permission_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class PermissionListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    permission_key: str | None = Field(default=None, max_length=128)
    permission_name: str | None = Field(default=None, max_length=128)
    module_code: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    sort_by: Literal["updated_at", "created_at", "permission_key", "module_code", "role_count"] = "permission_key"
    sort_order: Literal["asc", "desc"] = "asc"


class PermissionRoleItem(BaseModel):
    id: UUID
    role_no: str
    role_name: str


class PermissionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    permission_key: str
    permission_name: str
    module_code: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None
    role_count: int = 0


class PermissionDetailItem(PermissionItem):
    roles: list[PermissionRoleItem] = Field(default_factory=list)
