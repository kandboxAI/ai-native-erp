"""表模型（sys_department）。

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
    org_field,
    updated_at_field,
)


class SysDepartment(SQLModel, table=True):
    """部门：一行为一个部门（如教务科、学生科、教研组）。"""

    __tablename__ = "sys_department"
    __table_args__ = (
        Index("uk_sys_department_org_id_department_no", "org_id", "department_no", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '部门：一行为一个部门（如教务科、学生科、教研组）。部门树；负责人引用租户内用户。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    department_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '部门编号'})
    department_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '部门名称'})
    parent_id: UUID | None = Field(default=None, foreign_key="sys_department.id", index=True, nullable=True, sa_column_kwargs={'comment': '上级部门'})
    manager_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '部门负责人'})
    supervisor_party_id: UUID | None = Field(default=None, foreign_key="md_person.party_id", index=True, nullable=True, sa_column_kwargs={'comment': '分管领导；全系统唯一的分管领导来源'})
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
