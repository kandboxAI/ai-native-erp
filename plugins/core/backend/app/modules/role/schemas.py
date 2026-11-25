from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.auth.data_scope import DATA_SCOPE_ORGANIZATION
from app.db.pagination import PageParams

DataScopeCode = Literal["all", "organization", "department", "self", "related"]  # 字典 sys_data_scope


class RoleBase(BaseModel):
    role_no: str = Field(..., max_length=64)
    role_name: str = Field(..., max_length=128)
    description: str | None = None
    data_scope_code: DataScopeCode = DATA_SCOPE_ORGANIZATION
    is_active: bool = True


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    role_no: str | None = Field(default=None, max_length=64)
    role_name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    data_scope_code: DataScopeCode | None = None
    is_active: bool | None = None


class RoleListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=500)
    role_no: str | None = Field(default=None, max_length=64)
    role_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    sort_by: Literal["updated_at", "created_at", "role_no", "role_name", "user_count", "permission_count"] = "updated_at"
    sort_order: Literal["asc", "desc"] = "desc"


class RoleListItem(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_builtin: bool = False
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None
    user_count: int = 0
    permission_count: int = 0
    menu_count: int = 0


class RolePermissionItem(BaseModel):
    id: UUID
    permission_key: str
    permission_name: str
    module_code: str
    data_scope_code: str  # 生效的数据范围：权限上配置的，否则取角色的
    is_scope_overridden: bool = False


class RoleMenuItem(BaseModel):
    id: UUID
    menu_key: str
    menu_name: str
    menu_type_code: str
    path: str | None = None


class RoleUserItem(BaseModel):
    id: UUID
    display_name: str
    full_name: str | None = None


class RoleDetailItem(RoleListItem):
    permissions: list[RolePermissionItem] = Field(default_factory=list)
    menus: list[RoleMenuItem] = Field(default_factory=list)
    users: list[RoleUserItem] = Field(default_factory=list)
    miniapp_menu_ids: list[UUID] = Field(default_factory=list)


class RolePermissionConfigItem(BaseModel):
    id: UUID
    permission_key: str
    permission_name: str
    module_code: str
    selected: bool = False
    data_scope_code: str = DATA_SCOPE_ORGANIZATION


class RolePermissionConfig(BaseModel):
    role: RoleListItem
    permissions: list[RolePermissionConfigItem] = Field(default_factory=list)


class RolePermissionTemplateImportError(BaseModel):
    row: int
    message: str


class RolePermissionTemplateImportResult(BaseModel):
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    role_menu_total: int = 0
    role_permission_total: int = 0
    errors: list[RolePermissionTemplateImportError] = Field(default_factory=list)
