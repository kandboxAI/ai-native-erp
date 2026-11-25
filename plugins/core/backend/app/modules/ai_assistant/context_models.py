"""AI 个人偏好与岗位模板；岗位事实仍由所属业务模块提供。"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field, bool_field, created_at_field, flex_form_field,
    id_field, org_field, updated_at_field,
)


class AiUserPreference(SQLModel, table=True):
    __tablename__ = "ai_user_preference"
    __table_args__ = (
        Index("uk_ai_user_preference_user_id", "user_id", unique=True),
        {"comment": "AI 个人偏好：一行为当前租户一位用户的回答偏好，不作为身份或授权依据。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    user_id: UUID = Field(foreign_key="sys_user.id", nullable=False, sa_column_kwargs={"comment": "所属租户用户；仅本人维护"})
    instructions: str = Field(default="", sa_type=Text, sa_column_kwargs={"comment": "个人回答偏好；敏感：个人；注入前经过统一字段值保护"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field()


class AiPromptTemplate(SQLModel, table=True):
    __tablename__ = "ai_prompt_template"
    __table_args__ = ({"comment": "AI 岗位提示模板：一行为一个组织的通用、角色、岗位或业务身份模板；停用保留记录。"},)
    id: UUID = id_field()
    org_id: UUID = org_field()
    template_name: str = Field(max_length=128, sa_column_kwargs={"comment": "模板名称"})
    role_id: UUID | None = Field(default=None, foreign_key="sys_role.id", sa_column_kwargs={"comment": "匹配的角色；与岗位、业务身份互斥；不授予权限"})
    position_id: UUID | None = Field(default=None, foreign_key="sys_position.id", sa_column_kwargs={"comment": "匹配的岗位；与角色、业务身份互斥"})
    context_key: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "业务提供器声明的身份标识；与角色、岗位互斥；全部为空表示组织通用模板"})
    instructions: str = Field(sa_type=Text, sa_column_kwargs={"comment": "岗位指导正文；仅支持白名单占位符；注入前经过统一字段值保护"})
    is_active: bool = bool_field("是否启用", default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field()


class AiUserTemplatePreference(SQLModel, table=True):
    """没有个人记录时默认启用；每位用户独立选择，不修改角色授权。"""

    __tablename__ = "ai_user_template_preference"
    __table_args__ = (
        Index("uk_ai_user_template_preference_user_id_template_id", "user_id", "template_id", unique=True),
        {"comment": "AI 个人角色模板偏好：一行为一位租户用户对一份角色模板的启停选择；无记录默认启用。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="CASCADE", nullable=False,
                          sa_column_kwargs={"comment": "所属租户用户；引用 sys_user；仅本人维护；敏感：个人"})
    template_id: UUID = Field(foreign_key="ai_prompt_template.id", ondelete="CASCADE", index=True, nullable=False,
                              sa_column_kwargs={"comment": "选择的角色模板；引用 ai_prompt_template；不授予角色或权限"})
    is_active: bool = bool_field("本人是否启用该角色模板；仍须满足实际角色及管理员启用条件", default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    flex_form: dict[str, Any] = flex_form_field()
