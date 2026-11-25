"""MES P0 执行与现场报工模型。

产品、工艺版本、库存和文件分别由其所有者模块维护；本文件只保存 MES 的
工单执行事实和释放时快照，避免把制造语义塞进 md_item 或 inv 表。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)
from .delivery_models import MesShipment, MesShipmentLine, MesReconciliation, MesReconciliationLine
from .inventory_models import MesInventoryPosting
from .drawing_models import MesWorkOrderDrawingRevision, MesWorkOrderDrawingFile
from .external_import_models import MesExternalImportRow
from .workforce_models import MesProductionPerson, MesPersonProcess
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod


class MesProductionOrder(SQLModel, table=True):
    """生产项目：一行代表同一客户需求下的一组产品执行工单。"""

    __tablename__ = "mes_production_order"
    __table_args__ = (
        Index("uk_mes_production_order_org_id_production_order_no", "org_id", "production_order_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "MES 生产项目；统一客户需求和项目编号，产品及数量由所属执行工单维护。"},
    )
    id: UUID = id_field()
    source_sales_order_id: UUID | None = Field(default=None, foreign_key="mes_sales_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源客户订单；仅订单生产安排服务写入，手工项目为空"})
    org_id: UUID = org_field(ondelete="RESTRICT")
    production_order_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "生产项目编号；组织内唯一"})
    customer_id: UUID | None = Field(default=None, foreign_key="mes_customer.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用的客户档案；历史手填客户可为空"})
    project_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "项目名称"})
    source_product_count_snapshot: int | None = Field(default=None, sa_column_kwargs={"comment": "外部导入时原工单声明的货品款数；仅作来源完整性核对，不代替实际明细统计"})
    is_import_incomplete: bool = Field(default=False, sa_column_kwargs={"server_default": text("false"), "comment": "外部工单的货品明细是否未导全；不补造缺失货品"})
    customer_no_snapshot: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "客户外部编号快照；未对接客户主数据，无内部外键"})
    customer_name_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "客户名称快照；用户录入的外部客户名称，不作为内部主体关联；不进入 AI"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "项目备注；自由文本不进入 AI"})
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"server_default": text("1"), "comment": "项目版本号；乐观锁"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间成对")
    flex_form: dict[str, Any] = flex_form_field()


class MesWorkOrder(SQLModel, table=True):
    """生产工单：一行代表一张离散制造生产订单。"""

    __tablename__ = "mes_work_order"
    __table_args__ = (
        Index("uk_mes_work_order_org_id_work_order_no", "org_id", "work_order_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "MES 生产工单；保存产品、数量、状态和释放时的主数据快照。"},
    )

    id: UUID = id_field()
    source_sales_order_line_id: UUID | None = Field(default=None, foreign_key="mes_sales_order_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源成交货品；仅订单服务写入，数量和物料变更须重新安排"})
    org_id: UUID = org_field()
    production_order_id: UUID | None = Field(default=None, foreign_key="mes_production_order.id", index=True, ondelete="RESTRICT", sa_column_kwargs={"comment": "所属生产项目；历史独立工单为空，不回填虚构项目"})
    source_work_order_id: UUID | None = Field(default=None, foreign_key="mes_work_order.id", index=True, ondelete="RESTRICT", sa_column_kwargs={"comment": "返修来源工单；普通生产为空，返修事实独立记录"})
    process_template_id: UUID | None = Field(default=None, foreign_key="mes_process_template.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "应用的工序模板；仅作来源，执行使用本工单独立工序快照"})
    process_template_version_snapshot: int | None = Field(default=None, sa_column_kwargs={"comment": "应用时的模板修订号快照；模板更新不回写本工单"})
    order_type_code: str = Field(default="production", max_length=64, nullable=False, sa_column_kwargs={"server_default": text("'production'"), "comment": "工单类型；字典 mes_work_order_type"})
    processing_type_code: str = Field(default="in_house", max_length=64, nullable=False, sa_column_kwargs={"server_default": text("'in_house'"), "comment": "本产品执行工单的生产方式；字典 mes_processing_type；自制、委外或采购，类型标记不生成采购订单"})
    resume_status_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "工单暂停前状态；字典 mes_work_order_status；仅工单恢复使用"})
    is_process_change_pending: bool = Field(default=False, sa_column_kwargs={"server_default": text("false"), "comment": "工艺变更审批或处置期间冻结原工单"})
    is_process_change_repair: bool = Field(default=False, sa_column_kwargs={"server_default": text("false"), "comment": "工艺变更的返修工单；完工件返回原工单，不产生独立成品库存"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "工单说明；自由文本不进入 AI"})
    drawing_revision_label: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "本工单图纸版本标识；图纸由公共文件能力绑定，开始执行后冻结"})
    material_name_snapshot: str | None = Field(default=None, max_length=256, sa_column_kwargs={"comment": "本货品加工材料要求快照；外部导入或工程确认，不作为物料外键"})
    heat_treatment_snapshot: str | None = Field(default=None, max_length=256, sa_column_kwargs={"comment": "本货品热处理要求快照；自由文本不进入 AI"})
    surface_treatment_snapshot: str | None = Field(default=None, max_length=256, sa_column_kwargs={"comment": "本货品表面处理要求快照；自由文本不进入 AI"})
    process_requirement_snapshot: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "本货品工艺要求快照；不随档案修改，自由文本不进入 AI"})
    outsourced_due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "本货品外协预计回厂时间；未知为空，不推断为客户交期"})
    work_order_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "生产工单号；组织内唯一"})
    product_item_id: UUID = Field(foreign_key="md_item.id", index=True, nullable=False, sa_column_kwargs={"comment": "生产产品物料；引用 md_item"})
    product_item_no_snapshot: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "释放时产品物料编号快照"})
    product_item_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "释放时产品物料名称快照"})
    unit_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "生产计量单位；字典 md_unit"})
    planned_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "计划生产数量；单位见 unit_code"})
    good_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "累计合格数量"})
    scrap_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "累计报废数量"})
    rework_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "累计返工数量"})
    priority_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "优先级；字典 mes_priority"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "工单状态；字典 mes_work_order_status"})
    due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "交期"})
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"server_default": text("1"), "comment": "版本号；乐观锁"})
    released_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "释放时间"})
    released_by: UUID | None = audit_user_field("释放人")
    closed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "关闭时间"})
    closed_by: UUID | None = audit_user_field("关闭人")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；系统接口导入时可为空")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class MesWorkOrderOperation(SQLModel, table=True):
    """工序任务：一行代表一张工单的一道可执行工序。"""

    __tablename__ = "mes_work_order_operation"
    __table_args__ = (
        Index("uk_mes_work_order_operation_work_order_id_operation_no", "work_order_id", "operation_no", unique=True, postgresql_where=text("deleted_at is null")),
        Index("idx_mes_work_order_operation_assigned_production_person_id", "assigned_production_person_id"),
        CheckConstraint("(planned_start_at IS NULL AND planned_end_at IS NULL) OR (planned_start_at IS NOT NULL AND planned_end_at IS NOT NULL AND planned_end_at > planned_start_at)", name="ck_mes_work_order_operation_planned_period"),
        CheckConstraint("standard_minutes_per_unit IS NULL OR standard_minutes_per_unit > 0", name="ck_mes_work_order_operation_positive_standard_minutes"),
        {"comment": "MES 工单工序任务；是派工、Track-in、现场报工和 Track-out 的主对象。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", index=True, nullable=False, sa_column_kwargs={"comment": "所属生产工单"})
    operation_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "工序编号；工单内唯一"})
    operation_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "工序名称快照"})
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用工艺档案；名称和说明按提交时保存，不随档案变化"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用设备档案；工作站字段保存当时设备编号"})
    requirement_id: UUID | None = Field(default=None, foreign_key="mes_process_requirement.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用工艺要求；操作说明保存当时要求"})
    project_stage_id: UUID | None = Field(default=None, foreign_key="mes_project_stage.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "提交时工艺所属阶段"})
    stage_name_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "提交时项目阶段名称快照"})
    operation_description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={"comment": "工艺说明快照"})
    sequence_no: int = Field(nullable=False, sa_column_kwargs={"comment": "工序顺序"})
    work_center_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "工作中心名称快照"})
    workstation_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "工作站名称快照"})
    assigned_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={"comment": "派工人员；空表示按工作站或班组开放"})
    assigned_production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "手动指定的生产人员；为空时优先使用已应用方案的批次安排，再按原派工账号或开放任务处理"})
    planned_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "工序计划数量；单位沿用工单"})
    standard_minutes_per_unit: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "配置时单件预计工时；分钟/工单基本单位；乘本工序计划数量得到预计总时长，不代表实报工时"})
    is_imported_snapshot: bool = Field(default=False, sa_column_kwargs={"server_default": text("false"), "comment": "是否外部工序状态快照；缺少原排程时不按导入时间伪造原计划，人工重新配置后使用新配置记录"})
    good_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "工序累计合格数量"})
    scrap_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "工序累计报废数量"})
    rework_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "工序累计返工数量"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "工序任务状态；字典 mes_operation_task_status"})
    priority_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "任务优先级；字典 mes_priority"})
    required_skills_snapshot: list[str] = Field(default_factory=list, sa_type=JSONB, nullable=False, sa_column_kwargs={"server_default": text("'[]'::jsonb"), "comment": "技能要求快照；字典编码数组"})
    is_quality_required: bool = Field(default=False, nullable=False, sa_column_kwargs={"server_default": text("false"), "comment": "是否需要质量检验或放行"})
    is_equipment_required_snapshot: bool | None = Field(default=None, sa_column_kwargs={"comment": "工程确认时是否占用本厂机器的快照；空为待确认，不以设备外键空值推断人工工序"})
    is_predecessor_ready: bool = Field(default=True, nullable=False, sa_column_kwargs={"server_default": text("true"), "comment": "当前前置任务是否满足；仅为缓存提示，执行时必须再次校验"})
    due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "工序交期"})
    planned_start_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "人工排程计划开始时间；与计划结束成对，不代表实际开工"})
    planned_end_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "人工排程计划结束时间；须晚于计划开始"})
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"server_default": text("1"), "comment": "版本号；乐观锁"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class MesOperationMaterialRequirement(SQLModel, table=True):
    """工序物料需求：一行代表某工序所需的一种物料。"""

    __tablename__ = "mes_operation_material_requirement"
    __table_args__ = (
        Index("uk_mes_operation_material_requirement_operation_id_item_id", "operation_id", "item_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "MES 工序物料需求；保存计划用量与现场累计消耗。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", index=True, nullable=False, sa_column_kwargs={"comment": "工序任务"})
    item_id: UUID = Field(foreign_key="md_item.id", index=True, nullable=False, sa_column_kwargs={"comment": "需求物料；引用 md_item"})
    item_no_snapshot: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "物料编号快照"})
    item_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "物料名称快照"})
    required_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "需求数量"})
    consumed_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "已消耗数量"})
    unit_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "物料单位；字典 md_unit"})
    is_lot_controlled: bool = Field(default=False, nullable=False, sa_column_kwargs={"server_default": text("false"), "comment": "是否批次追溯"})
    is_serial_controlled: bool = Field(default=False, nullable=False, sa_column_kwargs={"server_default": text("false"), "comment": "是否序列号追溯"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class MesOperationExecution(SQLModel, table=True):
    """执行区间：一行代表一次工序任务在现场的 Track-in 到 Track-out 区间。"""

    __tablename__ = "mes_operation_execution"
    __table_args__ = (
        Index("idx_mes_operation_execution_operation_id_status_code", "operation_id", "status_code"),
        {"comment": "MES 工序执行区间；允许暂停、换站和多次执行。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", index=True, nullable=False, sa_column_kwargs={"comment": "工序任务"})
    production_phase_id: UUID | None = Field(default=None, foreign_key="mes_operation_production_phase.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "自动排程首件或剩余批量的实际执行批次；原整批执行为空"})
    production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际生产人员身份；与录入报工的登录账号分开，不为无账号人员伪造账号"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次实际执行设备；与工序当前配置分离，供实际占用及追溯"})
    segment_type_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "当前实际执行阶段；字典 mes_schedule_segment_type；原整批执行为空，照看和专注容量据此区分"})
    worker_user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={"comment": "执行人员；租户用户"})
    worker_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "执行人员姓名快照"})
    workstation_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "执行工作站快照"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "执行状态；字典 mes_execution_status"})
    tracked_in_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={"comment": "Track-in 时间"})
    held_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "最近一次暂停时间"})
    tracked_out_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "Track-out 时间"})
    labor_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={"comment": "累计人工工时；分钟"})
    machine_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={"comment": "累计机器工时；分钟"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field()


class MesProductionReport(SQLModel, table=True):
    """现场报工事实：提交后只追加，更正通过冲销或反向报工。"""

    __tablename__ = "mes_production_report"
    __table_args__ = (
        Index("uk_mes_production_report_org_id_report_no", "org_id", "report_no", unique=True),
        Index("uk_mes_production_report_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        Index("idx_mes_production_report_operation_id_created_at", "operation_id", "created_at"),
        {"comment": "MES 现场生产报工事实；手机、Web、设备等终端提交的一次产量与工时事实。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    report_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "报工单号"})
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", index=True, nullable=False, sa_column_kwargs={"comment": "工序任务"})
    execution_id: UUID | None = Field(default=None, foreign_key="mes_operation_execution.id", index=True, nullable=True, sa_column_kwargs={"comment": "关联执行区间"})
    good_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "本次合格数量"})
    scrap_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "本次报废数量"})
    rework_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={"comment": "本次返工数量"})
    labor_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={"comment": "本次人工工时；分钟"})
    machine_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={"comment": "本次机器工时；分钟"})
    exception_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={"comment": "异常类型；字典 mes_exception_type"})
    note: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={"comment": "现场说明；不存凭据等机密信息"})
    idempotency_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "幂等键；同一用户重试必须复用"})
    source_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "报工来源；字典 mes_report_source"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "报工处理状态；字典 mes_report_status"})
    reported_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={"comment": "业务发生时间"})
    operation_name_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "工艺切换前冻结的报工工序名称；未切换时从工序读取"})
    created_at: datetime = created_at_field()
    created_by: UUID = Field(foreign_key="sys_user.id", nullable=False, sa_column_kwargs={"comment": "提交人；现场报工必须有租户用户"})
    flex_form: dict[str, Any] = flex_form_field()


class MesProductionReportChange(SQLModel, table=True):
    """一行代表一次报工更正或冲销申请；原报工数值不被覆盖。"""
    __tablename__ = "mes_production_report_change"
    __table_args__ = (
        Index("uk_mes_production_report_change_report_id_pending", "report_id", unique=True, postgresql_where=text("status_code in ('draft', 'submitted')")),
        Index("uk_mes_production_report_change_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        {"comment": "MES 报工变更申请；底座工作流审批通过后冲销原报工并追加替代事实，拒绝或撤回不改产量。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    report_id: UUID = Field(foreign_key="mes_production_report.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "被更正的原报工；数量和工时保持原值，仅可变为已冲销"})
    replacement_report_id: UUID | None = Field(default=None, foreign_key="mes_production_report.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "审批后追加的替代报工；纯冲销为空"})
    wf_instance_id: UUID | None = Field(default=None, foreign_key="wf_instance.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "底座审批实例；由工作流拥有状态与候选人"})
    change_type_code: str = Field(max_length=64, sa_column_kwargs={"comment": "变更类型；字典 mes_report_change_type"})
    status_code: str = Field(default="draft", max_length=64, sa_column_kwargs={"comment": "申请状态；字典 mes_report_change_status"})
    good_quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请替代报工的合格数量；纯冲销为零"})
    scrap_quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请替代报工的报废数量；纯冲销为零"})
    rework_quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请替代报工的返工数量；纯冲销为零"})
    labor_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请替代报工的人工工时；分钟"})
    machine_minutes: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请替代报工的机器工时；分钟"})
    reason: str = Field(sa_type=Text, sa_column_kwargs={"comment": "变更理由；自由文本不进入 AI"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "提交幂等键；同一用户失败重试复用"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("申请人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("审批状态最后修改人")
    flex_form: dict[str, Any] = flex_form_field()


class MesWorkOrderEvent(SQLModel, table=True):
    """工单事件：一行代表一次配置或生命周期变更，追加保留。"""
    __tablename__ = "mes_work_order_event"
    __table_args__ = (
        Index("idx_mes_work_order_event_work_order_id_created_at", "work_order_id", "created_at"),
        {"comment": "MES 工单生命周期事件；保留动作、版本、状态和理由，不覆盖历史。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属执行工单"})
    event_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "动作类型；字典 mes_work_order_event_type"})
    from_status_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "变更前状态；字典 mes_work_order_status"})
    to_status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "变更后状态；字典 mes_work_order_status"})
    version_no: int = Field(nullable=False, sa_column_kwargs={"comment": "动作后的工单版本号"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "动作理由；自由文本不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("动作人；系统完成时为空")
    flex_form: dict[str, Any] = flex_form_field()


class MesProcessTemplate(SQLModel, table=True):
    """一行代表一个可复用的工序模板；应用时复制到工单，不共享可变工序。"""
    __tablename__ = "mes_process_template"
    __table_args__ = (
        Index("uk_mes_process_template_org_id_template_no", "org_id", "template_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "MES 工序模板；定义复用的有序工序，修改模板不修改已创建的生产工单。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    template_no: str = Field(max_length=64, sa_column_kwargs={"comment": "模板编号；组织内唯一"})
    template_name: str = Field(max_length=128, sa_column_kwargs={"comment": "模板名称"})
    product_item_id: UUID | None = Field(default=None, foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "适用产品物料；为空表示本组织通用模板"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "模板修订号；更新时校验，用于识别应用时版本"})
    is_active: bool = Field(default=True, sa_column_kwargs={"comment": "是否可供新工单选用；停用不影响已有工单"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class MesProcessTemplateOperation(SQLModel, table=True):
    """一行代表工序模板中的一道有序工序。"""
    __tablename__ = "mes_process_template_operation"
    __table_args__ = (
        Index("uk_mes_process_template_operation_template_id_operation_no", "template_id", "operation_no", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("standard_minutes_per_unit IS NULL OR standard_minutes_per_unit > 0", name="ck_mes_process_template_operation_positive_standard_minutes"),
        {"comment": "MES 工序模板明细；不保存人员派工、排程或生产累计。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    template_id: UUID = Field(foreign_key="mes_process_template.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属工序模板"})
    sequence_no: int = Field(sa_column_kwargs={"comment": "执行顺序；按工单选用时复制的顺序执行"})
    operation_no: str = Field(max_length=64, sa_column_kwargs={"comment": "模板内工序编号"})
    operation_name: str = Field(max_length=128, sa_column_kwargs={"comment": "工序名称"})
    standard_minutes_per_unit: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "路线建议单件预计工时；分钟/产品基本单位；选用时复制至工单，不反写已建工单"})
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用工艺档案；名称和说明按提交时保存，不随档案变化"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用设备档案；工作站字段保存当时设备编号"})
    requirement_id: UUID | None = Field(default=None, foreign_key="mes_process_requirement.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "选用工艺要求；操作说明保存当时要求"})
    project_stage_id: UUID | None = Field(default=None, foreign_key="mes_project_stage.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "提交时工艺所属阶段"})
    stage_name_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "提交时项目阶段名称快照"})
    operation_description: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "工艺操作说明；自由文本不进入 AI"})
    work_center_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "建议工作中心名称；尚无资源主数据外键"})
    workstation_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "建议工作站名称；尚无资源主数据外键"})
    is_quality_required: bool = Field(default=False, sa_column_kwargs={"comment": "是否需要检验；沿用工序的质量等待规则"})
    is_equipment_required_snapshot: bool | None = Field(default=None,sa_column_kwargs={"comment":"模板确认时本厂机器需求快照；空为待工程确认"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class MesReworkAssignment(SQLModel, table=True):
    """一行代表一次返工报工事实到返修执行工单的分配；关联追加保留。"""
    __tablename__ = "mes_rework_assignment"
    __table_args__ = (
        Index("uk_mes_rework_assignment_work_order_id", "work_order_id", unique=True),
        Index("idx_mes_rework_assignment_report_id", "report_id"),
        {"comment": "MES 返工处理关联；数量使用关联返修工单的计划和实际产量，不重复增加原报工产量。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    report_id: UUID = Field(foreign_key="mes_production_report.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "产生返工数量的原始报工事实"})
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "处理这部分返工的独立返修工单"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("安排人")
    flex_form: dict[str, Any] = flex_form_field()


class MesExecutionEvent(SQLModel, table=True):
    """执行事件：一行代表一次 MES 状态变化或现场动作，追加写入。"""

    __tablename__ = "mes_execution_event"
    __table_args__ = (
        Index("idx_mes_execution_event_operation_id_created_at", "operation_id", "created_at"),
        {"comment": "MES 工序执行事件时间线；状态变化、暂停、报工和 Track-out 只追加记录。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    operation_id: UUID = Field(foreign_key="mes_work_order_operation.id", index=True, nullable=False, sa_column_kwargs={"comment": "工序任务"})
    execution_id: UUID | None = Field(default=None, foreign_key="mes_operation_execution.id", index=True, nullable=True, sa_column_kwargs={"comment": "关联执行区间"})
    event_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "事件类型；字典 mes_execution_event_type"})
    from_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={"comment": "变更前工序状态；字典 mes_operation_task_status"})
    to_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={"comment": "变更后工序状态；字典 mes_operation_task_status"})
    note: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={"comment": "事件说明"})
    actor_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={"comment": "动作人；系统事件可为空"})
    actor_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "动作人姓名快照"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；系统事件可为空")
    flex_form: dict[str, Any] = flex_form_field()
