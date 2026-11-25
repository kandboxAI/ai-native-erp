"""表模型（sys_user、sys_user_org、sys_user_position）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
    utc_now,
)


class SysUser(SQLModel, table=True):
    """租户内用户：一行为一个登录账号在一个租户中的用户身份。"""

    __tablename__ = "sys_user"
    __table_args__ = (
        Index("uk_sys_user_auth_user_id", "auth_user_id", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '租户内用户：一行为一个登录账号在一个租户中的用户身份。用户进入租户后的身份：所属组织、部门、角色都挂在这里。姓名、电话等人员信息在 `md_person`（经 `md_person.user_id` 关联）。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    auth_user_id: UUID = Field(foreign_key="public.auth_user.id", nullable=False, sa_column_kwargs={'comment': '登录账号；跨 schema 引用 `public.auth_user`；本租户内唯一'})
    display_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '显示名称；敏感：个人'})
    avatar_url: str | None = Field(default=None, max_length=1024, nullable=True, sa_column_kwargs={'comment': '头像'})
    department_id: UUID | None = Field(default=None, foreign_key="sys_department.id", index=True, nullable=True, sa_column_kwargs={'comment': '所属部门'})
    org_access_mode_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '组织访问方式；字典 sys_org_access_mode'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class SysUserOrg(SQLModel, table=True):
    """用户可访问的组织：一行为一个用户被授权访问的一个组织。"""

    __tablename__ = "sys_user_org"
    __table_args__ = (
        Index("uk_sys_user_org_user_id_org_id", "user_id", "org_id", unique=True),
        {'comment': '用户可访问的组织：一行为一个用户被授权访问的一个组织。用户除主组织外还能访问的组织（如集团管理人员访问多个校区）。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    user_id: UUID = Field(foreign_key="sys_user.id", nullable=False, sa_column_kwargs={'comment': '用户'})
    access_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '授权类型；字典 sys_user_org_access_type'})
    is_primary: bool = bool_field('是否主组织', default=False)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class SysUserPosition(SQLModel, table=True):
    """账号岗位：一行为一个租户账号直接选择的一个岗位，不代表雇佣档案。"""
    __tablename__ = "sys_user_position"
    __table_args__ = (
        Index("uk_sys_user_position_user_id_position_id", "user_id", "position_id", unique=True,
              postgresql_where=text("deleted_at is null and valid_to is null")),
        {"comment": "账号岗位：一行为一个租户账号直接选择的一个岗位；用于岗位知识资格，不创建雇佣或改变主部门。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", nullable=False,
                         sa_column_kwargs={"comment": "租户账号；引用 sys_user.id"})
    position_id: UUID = Field(foreign_key="sys_position.id", ondelete="RESTRICT", nullable=False,
                             sa_column_kwargs={"comment": "所选岗位；引用 sys_position.id"})
    valid_from: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True), nullable=False,
        sa_column_kwargs={"server_default": text("now()"), "comment": "生效时间；保存账号岗位时起效，左闭"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "失效时间；移除岗位时结束关系，右开，空值表示持续有效"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
