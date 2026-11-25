from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams

DataScopeCode = Literal["all", "organization", "department", "self", "related"]


class RolePermissionCreate(BaseModel):
    role_id: UUID
    permission_id: UUID
    data_scope_code: DataScopeCode | None = Field(default=None, description="为空时取角色的数据范围")


class RolePermissionUpdate(BaseModel):
    data_scope_code: DataScopeCode | None = None


class RolePermissionScopeItem(BaseModel):
    permission_id: UUID
    data_scope_code: DataScopeCode | None = None


class RolePermissionBatchSync(BaseModel):
    """把角色的权限一次性对齐为提交的集合（多删少补）。"""

    role_id: UUID
    permission_ids: list[UUID] = Field(default_factory=list)
    permission_scopes: list[RolePermissionScopeItem] = Field(default_factory=list)


class RolePermissionListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    role_id: UUID | None = None
    permission_id: UUID | None = None
    module_code: str | None = Field(default=None, max_length=64)
    sort_by: Literal["updated_at", "created_at", "role_no", "permission_key", "module_code"] = "permission_key"
    sort_order: Literal["asc", "desc"] = "asc"


class RolePermissionItem(BaseModel):
    id: UUID
    role_id: UUID
    permission_id: UUID
    data_scope_code: str | None = None  # 权限上单独配置的数据范围
    effective_data_scope_code: str
    role_no: str
    role_name: str
    permission_key: str
    permission_name: str
    module_code: str
    created_at: datetime
    updated_at: datetime
