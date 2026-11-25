"""表模型（sys_role_permission）。

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


class SysRolePermission(SQLModel, table=True):
    """角色权限：一行为一个角色拥有的一个权限。"""

    __tablename__ = "sys_role_permission"
    __table_args__ = (
        Index("uk_sys_role_permission_role_id_permission_id", "role_id", "permission_id", unique=True),
        {'comment': '角色权限：一行为一个角色拥有的一个权限。'},
    )

    id: UUID = id_field()
    role_id: UUID = Field(foreign_key="sys_role.id", nullable=False, sa_column_kwargs={'comment': '角色'})
    permission_id: UUID = Field(foreign_key="sys_permission.id", index=True, nullable=False, sa_column_kwargs={'comment': '权限'})
    data_scope_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '数据范围；字典 sys_data_scope；为空时取角色的数据范围'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
