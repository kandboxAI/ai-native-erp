"""表模型（sys_setting）。

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


class SysSetting(SQLModel, table=True):
    """系统参数：一行为一个系统参数。"""

    __tablename__ = "sys_setting"
    __table_args__ = (
        Index("uk_sys_setting_setting_key", "setting_key", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '系统参数：一行为一个系统参数。代码读取的系统参数，`setting_key` 由代码定义，创建后不可修改。'},
    )

    id: UUID = id_field()
    setting_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '参数标识；代码中引用，如 password_min_length'})
    setting_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '参数名称'})
    setting_value: str | None = Field(default=None, max_length=2048, nullable=True, sa_column_kwargs={'comment': '参数值'})
    value_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '值类型；字典 sys_value_type'})
    setting_group_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '参数分组；字典 sys_setting_group'})
    description: str | None = Field(default=None, max_length=512, nullable=True, sa_column_kwargs={'comment': '说明'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
