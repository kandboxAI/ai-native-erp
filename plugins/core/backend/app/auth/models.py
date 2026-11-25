"""表模型（auth_user、auth_identity、auth_password_history、auth_tenant、auth_membership、auth_login_log）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class AuthUser(SQLModel, table=True):
    """登录账号：一行为一个可以登录的账号（全局唯一，不属于任何租户）。"""

    __tablename__ = "auth_user"
    __table_args__ = (
        Index("uk_auth_user_email", "email", unique=True),
        Index("uk_auth_user_mobile", "mobile", unique=True),
        {'comment': '登录账号：一行为一个可以登录的账号（全局唯一，不属于任何租户）。统一登录的账号。登录成功后，进入哪个租户、看到哪些数据，由该租户 schema 中的租户内用户 `sys_user` 决定。', 'schema': 'public'},
    )

    id: UUID = id_field()
    email: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '登录邮箱；敏感：个人；全局唯一'})
    mobile: str | None = Field(default=None, max_length=32, nullable=True, sa_column_kwargs={'comment': '登录手机号；敏感：个人；全局唯一'})
    password_hash: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '密码哈希；敏感：机密；只供认证服务读取'})
    is_active: bool = bool_field('是否启用；停用后不能登录', default=True)
    is_email_verified: bool = bool_field('邮箱是否已验证', default=False)
    password_changed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '最近改密时间'})
    is_password_change_required: bool = bool_field('下次登录必须改密', default=False)
    failed_login_count: int = Field(default=0, nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": '连续登录失败次数；达到阈值后锁定'})
    locked_until: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '锁定截止时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；引用登录账号；系统任务写入时为空', target="public.auth_user.id")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人；引用登录账号', target="public.auth_user.id")
    flex_form: dict[str, Any] = flex_form_field('扩展字段；账号级扩展信息，与租户无关；学校自定义的用户字段在 sys_user.flex_form；默认 {}')


class AuthIdentity(SQLModel, table=True):
    """外部身份：一行为一个账号绑定的一个外部登录身份。"""

    __tablename__ = "auth_identity"
    __table_args__ = (
        Index(
            "uk_auth_identity_provider_appid_external_user_no",
            "provider",
            "appid",
            "external_user_no",
            unique=True,
        ),
        Index(
            "uk_auth_identity_provider_appid_auth_user_id",
            "provider",
            "appid",
            "auth_user_id",
            unique=True,
        ),
        {'comment': '外部身份：一行为一个账号绑定的一个外部登录身份。微信、企业微信等外部身份与登录账号的绑定，用于扫码或一键登录。', 'schema': 'public'},
    )

    id: UUID = id_field()
    auth_user_id: UUID = Field(foreign_key="public.auth_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '登录账号'})
    provider: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '身份提供方；字典 ntf_provider'})
    appid: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '应用 ID'})
    external_user_no: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '外部用户标识；敏感：个人；如微信 openid'})
    unionid: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '微信 unionid；敏感：个人'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；引用登录账号；系统任务写入时为空', target="public.auth_user.id")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人；引用登录账号', target="public.auth_user.id")
    flex_form: dict[str, Any] = flex_form_field('扩展字段；账号级扩展信息，与租户无关；学校自定义的用户字段在 sys_user.flex_form；默认 {}')


class AuthPasswordHistory(SQLModel, table=True):
    """密码历史：一行为一次密码设置。"""

    __tablename__ = "auth_password_history"
    __table_args__ = (
        {'comment': '密码历史：一行为一次密码设置。用于“不得与最近 N 次密码相同”的校验。', 'schema': 'public'},
    )

    id: UUID = id_field()
    auth_user_id: UUID = Field(foreign_key="public.auth_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '登录账号'})
    password_hash: str = Field(max_length=255, nullable=False, sa_column_kwargs={'comment': '历史密码哈希；敏感：机密'})
    created_at: datetime = created_at_field()


class AuthTenant(SQLModel, table=True):
    """租户：一行为一个租户（一个教育集团或一所学校）。"""

    __tablename__ = "auth_tenant"
    __table_args__ = (
        Index("uk_auth_tenant_tenant_no", "tenant_no", unique=True),
        Index("uk_auth_tenant_schema_name", "schema_name", unique=True),
        {'comment': '租户：一行为一个租户（一个教育集团或一所学校）。租户目录。每个租户的业务数据在自己的 schema 中（`schema_name`），不同租户互不可见；登录时据此切换 schema。', 'schema': 'public'},
    )

    id: UUID = id_field()
    tenant_no: str = Field(max_length=32, nullable=False, sa_column_kwargs={'comment': '租户编号；小写字母、数字、下划线；schema 名为 t_<租户编号>'})
    tenant_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '租户名称'})
    schema_name: str = Field(max_length=63, nullable=False, sa_column_kwargs={'comment': '租户 schema；如 t_edu；创建后不修改'})
    is_active: bool = bool_field('是否启用；停用后该租户的用户不能登录', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；引用登录账号；系统任务写入时为空', target="public.auth_user.id")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人；引用登录账号', target="public.auth_user.id")
    flex_form: dict[str, Any] = flex_form_field('扩展字段；账号级扩展信息，与租户无关；学校自定义的用户字段在 sys_user.flex_form；默认 {}')


class AuthTenantPlugin(SQLModel, table=True):
    """租户能力包：一行记录一个租户对一个能力包的开通和启停状态。"""

    __tablename__ = "auth_tenant_plugin"
    __table_args__ = (
        Index("uk_auth_tenant_plugin_tenant_id_plugin_key", "tenant_id", "plugin_key", unique=True),
        {"comment": "租户能力包：一行记录一个租户对一个能力包的开通和启停状态。", "schema": "public"},
    )

    id: UUID = id_field()
    tenant_id: UUID = Field(foreign_key="public.auth_tenant.id", ondelete="CASCADE", nullable=False, sa_column_kwargs={"comment": "所属租户；引用 public.auth_tenant.id"})
    plugin_key: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "能力包稳定标识；与 plugin.toml 的 key 一致"})
    installed_version: str | None = Field(default=None, max_length=32, nullable=True, sa_column_kwargs={"comment": "最近一次成功开通的能力包版本；实际数据库修订以租户 alembic_version 为准"})
    provisioning_status_code: str = Field(default="pending", max_length=32, nullable=False, sa_column_kwargs={"server_default": text("'pending'"), "comment": "开通状态；字典 auth_tenant_plugin_provisioning_status"})
    is_active: bool = bool_field("是否启用；仅 ready 且启用时开放入口", default=False)
    enabled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "最近一次启用时间"})
    last_error_type: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={"comment": "最近开通失败的异常类别；不包含连接串、凭据或个人信息"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；引用登录账号；系统开通时为空", target="public.auth_user.id")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；引用登录账号；系统开通时为空", target="public.auth_user.id")
    flex_form: dict[str, Any] = flex_form_field("租户能力包扩展配置；默认 {}")


class AuthMembership(SQLModel, table=True):
    """账号可进入的租户：一行为一个账号可以进入的一个租户。"""

    __tablename__ = "auth_membership"
    __table_args__ = (
        Index("uk_auth_membership_auth_user_id_tenant_id", "auth_user_id", "tenant_id", unique=True),
        {'comment': '账号可进入的租户：一行为一个账号可以进入的一个租户。登录后供用户选择进入哪个租户。由开通、停用租户内用户的流程同步维护。', 'schema': 'public'},
    )

    id: UUID = id_field()
    auth_user_id: UUID = Field(foreign_key="public.auth_user.id", nullable=False, sa_column_kwargs={'comment': '登录账号'})
    tenant_id: UUID = Field(foreign_key="public.auth_tenant.id", index=True, nullable=False, sa_column_kwargs={'comment': '租户'})
    last_entered_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '最近进入时间'})
    is_active: bool = bool_field('是否可进入', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；引用登录账号；系统任务写入时为空', target="public.auth_user.id")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人；引用登录账号', target="public.auth_user.id")
    flex_form: dict[str, Any] = flex_form_field('扩展字段；账号级扩展信息，与租户无关；学校自定义的用户字段在 sys_user.flex_form；默认 {}')


class AuthLoginLog(SQLModel, table=True):
    """登录日志：一行为一次登录尝试。"""

    __tablename__ = "auth_login_log"
    __table_args__ = (
        {'comment': '登录日志：一行为一次登录尝试。成功和失败的登录都记录。', 'schema': 'public'},
    )

    id: UUID = id_field()
    auth_user_id: UUID | None = Field(default=None, foreign_key="public.auth_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '登录账号；登录失败且账号不存在时为空'})
    login_name: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '登录名；敏感：个人；用户输入的邮箱或手机号'})
    ip_address: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': 'IP 地址；敏感：个人'})
    user_agent: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '终端信息'})
    is_success: bool = bool_field('是否成功', default=False)
    message: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '结果说明'})
    created_at: datetime = created_at_field()
