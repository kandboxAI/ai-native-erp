"""自动排程正式方案、输入配置和执行批次；预测与实际质量事实分别保存。"""
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import conv
from sqlmodel import Field
from app.framework.db.models import audit_user_field
from .archive_models import ArchiveFields


class MesOperationScheduleSetting(ArchiveFields, table=True):
    __tablename__ = "mes_operation_schedule_setting"
    __table_args__ = (
        Index("uk_mes_operation_schedule_setting_operation", "operation_id", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("setup_minutes >= 0 AND load_minutes >= 0 AND unload_minutes >= 0", name=conv("ck_mes_operation_schedule_setting_minutes")),
        {"comment": "工单工序排程参数；一行保存工程明确确认的执行方式及阶段用时，不回写标准单件分钟口径。"},
    )
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属工单工序；同组织，一对一扩展"})
    execution_kind_code: str = Field(max_length=64, sa_column_kwargs={"comment": "执行方式；字典 mes_schedule_execution_kind"})
    setup_minutes: int = Field(sa_column_kwargs={"comment": "一次性准备分钟；工程确认未包含在单件工时中"})
    load_minutes: int = Field(sa_column_kwargs={"comment": "逐件装料分钟；没有该动作时明确填零"})
    unload_minutes: int = Field(sa_column_kwargs={"comment": "逐件卸料分钟；没有该动作时明确填零"})
    can_supervise_two_machines: bool = Field(default=False, sa_column_kwargs={"comment": "是否明确允许自动运行时一人照看两机；人工操作仍独占"})
    can_run_during_lunch: bool = Field(default=False, sa_column_kwargs={"comment": "是否明确允许机器跨人员午休自动运行；不等于夜间无人运行"})
    is_timing_confirmed: bool = Field(default=False, sa_column_kwargs={"comment": "工程是否确认标准工时为净单件耗时、准备装卸未重复计算"})
    source_version_no_snapshot: int = Field(sa_column_kwargs={"comment": "确认时的工序修订号；工序修改后须重新确认"})
    external_first_return_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "首件委外预计回厂时间；未知为空，不推断为交期"})
    external_remaining_return_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "剩余整批委外预计回厂时间；回厂后仍须检验"})
    inspection_process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本工序独立放行或委外回厂检验工艺；无独立检验时为空"})
    inspection_minutes_per_piece: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本工序独立检验单件分钟；工程确认，不包含在加工时间中"})
    is_inspection_equipment_required: bool = Field(default=False, sa_column_kwargs={"comment": "本工序独立检验是否占用匹配检验设备"})


class MesWorkOrderReadiness(ArchiveFields, table=True):
    __tablename__ = "mes_work_order_readiness"
    __table_args__ = (
        Index("uk_mes_work_order_readiness_order_kind", "work_order_id", "readiness_kind_code", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "工单开工就绪条件；一行代表材料、图纸、程序或刀具之一的预计时间与人工实际确认，不以预计到时自动放行。"},
    )
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属生产工单"})
    readiness_kind_code: str = Field(max_length=64, sa_column_kwargs={"comment": "就绪类型；字典 mes_schedule_readiness_kind"})
    expected_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "预计就绪时刻；试排可以使用未来时间"})
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "实际就绪确认时刻；服务端记录，不按预计时间自动填写"})
    confirmed_by: UUID | None = audit_user_field("实际就绪确认人", ondelete="SET NULL")


class MesWorkOrderInspectionSetting(ArchiveFields, table=True):
    __tablename__ = "mes_work_order_inspection_setting"
    __table_args__ = (
        Index("uk_mes_work_order_inspection_setting_order", "work_order_id", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("minutes_per_piece IS NULL OR minutes_per_piece > 0", name=conv("ck_mes_work_order_inspection_setting_minutes")),
        {"comment": "工单首件与最终检验安排；选择复用末道检验或路线外独立检验，不保存实际合格结论。"},
    )
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属生产工单"})
    inspection_mode_code: str = Field(max_length=64, sa_column_kwargs={"comment": "检验安排；字典 mes_schedule_inspection_mode"})
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "独立检验采用的工艺；复用末道时为空"})
    is_equipment_required: bool = Field(default=False, sa_column_kwargs={"comment": "独立检验是否需要匹配设备，如三坐标"})
    minutes_per_piece: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "独立检验单件分钟；复用末道时不额外计时"})


