from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    id_field, org_field, audit_user_field, created_at_field, updated_at_field, flex_form_field, utc_now,
)


class SysTodo(SQLModel, table=True):
    __tablename__ = "sys_todo"
    __table_args__ = (
        Index("uk_sys_todo_dedup_key", "dedup_key", unique=True),
        {"comment": "通用待办：一行代表一个业务对象的一轮办理事项。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    todo_type_key: str = Field(max_length=128, sa_column_kwargs={"comment": "代码登记的待办类型；与来源共同确定业务读取和办理契约"})
    source_id: UUID = Field(sa_column_kwargs={"comment": "来源对象；多态引用由 todo_type_key 对应处理器定义，不能声明统一外键"})
    dedup_key: str = Field(max_length=256, sa_column_kwargs={"comment": "业务办理轮次幂等键；重试不得重复创建"})
    title: str = Field(max_length=256, sa_column_kwargs={"comment": "待办标题；个人信息默认不向 AI 发布"})
    summary: str = Field(default="", sa_type=Text, sa_column_kwargs={"comment": "展示摘要；自由文本默认不向 AI 发布"})
    status_code: str = Field(default="pending", max_length=32, sa_column_kwargs={"comment": "状态；字典 sys_todo_status"})
    priority_code: str = Field(default="normal", max_length=32, sa_column_kwargs={"comment": "优先级；字典 sys_todo_priority"})
    arrived_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "待办到达时间"})
    due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "办理截止时间；为空表示未设置"})
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "整项完成时间"})
    completed_by: UUID | None = audit_user_field("整项完成人；自动关闭时为空", ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class SysTodoAssignee(SQLModel, table=True):
    __tablename__ = "sys_todo_assignee"
    __table_args__ = (
        Index("uk_sys_todo_assignee_todo_id_user_id", "todo_id", "user_id", unique=True),
        Index("idx_sys_todo_assignee_user_id_status_code", "user_id", "status_code"),
        {"comment": "待办分配：一行代表一项待办的一名具体办理人及其处理状态。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    todo_id: UUID = Field(foreign_key="sys_todo.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "待办；引用 sys_todo.id"})
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "具体办理人；引用 sys_user.id"})
    status_code: str = Field(default="pending", max_length=32, sa_column_kwargs={"comment": "个人状态；字典 sys_todo_assignee_status"})
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "首次查看时间；查看不代表办理"})
    handled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "本人办理时间"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("分配创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()
