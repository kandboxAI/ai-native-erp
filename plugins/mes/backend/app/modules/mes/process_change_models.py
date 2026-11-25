from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field, created_at_field, flex_form_field, id_field, org_field, updated_at_field,
)


class MesWorkOrderProcessChange(SQLModel, table=True):
    __tablename__ = "mes_work_order_process_change"
    __table_args__ = (
        Index("uk_mes_work_order_process_change_open", "work_order_id", unique=True,
              postgresql_where=text("status_code IN ('submitted', 'approved')")),
        {"comment": "MES 工艺变更单；一行表示一次工序工艺切换以及原工艺已加工件的处置。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", index=True,
                               sa_column_kwargs={"comment": "需要继续生产的原工单"})
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", index=True,
                               sa_column_kwargs={"comment": "变更目标工序；工序执行及报工仍引用此任务"})
    previous_process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT",
                                            sa_column_kwargs={"comment": "变更前选用工艺；历史手工工序为空"})
    new_process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT",
                                 sa_column_kwargs={"comment": "审批后用于剩余生产的新工艺"})
    new_equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT",
                                          sa_column_kwargs={"comment": "审批后供剩余生产使用的生产设备；无须指定设备时可空"})
    previous_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "变更前工序名称快照"})
    new_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "提交变更时的新工艺名称快照"})
    new_process_version_snapshot: int = Field(sa_column_kwargs={"comment": "提交时的新工艺档案版本；生效时重新核对"})
    previous_configuration_snapshot: dict = Field(sa_type=JSONB,
        sa_column_kwargs={"comment": "变更前配置快照；含设备、检验要求、工位、说明、派工人和工时；默认不发布给 AI"})
    remaining_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3),
                                                  sa_column_kwargs={"comment": "尚未报工的数量；采用原工单单位"})
    disposition_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3),
                                                    sa_column_kwargs={"comment": "本次处置的已报合格数量；采用原工单单位"})
    disposition_code: str = Field(max_length=32, sa_column_kwargs={"comment": "已加工件处置方式；字典 mes_process_change_disposition"})
    status_code: str = Field(default="draft", max_length=32, sa_column_kwargs={"comment": "变更单状态；字典 mes_process_change_status"})
    previous_order_status_code: str = Field(max_length=64, sa_column_kwargs={"comment": "原工单在变更冻结前的状态；字典 mes_work_order_status"})
    reason: str = Field(sa_type=Text, sa_column_kwargs={"comment": "变更原因；自由文本不进入 AI"})
    disposition_note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "实际处置结果或复检依据；自由文本不进入 AI"})
    disposition_by: UUID | None = audit_user_field("确认处置的租户用户")
    repair_order_id: UUID | None = Field(default=None, foreign_key="mes_work_order.id", ondelete="RESTRICT", index=True,
                                         sa_column_kwargs={"comment": "本变更安排的独立返修工单；返工时填写"})
    wf_instance_id: UUID | None = Field(default=None, foreign_key="wf_instance.id", ondelete="RESTRICT",
                                        sa_column_kwargs={"comment": "底座工艺变更审批实例"})
    applied_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True),
                                       sa_column_kwargs={"comment": "变更实际生效时间；为空表示未切换"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("提出变更的租户用户")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("最后修改变更单的租户用户")
    flex_form: dict = flex_form_field()
