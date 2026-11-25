from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.pagination import PageParams


class ProductionTaskListQuery(PageParams):
    status_code: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=128)


class MesWorkOrderListQuery(PageParams):
    processing_type_code: Literal["in_house", "outsourced", "purchased"] | None = None
    status_code: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=128)
    priority_code: str | None = Field(default=None, max_length=64)
    overdue_only: bool = False
    repair_source_only: bool = False
    production_order_id: UUID | None = None
    customer: str | None = Field(default=None, max_length=128)
    order_type_code: str | None = Field(default=None, max_length=64)
    created_from: date | None = None
    created_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    configuration: str | None = Field(default=None, pattern="^(configured|unconfigured)$")
    created_by: UUID | None = None
    creator: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def ordered_dates(self):
        for start, end in [(self.created_from, self.created_to), (self.due_from, self.due_to)]:
            if start and end and start > end:
                raise ValueError("开始日期不能晚于结束日期")
        return self


class ProductionReportListQuery(PageParams):
    operation_id: UUID | None = None
    work_order_id: UUID | None = None
    status_code: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=128)


class MesOptionQuery(BaseModel):
    keyword: str = Field(default="", max_length=128)
    limit: int = Field(default=50, ge=1, le=50)


class ProductionActionBody(BaseModel):
    version_no: int = Field(ge=1)
    execution_id: UUID | None = None
    note: str | None = Field(default=None, max_length=1000)
    production_person_id: UUID | None = None
    production_phase_code: Literal["first", "remaining"] | None = None
    segment_type_code: Literal["load", "run", "unload", "manual", "external_return"] | None = None


class ProductionDispatchBody(BaseModel):
    version_no: int = Field(ge=1)
    production_person_id: UUID
    note: str | None = Field(default=None, max_length=1000)


