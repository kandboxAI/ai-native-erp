"""表模型（sys_permission）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index, text
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


class SysPermission(SQLModel, table=True):
    """权限：一行为一个功能权限点。"""

    __tablename__ = "sys_permission"
    __table_args__ = (
        Index("uk_sys_permission_permission_key", "permission_key", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '权限：一行为一个功能权限点。权限由代码定义，开通租户时从模板生成；接口按 `permission_key` 校验。'},
    )

    id: UUID = id_field()
    permission_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '权限标识；如 leave:approve'})
    permission_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '权限名称'})
    module_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '所属模块；字典 sys_module'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
