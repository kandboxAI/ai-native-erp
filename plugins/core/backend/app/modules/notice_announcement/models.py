"""表模型（ntf_notice、ntf_notice_target、ntf_notice_read）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text
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


class NtfNotice(SQLModel, table=True):
    """公告：一行为一条通知公告。"""

    __tablename__ = "ntf_notice"
    __table_args__ = (
        {'comment': '公告：一行为一条通知公告。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    title: str = Field(max_length=256, nullable=False, sa_column_kwargs={'comment': '标题'})
    summary: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '内容'})
    notice_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '公告类型；字典 ntf_notice_type'})
    is_shown_on_home: bool = bool_field('是否在首页显示', default=False)
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 ntf_notice_status'})
    published_by: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '发布人'})
    publisher_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '发布人姓名；快照'})
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '发布时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfNoticeTarget(SQLModel, table=True):
    """公告接收范围：一行为一条公告的一个接收对象。"""

    __tablename__ = "ntf_notice_target"
    __table_args__ = (
        {'comment': '公告接收范围：一行为一条公告的一个接收对象。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    notice_id: UUID = Field(foreign_key="ntf_notice.id", index=True, nullable=False, sa_column_kwargs={'comment': '公告'})
    target_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '对象类型；字典 ntf_target_type'})
    role_id: UUID | None = Field(default=None, foreign_key="sys_role.id", index=True, nullable=True, sa_column_kwargs={'comment': '角色'})
    user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '用户'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfNoticeRead(SQLModel, table=True):
    """公告阅读记录：一行为一个用户阅读一条公告。"""

    __tablename__ = "ntf_notice_read"
    __table_args__ = (
        Index("uk_ntf_notice_read_notice_id_user_id", "notice_id", "user_id", unique=True),
        {'comment': '公告阅读记录：一行为一个用户阅读一条公告。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    notice_id: UUID = Field(foreign_key="ntf_notice.id", nullable=False, sa_column_kwargs={'comment': '公告'})
    user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '用户'})
    read_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '阅读时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
