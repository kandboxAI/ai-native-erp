"""表模型（sys_user_role）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class SysUserRole(SQLModel, table=True):
    """用户角色：一行为一个用户拥有的一个角色。"""

    __tablename__ = "sys_user_role"
    __table_args__ = (
        Index("uk_sys_user_role_user_id_role_id", "user_id", "role_id", unique=True),
        {'comment': '用户角色：一行为一个用户拥有的一个角色。'},
    )

    id: UUID = id_field()
    user_id: UUID = Field(foreign_key="sys_user.id", nullable=False, sa_column_kwargs={'comment': '用户'})
    role_id: UUID = Field(foreign_key="sys_role.id", index=True, nullable=False, sa_column_kwargs={'comment': '角色'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
