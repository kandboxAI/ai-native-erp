"""表模型（sys_dict_item）。

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


class SysDictItem(SQLModel, table=True):
    """字典项：一行为字典中的一个取值。"""

    __tablename__ = "sys_dict_item"
    __table_args__ = (
        Index("uk_sys_dict_item_dict_id_item_code", "dict_id", "item_code", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '字典项：一行为字典中的一个取值。业务表 `_code` 字段存的就是 `item_code`。内置项由平台定义，学校自己增加的项 `is_builtin` 为否。'},
    )

    id: UUID = id_field()
    dict_id: UUID = Field(foreign_key="sys_dict.id", nullable=False, sa_column_kwargs={'comment': '所属字典'})
    item_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '取值编码；小写英文，业务表中保存的值'})
    item_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '取值名称；界面显示的中文'})
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    is_builtin: bool = bool_field('是否内置；平台定义的内置项不可删除，只能停用', default=False)
    is_active: bool = bool_field('是否启用', default=True)
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
