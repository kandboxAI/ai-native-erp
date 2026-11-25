"""制造异常及其追加处理事实；不代替生产、质量和库存状态机。"""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, Index, Text, text
from sqlmodel import SQLModel, Field
from app.framework.db.models import id_field, org_field, audit_user_field, created_at_field, updated_at_field, deleted_at_field, flex_form_field


class MesExceptionCase(SQLModel, table=True):
    __tablename__ = "mes_exception_case"
    __table_args__ = (
        Index("uk_mes_exception_case_org_id_case_no", "org_id", "case_no", unique=True),
        Index("uk_mes_exception_case_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        Index("idx_mes_exception_case_work_order_id", "work_order_id"),
        Index("idx_mes_exception_case_assigned_user_id", "assigned_user_id"),
        Index("idx_mes_exception_case_status_code_due_at", "status_code", "due_at"),
        {"comment":"MES 异常单；一行代表一个工单或工序需专人处理并复核的异常，不自动改变生产状态。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    case_no: str = Field(max_length=48, sa_column_kwargs={"comment":"异常单编号；组织内唯一"})
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment":"来源工单；与异常所属组织一致"})
    operation_id: UUID | None = Field(default=None, foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment":"可选来源工序；必须属于来源工单"})
    title: str = Field(max_length=128, sa_column_kwargs={"comment":"异常标题；业务自由文本，不自动进入 AI"})
    description: str = Field(sa_type=Text, sa_column_kwargs={"comment":"异常现象说明；业务自由文本，不自动进入 AI"})
    exception_type_code: str = Field(max_length=64, sa_column_kwargs={"comment":"异常类型；字典 mes_exception_type"})
    status_code: str = Field(default="pending", max_length=64, sa_column_kwargs={"server_default":text("'pending'"), "comment":"异常状态；字典 mes_exception_status"})
    assigned_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment":"当前责任人；同组织活动租户用户"})
    due_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment":"要求处理或复核完成的期限；带时区时间点"})
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment":"最近一次提交处理结果时间；退回或重开后清空"})
    resolved_by: UUID | None = audit_user_field("最近一次提交处理结果人；退回或重开后清空", ondelete="RESTRICT")
    closed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment":"复核关闭时间；重开后清空"})
    closed_by: UUID | None = audit_user_field("复核关闭人；不能是本轮处理结果提交人", ondelete="RESTRICT")
    last_reminded_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment":"最近一次成功超时提醒时间；改派、延期、待复核或重开时重置"})
    version_no: int = Field(default=1, sa_column_kwargs={"server_default":text("1"), "comment":"异常单修订号；乐观锁"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment":"登记幂等键；同一提交人重试复用"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment":"登记请求 SHA256；重复幂等键须匹配原内容"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("异常提出人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("最近处理人；提醒任务为空", ondelete="RESTRICT")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间配对，本版不提供删除动作", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesExceptionEvent(SQLModel, table=True):
    __tablename__ = "mes_exception_event"
    __table_args__ = (Index("idx_mes_exception_event_case_id_created_at", "case_id", "created_at"),
        {"comment":"MES 异常处理流水；一行代表登记、指派、处理、复核或提醒的一次追加事实，不修改历史。"})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    case_id: UUID = Field(foreign_key="mes_exception_case.id", ondelete="RESTRICT", sa_column_kwargs={"comment":"所属异常单"})
    action_code: str = Field(max_length=64, sa_column_kwargs={"comment":"处理动作；字典 mes_exception_action"})
    from_status_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment":"动作前状态；字典 mes_exception_status；登记为空"})
    to_status_code: str = Field(max_length=64, sa_column_kwargs={"comment":"动作后状态；字典 mes_exception_status"})
    note: str = Field(sa_type=Text, sa_column_kwargs={"comment":"处理说明或结果；业务自由文本，不自动进入 AI"})
    assigned_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment":"该动作时的责任人；历史事实，不随改派变化"})
    due_at_snapshot: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment":"该动作时的处理期限快照"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("动作人；系统提醒为空", ondelete="RESTRICT")
    flex_form: dict = flex_form_field("追加业务流水扩展；默认 {}")
