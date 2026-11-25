"""表模型（sys_role）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class SysRole(SQLModel, table=True):
    """角色：一行为一个角色。"""

    __tablename__ = "sys_role"
    __table_args__ = (
        Index("uk_sys_role_role_no", "role_no", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '角色：一行为一个角色。角色是学校配置的权限与数据范围组合。代码不按角色名判断；内置管理员角色以 `is_builtin` 防止删除，数据范围为全部、拥有全部权限。'},
    )

    id: UUID = id_field()
    role_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '角色编号'})
    role_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '角色名称'})
    description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    data_scope_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '数据范围；字典 sys_data_scope'})
    is_builtin: bool = bool_field('是否内置；内置角色不可删除', default=False)
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
