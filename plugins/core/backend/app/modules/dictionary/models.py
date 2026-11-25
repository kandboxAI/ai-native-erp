"""表模型（sys_dict）。

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


class SysDict(SQLModel, table=True):
    """字典：一行为一个字典（如“请假类型”）。"""

    __tablename__ = "sys_dict"
    __table_args__ = (
        Index("uk_sys_dict_dict_code", "dict_code", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '字典：一行为一个字典（如“请假类型”）。每个租户 schema 一份完整字典。内置字典由平台定义，开通租户时生成、升级时同步。'},
    )

    id: UUID = id_field()
    dict_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '字典编码；如 edu_leave_type；字典表自身豁免“_code 引用字典”规则'})
    dict_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '字典名称'})
    description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    is_tenant_extensible: bool = bool_field('学校可否扩展；是否允许学校增加自己的字典项', default=True)
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
