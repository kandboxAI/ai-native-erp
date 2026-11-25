from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.auth.data_scope import DATA_SCOPE_ORGANIZATION, ORG_ACCESS_PRIMARY_ONLY

LoginPortal = Literal["family", "employee"]


class AuthenticatedUser(BaseModel):
    """当前登录用户：一个登录账号（auth_user）在一个租户中的用户身份（sys_user）。

    - tenant_id / tenant_no / tenant_schema：本次会话进入的租户（public.auth_tenant），业务数据在 tenant_schema 中；
    - user_id：租户内用户 sys_user.id，写入 created_by / updated_by 等字段；
    - auth_user_id：登录账号 public.auth_user.id，只用于认证与会话；
    - role_nos：角色编号，仅用于展示；代码只按 permissions 判断，不按角色判断。
    """

    model_config = ConfigDict(from_attributes=True)

    auth_user_id: UUID
    tenant_id: UUID
    tenant_no: str
    tenant_schema: str
    tenant_name: str | None = None
    user_id: UUID
    party_id: UUID | None = None
    org_id: UUID | None = None
    org_ids: list[UUID] = Field(default_factory=list)
    org_access_mode_code: str = ORG_ACCESS_PRIMARY_ONLY
    department_id: UUID | None = None
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    data_scope_code: str = DATA_SCOPE_ORGANIZATION
    permission_scopes: dict[str, str] = Field(default_factory=dict)
    role_nos: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list, description="当前账号的角色展示名称；不参与权限判断")
    permissions: list[str] = Field(default_factory=list)
    enabled_plugin_keys: list[str] = Field(default_factory=list)
    is_guardian: bool = False
    is_teacher: bool = False
    profile: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    login_name: str = Field(..., min_length=1, max_length=128, description="邮箱、手机号或员工登录名")
    password: str = Field(..., min_length=6, max_length=128)
    captcha_id: str = Field(..., min_length=1, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=16)
    remember_me: bool = Field(default=False, strict=True, description="是否跨客户端重启保留登录")
    remember_days: int = Field(default=7, ge=1, le=30, strict=True, description="免登录天数，受服务端最大期限限制")
    tenant_id: UUID | None = Field(default=None, description="账号可进入多个租户时指定进入哪个租户")
    portal: LoginPortal | None = Field(
        default=None,
        description="登录端类型：family-家长端 employee-教职工端",
    )


class WechatMiniappLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=512, description="wx.login 返回的一次性登录凭证")
    phone_code: str | None = Field(
        default=None,
        max_length=512,
        description="首次绑定时由 getPhoneNumber 返回的一次性手机号凭证",
    )
    tenant_id: UUID | None = Field(default=None, description="账号可进入多个租户时指定进入哪个租户")


class LoginCaptchaResponse(BaseModel):
    captcha_id: str
    image: str
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class AuthSession(BaseModel):
    user_id: UUID | None = None
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None = None
    expires_at: int | None = None
    remember_me: bool = False
    session_expires_at: int | None = None


class LoginResponse(BaseModel):
    session: AuthSession
    user: AuthenticatedUser