class WorkOrderOperationCreate(BaseModel):
    is_equipment_required_snapshot: bool | None = None
    standard_minutes_per_unit: Decimal | None = Field(default=None, gt=0, le=5256000, max_digits=18, decimal_places=3)
    process_id: UUID | None = None
    equipment_id: UUID | None = None
    requirement_id: UUID | None = None
    operation_no: str = Field(min_length=1, max_length=64)
    operation_name: str = Field(min_length=1, max_length=128)
    planned_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=3)
    work_center_name: str | None = Field(default=None, max_length=128)
    workstation_name: str | None = Field(default=None, max_length=128)
    assigned_user_id: UUID | None = None
    is_quality_required: bool = False
    operation_description: str | None = Field(default=None, max_length=4000)

    @field_validator("operation_no", "operation_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("工序编号和名称不能为空")
        return value.strip()


class WorkOrderCreate(BaseModel):
    material_name_snapshot: str | None = Field(default=None, max_length=256)
    heat_treatment_snapshot: str | None = Field(default=None, max_length=256)
    surface_treatment_snapshot: str | None = Field(default=None, max_length=256)
    process_requirement_snapshot: str | None = Field(default=None, max_length=4000)
    outsourced_due_at: datetime | None = None
    drawing_attachment_ids: list[UUID] | None = Field(default=None, max_length=2)
    drawing_revision_label: str | None = Field(default=None, max_length=128)
    processing_type_code: Literal["in_house", "outsourced", "purchased"] = "in_house"
    org_id: UUID | None = None
    work_order_no: str = Field(min_length=1, max_length=64)
    product_item_id: UUID
    planned_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    priority_code: str = Field(default="normal", min_length=1, max_length=64)
    due_at: datetime | None = None
    operations: list[WorkOrderOperationCreate] = Field(default_factory=list, max_length=100)
    publish: bool = True
    source_work_order_id: UUID | None = None
    rework_report_id: UUID | None = None
    process_template_id: UUID | None = None
    process_template_version_snapshot: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("work_order_no")
    @classmethod
    def strip_order_no(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("工单号不能为空")
        return value.strip()

    @field_validator("due_at", "outsourced_due_at")
    @classmethod
    def aware_due_date(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("交付时间必须包含时区")
        return value

    @model_validator(mode="after")
    def unique_operations(self):
        if self.drawing_attachment_ids:
            if len(set(self.drawing_attachment_ids)) != len(self.drawing_attachment_ids):
                raise ValueError("图纸文件不能重复提交")
        if self.publish and not self.operations:
            raise ValueError("下单前至少配置一道工序")
        numbers = [operation.operation_no for operation in self.operations]
        if len(numbers) != len(set(numbers)):
            raise ValueError("同一工单的工序编号不能重复")
        from .operation_planning import MAX_PLAN_MINUTES
        total = sum((op.standard_minutes_per_unit * (op.planned_quantity or self.planned_quantity)
            for op in self.operations if op.standard_minutes_per_unit is not None), Decimal(0))
        if total > MAX_PLAN_MINUTES:
            raise ValueError("工序预计总时长超过10年，请检查单件工时与计划数量")
        return self


class WorkOrderUpdate(WorkOrderCreate):
    version_no: int = Field(ge=1)
    publish: bool = False


class WorkOrderCommand(BaseModel):
    version_no: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class ProjectOrderVersion(BaseModel):
    id: UUID
    version_no: int = Field(ge=1)


class ProjectPlaceOrder(BaseModel):
    version_no: int = Field(ge=1)
    orders: list[ProjectOrderVersion] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_orders(self):
        if len({row.id for row in self.orders}) != len(self.orders):
            raise ValueError("下单货品不能重复")
        return self


class ProductionOrderCreate(BaseModel):
    customer_id: UUID | None = None
    org_id: UUID | None = None
    production_order_no: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=128)
    customer_no: str | None = Field(default=None, max_length=64)
    customer_name: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=4000)
    products: list[WorkOrderCreate] = Field(min_length=1, max_length=100)

    @field_validator("production_order_no", "project_name")
    @classmethod
    def strip_required(cls, value):
        if not value.strip():
            raise ValueError("项目编号和名称不能为空")
        return value.strip()

    @model_validator(mode="after")
    def unique_order_numbers(self):
        values = [row.work_order_no for row in self.products]
        if len(values) != len(set(values)):
            raise ValueError("同一项目中的产品工单号不能重复")
        return self


class ProductionOrderUpdate(ProductionOrderCreate):
    version_no: int = Field(ge=1)
    products: list[WorkOrderCreate] = Field(default_factory=list, max_length=100)


class ProductionReportBody(ProductionActionBody):
    good_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    scrap_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    rework_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    labor_minutes: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    machine_minutes: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    exception_type_code: str | None = Field(default=None, max_length=64)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("幂等键不能为空")
        return value


class ProductionMaterialRequirementItem(BaseModel):
    id: UUID
    item_no: str
    item_name: str
    required_quantity: float
    consumed_quantity: float
    unit_name: str
    is_lot_controlled: bool
    is_serial_controlled: bool


class ProductionExecutionItem(BaseModel):
    id: UUID
    tracked_in_at: datetime
    tracked_out_at: datetime | None = None
    status_code: str | None = None
    worker_name: str | None = None
    workstation_name: str | None = None
    labor_minutes: float | None = None
    machine_minutes: float | None = None
    production_phase_id: UUID | None = None
    production_person_id: UUID | None = None
    production_person_name: str | None = None
    segment_type_code: str | None = None


class ProductionExecutionEventItem(BaseModel):
    id: UUID
    event_type_code: str
    event_label: str | None = None
    note: str | None = None
    actor_name_snapshot: str | None = None
    created_at: datetime


class ProductionTaskItem(BaseModel):
    id: UUID
    work_order_id: UUID | None = None
    work_order_status_code: str | None = None
    org_id: UUID | None = None
    sequence_no: int = 1
    version_no: int = 1
    assigned_user_id: UUID | None = None
    assigned_production_person_id: UUID | None = None
    assigned_production_person_name: str | None = None
    assigned_production_person_no: str | None = None
    schedule_plan_id: UUID | None = None
    scheduled_production_person_name: str | None = None
    process_id: UUID | None = None
    equipment_id: UUID | None = None
    assigned_user_name: str | None = None
    actual_started_at: datetime | None = None
    actual_finished_at: datetime | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    work_order_no: str
    operation_no: str
    operation_name: str
    operation_description: str | None = None
    product_item_no: str
    product_item_name: str
    work_center_name: str | None = None
    workstation_name: str | None = None
    planned_quantity: float
    good_quantity: float
    scrap_quantity: float
    rework_quantity: float
    unit_name: str
    status_code: str
    status_label: str
    priority_code: str | None = None
    priority_label: str | None = None
    due_at: datetime | None = None
    updated_at: datetime | None = None


class ProductionTaskDetail(ProductionTaskItem):
    version_no: int
    operation_description: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    is_predecessor_ready: bool
    is_quality_required: bool
    schedule_context: dict[str, Any] | None = None
    material_requirements: list[ProductionMaterialRequirementItem] = Field(default_factory=list)
    current_execution: ProductionExecutionItem | None = None
    events: list[ProductionExecutionEventItem] = Field(default_factory=list)
    executions: list[ProductionExecutionItem] = Field(default_factory=list)


class MesOperationProgressItem(BaseModel):
    is_imported_snapshot: bool = False
    """工单列表的最小工序进度投影，不包含人员、说明或附件。"""
    id: UUID
    sequence_no: int
    operation_no: str
    operation_name: str
    planned_quantity: float
    good_quantity: float
    scrap_quantity: float
    rework_quantity: float
    status_code: str
    status_label: str
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    actual_started_at: datetime | None = None
    actual_finished_at: datetime | None = None
    plan_source_key: str | None = None
    standard_minutes_per_unit: float | None = None
    planned_duration_minutes: float | None = None


class MesWorkOrderItem(BaseModel):
    is_process_change_pending: bool = False
    material_name_snapshot: str | None = None
    heat_treatment_snapshot: str | None = None
    surface_treatment_snapshot: str | None = None
    process_requirement_snapshot: str | None = None
    outsourced_due_at: datetime | None = None
    display_status_key: str | None = None
    processing_type_code: str = "in_house"
    processing_type_label: str = "自制"
    id: UUID
    org_id: UUID | None = None
    production_order_id: UUID | None = None
    production_order_no: str | None = None
    project_name: str | None = None
    customer_no: str | None = None
    customer_name: str | None = None
    order_type_code: str = "production"
    source_work_order_id: UUID | None = None
    version_no: int = 1
    created_at: datetime | None = None
    created_by: UUID | None = None
    creator_name: str | None = None
    work_order_no: str
    product_item_no: str
    product_item_name: str
    unit_name: str
    planned_quantity: float
    good_quantity: float
    scrap_quantity: float
    rework_quantity: float
    status_code: str
    status_label: str
    priority_code: str
    priority_label: str
    due_at: datetime | None = None
    operation_count: int
    completed_operation_count: int
    operation_progress: list[MesOperationProgressItem] = Field(default_factory=list)
    updated_at: datetime | None = None


class MesWorkOrderDetail(MesWorkOrderItem):
    operations: list[ProductionTaskItem] = Field(default_factory=list)
    note: str | None = None
    events: list[dict] = Field(default_factory=list)
    can_edit_configuration: bool = False
    source_work_order_no: str | None = None


class ProductionReportItem(BaseModel):
    reporter_name: str | None = None
    note: str | None = None
    id: UUID
    report_no: str
    work_order_no: str
    operation_no: str
    operation_name: str
    product_item_no: str
    product_item_name: str
    good_quantity: float
    scrap_quantity: float
    rework_quantity: float
    labor_minutes: float | None = None
    machine_minutes: float | None = None
    exception_type_code: str | None = None
    status_code: str
    reported_at: datetime
    source_code: str
    created_by: UUID
    operation_id: UUID | None = None
    work_order_id: UUID | None = None


class ReportChangeBody(BaseModel):
    change_type_code: str = Field(pattern="^(replace|reverse)$")
    good_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    scrap_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    rework_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    labor_minutes: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    machine_minutes: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    starter_choices: dict[str, list[UUID]] | None = None

    @model_validator(mode="after")
    def valid_change(self):
        self.reason, self.idempotency_key = self.reason.strip(), self.idempotency_key.strip()
        if not self.reason or len(self.idempotency_key) < 8:
            raise ValueError("请填写变更理由并提供有效幂等键")
        if self.change_type_code == "reverse":
            if any([self.good_quantity, self.scrap_quantity, self.rework_quantity, self.labor_minutes, self.machine_minutes]):
                raise ValueError("纯冲销的替代数量和工时必须为零")
        elif self.good_quantity + self.scrap_quantity + self.rework_quantity <= 0:
            raise ValueError("更正后的产出数量必须大于零；清空报工请申请冲销")
        return self


class ReportChangeQuery(PageParams):
    status_code: str | None = Field(default=None, max_length=64)
    report_id: UUID | None = None


class ScheduleQuery(ProductionTaskListQuery):
    group_by_work_order: bool = Field(default=False, description="按货品工单分页；total 为工单数，items 包含本页工单的全部授权工序")
    work_order_id: UUID | None = None
    work_center: str | None = Field(default=None, max_length=128)
    scheduled: bool | None = None
    start_date: date | None = None
    end_date: date | None = None
    product_keyword: str | None = Field(default=None, max_length=128)
    equipment_keyword: str | None = Field(default=None, max_length=128)
    equipment_id: UUID | None = None
    process_id: UUID | None = None
    org_id: UUID | None = None
    workstation: str | None = Field(default=None, max_length=128)
    work_center_exact: str | None = Field(default=None, max_length=128)
    unassigned_only: bool = False
    unfinished_only: bool = False
    unstarted_only: bool = False
    priority_code: str | None = Field(default=None, max_length=64)
    due_from: date | None = None
    due_to: date | None = None
    window_start: date | None = None
    window_end: date | None = None

    @model_validator(mode="after")
    def valid_schedule_ranges(self):
        for start, end in ((self.start_date, self.end_date), (self.due_from, self.due_to), (self.window_start, self.window_end)):
            if start and end and start > end:
                raise ValueError("开始日期不能晚于结束日期")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("时间轴显示区间须同时填写开始和结束日期")
        if self.window_start and (self.window_end - self.window_start).days > 30:
            raise ValueError("时间轴一次最多显示 31 天")
        return self


class ScheduleOperation(BaseModel):
    operation_id: UUID
    version_no: int = Field(ge=1)
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    equipment_id: UUID | None = None

    @model_validator(mode="after")
    def valid_period(self):
        start, end = self.planned_start_at, self.planned_end_at
        if (start is None) != (end is None):
            raise ValueError("计划开始与结束时间必须同时填写或同时清空")
        if start is not None:
            if start.utcoffset() is None or end.utcoffset() is None:
                raise ValueError("排程时间必须包含时区")
            if start >= end:
                raise ValueError("计划结束时间必须晚于开始时间")
        return self


class ScheduleUpdate(BaseModel):
    operations: list[ScheduleOperation] = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_tasks(self):
        if not self.note.strip():
            raise ValueError("请填写排程或调整理由")
        ids = [row.operation_id for row in self.operations]
        if len(set(ids)) != len(ids):
            raise ValueError("同一工序不能重复排程")
        return self


class ProcessTemplateQuery(PageParams):
    org_id: UUID | None = None
    product_item_id: UUID | None = None
    is_active: bool | None = None


class ProcessTemplateBody(BaseModel):
    org_id: UUID
    template_no: str = Field(min_length=1, max_length=64)
    template_name: str = Field(min_length=1, max_length=128)
    product_item_id: UUID | None = None
    version_no: int | None = Field(default=None, ge=1)
    is_active: bool = True
    operations: list[WorkOrderOperationCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_template(self):
        self.template_no, self.template_name = self.template_no.strip(), self.template_name.strip()
        if not self.template_no or not self.template_name:
            raise ValueError("模板编号和名称不能为空")
        numbers = [row.operation_no for row in self.operations]
        if len(set(numbers)) != len(numbers):
            raise ValueError("模板中的工序编号不能重复")
        if any(row.assigned_user_id or row.planned_quantity is not None for row in self.operations):
            raise ValueError("模板只定义工艺，不保存派工人员或本单数量")
        return self


class WorkOrderDrawingUpdate(BaseModel):
    version_no: int = Field(ge=1)
    attachment_ids: list[UUID] = Field(default_factory=list, min_length=1, max_length=2)
    revision_label: str | None = Field(default=None, max_length=128)
    change_note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid_revision(self):
        self.revision_label = (self.revision_label or "").strip() or None
        self.change_note = self.change_note.strip()
        if not self.change_note or len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("请填写变更说明，且不能重复选择文件")
        return self


class DrawingHistoryQuery(PageParams):
    page_size: int = Field(default=5, ge=1, le=20)


class ReworkQuery(ProductionReportListQuery):
    allocation: str | None = Field(default=None, pattern="^(pending|partial|allocated)$")
