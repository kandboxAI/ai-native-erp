from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.pagination import PageParams

ORG_TYPE_GROUP = "group"
ORG_TYPE_ORGANIZATION = "organization"

def _check_org_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > 64:
        raise ValueError("请选择有效的组织类型")
    return normalized


class OrganizationBase(BaseModel):
    org_no: str = Field(..., max_length=64)
    org_name: str = Field(..., max_length=128)
    org_type_code: str = Field(default=ORG_TYPE_ORGANIZATION, max_length=64, description="字典 sys_org_type")
    parent_id: UUID | None = None
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    sort_no: int | None = None
    is_active: bool = True
    remark: str | None = None

    @field_validator("org_type_code")
    @classmethod
    def _validate_type(cls, value):
        return _check_org_type(value)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    org_no: str | None = Field(default=None, max_length=64)
    org_name: str | None = Field(default=None, max_length=128)
    org_type_code: str | None = Field(default=None, max_length=64)
    parent_id: UUID | None = None
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    sort_no: int | None = None
    is_active: bool | None = None
    remark: str | None = None

    @field_validator("org_type_code")
    @classmethod
    def _validate_type(cls, value):
        return _check_org_type(value)


class OrganizationItem(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class OrganizationListQuery(PageParams):
    org_type_code: str | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None


class OrganizationListWithDepartmentsQuery(PageParams):
    org_no: str | None = Field(default=None, max_length=64)
    org_name: str | None = Field(default=None, max_length=128)
    org_type_code: str | None = Field(default=None, max_length=64)
    parent_id: UUID | None = None
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    created_at_start: datetime | None = None
    created_at_end: datetime | None = None

    @field_validator("org_type_code", mode="before")
    @classmethod
    def _empty_type(cls, value):
        return None if value in ("", None) else _check_org_type(value)


class OrganizationDepartmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    department_no: str
    department_name: str
    parent_id: UUID | None = None
    manager_user_id: UUID | None = None
    sort_no: int | None = None
    is_active: bool = True
    remark: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationWithDepartmentsItem(OrganizationItem):
    children: list[OrganizationDepartmentItem] = Field(default_factory=list)


class OrganizationTreeNode(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    org_no: str
    org_name: str
    org_type_code: str
    sort_no: int | None = None
    is_active: bool = True
    children: list["OrganizationTreeNode"] = Field(default_factory=list)