class MesSchedulePlan(ArchiveFields, table=True):
    __tablename__ = "mes_schedule_plan"
    __table_args__ = (
        Index("uk_mes_schedule_plan_org_no", "org_id", "plan_no", unique=True),
        CheckConstraint("window_end_at > window_start_at", name=conv("ck_mes_schedule_plan_window")),
        {"comment": "自动排程正式方案；一行代表一次固定输入的计算及确认记录，只有已应用的阶段占用正式资源。"},
    )
    plan_no: str = Field(max_length=64, sa_column_kwargs={"comment": "组织内方案编号"})
    plan_name: str = Field(max_length=128, sa_column_kwargs={"comment": "方案名称"})
    window_start_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "排程窗口开始"})
    window_end_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "排程窗口结束"})
    status_code: str = Field(max_length=64, sa_column_kwargs={"comment": "方案状态；字典 mes_schedule_plan_status"})
    solver_result_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "求解结果；字典 mes_schedule_solver_result"})
    input_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "工单、人员、设备、资格、日历及占用资料的输入摘要；确认时重算"})
    input_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, sa_column_kwargs={"comment": "按正式排程协议校验的输入、配置及版本快照；仅供授权复算，不作为关联源、不进入AI"})
    result_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB, sa_column_kwargs={"comment": "求解状态、目标指标和提示的结构化快照；正式资源关系保存在明细表"})
    solver_version: str = Field(max_length=64, sa_column_kwargs={"comment": "OR-Tools及本项目模型版本"})
    time_limit_seconds: int = Field(sa_column_kwargs={"comment": "本次共享求解时间预算；秒"})
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "正式应用时间"})
    confirmed_by: UUID | None = audit_user_field("正式应用人", ondelete="SET NULL")
    supersedes_plan_id: UUID | None = Field(default=None, foreign_key="mes_schedule_plan.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "替代的未执行方案；旧方案历史保留，不覆盖"})


class MesSchedulePlanOperation(ArchiveFields, table=True):
    __tablename__ = "mes_schedule_plan_operation"
    __table_args__ = (
        Index("uk_mes_schedule_plan_operation_plan_operation", "plan_id", "operation_id", unique=True),
        {"comment": "排程方案工序；一行代表某方案中的一道真实工单工序，跨首件与剩余批量的总跨度不作为连续资源占用。"},
    )
    plan_id: UUID = Field(foreign_key="mes_schedule_plan.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属排程方案"})
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "参与安排的真实工单工序"})
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "父工单；用于完整路线及应用范围核对"})
    operation_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "计算时工序名称快照；历史展示不随源工序重命名"})
    work_order_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "计算时货品工单编号快照"})
    planned_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "计算时交付数量快照；首件计入其中"})
    production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本工序加工人员；独立检验人员保存在阶段明细"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本工序加工设备；人工为空"})
    planned_start_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "各阶段最早开始；失败时为空"})
    planned_end_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "各阶段最晚结束；不能作为连续占用或整批转序约束"})
    duration_minutes_snapshot: int | None = Field(default=None, sa_column_kwargs={"comment": "非等待阶段分钟合计快照；非实际工时"})
    source_version_no_snapshot: int = Field(sa_column_kwargs={"comment": "计算时的源工序修订号"})
    applied_version_no_snapshot: int | None = Field(default=None, sa_column_kwargs={"comment": "应用写回计划后的工序修订号，重排及执行据此核对"})
    is_scheduled: bool = Field(default=False, sa_column_kwargs={"comment": "本次是否完整安排成功"})
    unscheduled_reason: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "未安排原因；失败不写虚构资源或时间"})


