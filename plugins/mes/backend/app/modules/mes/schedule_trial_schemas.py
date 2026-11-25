"""只读试排协议；阶段资料是本次工程确认输入，不冒充已保存的生产事实。"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from .schedule_limits import DEFAULT_SOLVE_SECONDS, MAX_SOLVE_SECONDS


class TrialScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_id: UUID
    work_order_ids: list[UUID] = Field(min_length=1, max_length=10)
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self):
        if not timedelta(hours=1) <= self.end_at - self.start_at <= timedelta(days=31):
            raise ValueError("试排窗口须为1小时至31天")
        if len(set(self.work_order_ids)) != len(self.work_order_ids):
            raise ValueError("工单不能重复")
        return self


class OperationInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    process_id: UUID
    is_equipment_required: bool
    minutes_per_piece: Decimal = Field(gt=0, le=1440, max_digits=12, decimal_places=3)


class TrialOperationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    version_no: int = Field(ge=1)
    kind_key: Literal["machine", "manual", "inspection", "machine_inspection", "external"]
    setup_minutes: int = Field(ge=0, le=1440)
    load_minutes: int = Field(ge=0, le=240)
    unload_minutes: int = Field(ge=0, le=240)
    supervision_key: Literal["exclusive", "two_machines"] = "exclusive"
    is_lunch_auto_allowed: bool = False
    is_timing_confirmed: bool = False
    inspection: OperationInspection | None = None
    external_first_return_at: AwareDatetime | None = None
    external_remaining_return_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind_key != "machine" and (self.load_minutes or self.unload_minutes
                or self.is_lunch_auto_allowed or self.supervision_key != "exclusive"):
            raise ValueError("人工/检验工序不使用机器装卸料或自动照看参数")
        if self.kind_key == "external":
            if self.setup_minutes or not self.external_first_return_at or not self.inspection:
                raise ValueError("委外须填写预计回厂时间及回厂检验；不占用本厂准备资源")
            if self.external_remaining_return_at and self.external_remaining_return_at<=self.external_first_return_at:
                raise ValueError("剩余批量预计回厂须晚于首件回厂，且仍受首件检验放行约束")
        elif self.external_first_return_at or self.external_remaining_return_at:
            raise ValueError("只有委外工序填写外部回厂时间")
        return self


class TrialOrderRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: UUID
    version_no: int = Field(ge=1)
    ready_at: AwareDatetime
    is_readiness_confirmed: bool = False
    delivery_mode_key: Literal["whole_project", "individual"] = "whole_project"
    shipping_preparation_minutes: int | None = Field(default=None, ge=0, le=10080)
    shipping_windows: list["ShippingWindow"] = Field(default_factory=list, max_length=62)


class ShippingWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.end_at<=self.start_at:raise ValueError("出货时段结束必须晚于开始")
        return self


TrialOrderRule.model_rebuild()


class TrialInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode_key: Literal["separate", "last_operation"] = "separate"
    process_id: UUID | None = None
    is_equipment_required: bool = False
    minutes_per_piece: Decimal | None = Field(default=None, gt=0, le=1440, max_digits=12, decimal_places=3)

    @model_validator(mode="after")
    def validate_inspection(self):
        if self.mode_key == "separate" and (self.process_id is None or self.minutes_per_piece is None):
            raise ValueError("独立检验必须明确工艺及单件耗时")
        if self.mode_key == "last_operation" and (self.process_id or self.minutes_per_piece or self.is_equipment_required):
            raise ValueError("复用末道检验时不再额外添加检验资源和耗时")
        return self


class TrialSolve(TrialScope):
    snapshot_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation_rules: list[TrialOperationRule] = Field(min_length=1, max_length=100)
    order_rules: list[TrialOrderRule] = Field(min_length=1, max_length=10)
    inspection: TrialInspection
    is_regular_calendar_confirmed: bool = False
    time_limit_seconds: int = Field(default=DEFAULT_SOLVE_SECONDS, ge=1, le=MAX_SOLVE_SECONDS)

    @model_validator(mode="after")
    def validate_ids(self):
        for rows, key in ((self.operation_rules, "operation_id"), (self.order_rules, "work_order_id")):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError("确认资料不能重复")
        return self
