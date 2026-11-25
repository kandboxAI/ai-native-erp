from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class DepartmentBase(BaseModel):
    org_id: UUID
    department_no: str = Field(..., max_length=64)
    department_name: str = Field(..., max_length=128)
    parent_id: UUID | None = None
    manager_user_id: UUID | None = None
    sort_no: int | None = None
    is_active: bool = True
    remark: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    org_id: UUID | None = None
    department_no: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=128)
    parent_id: UUID | None = None
    manager_user_id: UUID | None = None
    sort_no: int | None = None
    is_active: bool | None = None
    remark: str | None = None


class DepartmentItem(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class DepartmentListQuery(PageParams):
    org_id: UUID | None = None
    is_active: bool | None = None
