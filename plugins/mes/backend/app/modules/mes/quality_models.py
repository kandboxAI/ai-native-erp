"""工序检验追加事实；整道工序放行/返工，不覆盖报工及历史检验。"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Index, Numeric, Text
from sqlmodel import Field, SQLModel
from app.framework.db.models import id_field, org_field, audit_user_field, created_at_field, flex_form_field


class MesQualityInspection(SQLModel, table=True):
    __tablename__ = "mes_quality_inspection"
    __table_args__ = (
        Index("uk_mes_quality_inspection_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        Index("uk_mes_quality_inspection_operation_id_version", "operation_id", "operation_version_snapshot", unique=True),
        Index("idx_mes_quality_inspection_operation_id_created_at", "operation_id", "created_at"),
        CheckConstraint("reported_good_quantity_snapshot >= 0 AND reported_scrap_quantity_snapshot >= 0 AND reported_rework_quantity_snapshot >= 0", name="ck_mes_quality_inspection_nonnegative_quantities"),
        {"comment": "MES 工序检验记录；一行代表对整道工序当前报工累计的一次合格放行或退回返工，只追加不修改。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "被检验工序；通过工序关联工单和产品"})
    production_phase_id: UUID | None = Field(default=None, foreign_key="mes_operation_production_phase.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际首件或剩余批量；原整工序检验为空"})
    inspection_type_code: str = Field(default="operation", max_length=64, sa_column_kwargs={"server_default": "operation", "comment": "检验类型；字典 mes_quality_inspection_type；首件、工序、最终或委外回厂，不是计划预测"})
    inspection_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际检验人员身份；可由有管理权限的登录用户代录，与提交人分开"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际检验使用设备；纯人工检验为空"})
    execution_id: UUID = Field(foreign_key="mes_operation_execution.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "提交检验时最近一个已结束的执行区间；返工须重新开工并结束后复检"})
    operation_version_snapshot: int = Field(sa_column_kwargs={"comment": "检验前工序修订号快照；一次修订只能处置一次"})
    result_code: str = Field(max_length=64, sa_column_kwargs={"comment": "检验结论；字典 mes_quality_result；本期 pass 为合格、fail 为不合格退回原工序返工"})
    to_status_code: str = Field(max_length=64, sa_column_kwargs={"comment": "处置后工序状态；字典 mes_operation_task_status"})
    reported_good_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "检验时操作员累计申报合格数量快照；单位同 unit_code_snapshot，不重复计产"})
    reported_scrap_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "检验时累计报废数量快照；不通过本检验重分类，单位同 unit_code_snapshot"})
    reported_rework_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "检验时累计申报返工数量快照；不通过本检验重分类，单位同 unit_code_snapshot"})
    unit_code_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "检验时数量基本单位快照；字典 md_unit"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "检验说明或不合格原因；退回返工必填，自由文本默认不进入 AI"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "本次检验提交幂等键；按提交人唯一，不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("检验人；租户用户，服务端按当前用户记录", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()
