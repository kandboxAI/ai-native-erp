"""部门岗位（L1）表模型：sys_position。

任职（员工 × 部门 × 岗位）属于 L2 人事（hr_position_assignment），L1 通过汇报线提供器使用（见 reporting.py）。
设计见 docs/foundation-platform/hr-employee-design.md §4.1。
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
    org_field,
    updated_at_field,
)


class SysPosition(SQLModel, table=True):
    """岗位：一行为部门中的一类岗位，可由多人任职（如教务处处长）。"""

    __tablename__ = "sys_position"
    __table_args__ = (
        Index("uk_sys_position_org_id_position_no", "org_id", "position_no", unique=True, postgresql_where=text("deleted_at is null")),
        Index(
            "uk_sys_position_department_head", "department_id", unique=True,
            postgresql_where=text("is_department_head and deleted_at is null"),
        ),
        {'comment': '岗位：一行为部门中的一类岗位，可由多人任职。上级岗位构成汇报线（不能成环）；同一部门最多一个负责人岗位。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    position_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '岗位编号'})
    position_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '岗位名称'})
    department_id: UUID = Field(foreign_key="sys_department.id", index=True, nullable=False, sa_column_kwargs={'comment': '所属部门'})
    parent_position_id: UUID | None = Field(default=None, foreign_key="sys_position.id", index=True, nullable=True, sa_column_kwargs={'comment': '上级岗位；汇报线'})
    is_department_head: bool = bool_field('是否负责人岗位；在任者即部门负责人', default=False)
    headcount: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '编制人数；为空表示不限'})
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field()


__all__ = ["SysPosition"]