class MesSchedulePlanSegment(ArchiveFields, table=True):
    __tablename__ = "mes_schedule_plan_segment"
    __table_args__ = (
        Index("uk_mes_schedule_plan_segment_operation_sequence", "plan_operation_id", "sequence_no", unique=True),
        CheckConstraint("planned_end_at > planned_start_at", name=conv("ck_mes_schedule_plan_segment_period")),
        CheckConstraint("person_capacity_units_snapshot >= 0 AND person_capacity_units_snapshot <= 2", name=conv("ck_mes_schedule_plan_segment_capacity")),
        {"comment": "排程方案阶段；一行代表首件或剩余批量的一次加工、人工、检验或等待，应用后按阶段保留人机占用。"},
    )
    plan_operation_id: UUID = Field(foreign_key="mes_schedule_plan_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属方案工序"})
    sequence_no: int = Field(sa_column_kwargs={"comment": "本方案工序内阶段序号"})
    production_phase_code: str = Field(max_length=64, sa_column_kwargs={"comment": "生产批次；字典 mes_schedule_production_phase"})
    piece_no: int = Field(default=0, sa_column_kwargs={"comment": "该批次内的件次；共享准备为0，不代表新增订单数量"})
    quantity_snapshot: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本阶段计量数量快照；逐件阶段为1、准备为空，不作为实际报工"})
    segment_type_code: str = Field(max_length=64, sa_column_kwargs={"comment": "阶段类型；字典 mes_schedule_segment_type"})
    process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本阶段要求的工艺资格；独立检验使用检验工艺"})
    production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本阶段责任人员；占机等待无人员时为空"})
    person_no_snapshot: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "计算时生产人员编号快照；不保存姓名到求解结果"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本阶段占用的设备；待卸料时继续保留"})
    equipment_name_snapshot: str | None = Field(default=None, max_length=256, sa_column_kwargs={"comment": "计算时设备编号与名称快照"})
    planned_start_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "阶段开始；左闭端"})
    planned_end_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "阶段结束；右开端"})
    duration_minutes_snapshot: int = Field(sa_column_kwargs={"comment": "本阶段跨度分钟；等待与加工分别记录"})
    person_capacity_units_snapshot: int = Field(sa_column_kwargs={"comment": "人员容量需求；照看1、专注2、无人员0，总容量2"})
    is_equipment_occupied: bool = Field(default=False, sa_column_kwargs={"comment": "是否保留设备；等待卸料为真"})
    is_independent_inspection: bool = Field(default=False, sa_column_kwargs={"comment": "是否为路线外全路线检验，避免与原工序加工/检验混淆"})


class MesOperationProductionPhase(ArchiveFields, table=True):
    __tablename__ = "mes_operation_production_phase"
    __table_args__ = (
        Index("uk_mes_operation_production_phase_operation_phase", "operation_id", "production_phase_code", unique=True,
            postgresql_where=text("deleted_at is null")),
        CheckConstraint("planned_quantity > 0", name=conv("ck_mes_operation_production_phase_quantity")),
        {"comment": "工序实际生产批次；一行代表工序的首件或剩余批量执行状态，数量独立受控，累计报工仍由原生产报工记录归属。"},
    )
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属货品工单"})
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属真实工序"})
    plan_operation_id: UUID = Field(foreign_key="mes_schedule_plan_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本批次当前正式方案工序；重排保留原方案历史"})
    production_phase_code: str = Field(max_length=64, sa_column_kwargs={"comment": "生产批次；字典 mes_schedule_production_phase"})
    planned_quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本批次数量；首件1，剩余交付数量减1"})
    status_code: str = Field(default="pending", max_length=64, sa_column_kwargs={"comment": "执行状态；字典 mes_operation_task_status"})
    is_rework: bool = Field(default=False, sa_column_kwargs={"comment": "是否返工复作；保留原数量，不因再次执行重复增加产量"})


class MesWorkOrderFirstArticle(ArchiveFields, table=True):
    __tablename__ = "mes_work_order_first_article"
    __table_args__ = (
        Index("uk_mes_work_order_first_article_order", "work_order_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "工单全路线首件准入；一行记录首件流转和质量实际放行，方案预计通过不能替代本事实。"},
    )
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属生产工单"})
    status_code: str = Field(default="pending", max_length=64, sa_column_kwargs={"comment": "首件状态；字典 mes_first_article_status"})
    last_inspection_id: UUID | None = Field(default=None, foreign_key="mes_quality_inspection.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "最近一次真实首件检验事实；未检验为空"})
    released_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "真实全路线首件合格放行时间"})
    released_by: UUID | None = audit_user_field("首件放行人", ondelete="SET NULL")
