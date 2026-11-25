from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.data_scope import ORG_ACCESS_PRIMARY_ONLY
from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin

OrgAccessModeCode = Literal["primary_only", "assigned", "all"]  # 字典 sys_org_access_mode


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class UserListQuery(PageParams):
    full_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    mobile: str | None = Field(default=None, max_length=32)
    org_id: UUID | None = None
    department_id: UUID | None = None
    role_id: UUID | None = None
    role_no: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    sort_by: Literal["updated_at", "created_at", "display_name", "email", "role_count"] = "updated_at"
    sort_order: Literal["asc", "desc"] = "desc"


class UserCreate(BaseModel):
    """新增用户：登录账号（public.auth_user）+ 账号可进入的租户 + 租户内用户 + 人员 + 组织 + 角色。

    邮箱、手机号至少填写一个；该账号已在其他租户存在时复用（不修改其密码）。
    """

    email: str | None = Field(default=None, max_length=255)
    mobile: str | None = Field(default=None, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    org_id: UUID
    org_access_mode_code: OrgAccessModeCode = ORG_ACCESS_PRIMARY_ONLY
    org_ids: list[UUID] = Field(default_factory=list, description="授权的组织（访问方式为 assigned 时）")
    department_id: UUID | None = None
    role_ids: list[UUID] = Field(default_factory=list)
    position_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("email", "mobile", "display_name", mode="before")
    @classmethod
    def _blank(cls, value):
        return _blank_to_none(value)


class UserUpdate(BaseModel):
    """登录邮箱是账号级信息，不在这里修改；手机号暂时只读。"""

    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    # 保留请求字段以便对旧客户端给出明确业务错误，Service 禁止写入。
    mobile: str | None = Field(default=None, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=1024)
    org_id: UUID | None = None
    org_access_mode_code: OrgAccessModeCode | None = None
    org_ids: list[UUID] | None = None
    department_id: UUID | None = None
    role_ids: list[UUID] | None = None
    position_ids: list[UUID] | None = None
    is_active: bool | None = None

    @field_validator("mobile", "display_name", mode="before")
    @classmethod
    def _blank(cls, value):
        return _blank_to_none(value)


class UserResetPassword(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)
    is_password_change_required: bool = False


class AvatarSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: UUID


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleBrief(BaseModel):
    id: UUID
    role_no: str
    role_name: str


class UserPermissionBrief(BaseModel):
    id: UUID
    permission_key: str
    permission_name: str
    module_code: str


class UserListItem(DisplayDatetimeJsonMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth_user_id: UUID
    party_id: UUID | None = None
    display_name: str
    full_name: str | None = None
    email: str | None = None
    mobile: str | None = None
    avatar_url: str | None = None
    org_id: UUID
    org_name: str | None = None
    org_access_mode_code: str = ORG_ACCESS_PRIMARY_ONLY
    org_ids: list[UUID] = Field(default_factory=list)
    department_id: UUID | None = None
    department_name: str | None = None
    is_active: bool = True
    account_is_active: bool = True
    roles: list[UserRoleBrief] = Field(default_factory=list)
    position_ids: list[UUID] = Field(default_factory=list)
    role_count: int = 0
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None


class UserDetailItem(UserListItem):
    permissions: list[UserPermissionBrief] = Field(default_factory=list)
