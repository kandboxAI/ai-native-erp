"""表模型（sys_org）。

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


class SysOrg(SQLModel, table=True):
    """组织：一行为组织树中的一个节点（集团、学校或校区）。"""

    __tablename__ = "sys_org"
    __table_args__ = (
        Index("uk_sys_org_org_no", "org_no", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '组织：一行为组织树中的一个节点（集团、学校或校区）。本租户内部的组织架构。教学数据的 `org_id` 指向校区；只有一个校区的学校，校区即学校本身。'},
    )

    id: UUID = id_field()
    org_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '组织编号'})
    org_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '组织名称'})
    org_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '组织类型；字典 sys_org_type'})
    parent_id: UUID | None = Field(default=None, foreign_key="sys_org.id", index=True, nullable=True, sa_column_kwargs={'comment': '上级组织'})
    contact_name: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '联系人；敏感：个人'})
    contact_phone: str | None = Field(default=None, max_length=32, nullable=True, sa_column_kwargs={'comment': '联系电话；敏感：个人'})
    province: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '省'})
    city: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '市'})
    district: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '区县'})
    address: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '详细地址'})
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    is_active: bool = bool_field('是否启用', default=True)
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
