from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.db.pagination import PageParams
from .schedule_trial_schemas import TrialSolve


class ReadinessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: UUID
    readiness_kind_code: Literal["material", "drawing", "program", "tool"]
    expected_at: AwareDatetime
    is_confirmed: bool = False
    version_no: int | None = Field(default=None,ge=1)


class ReadinessUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    readiness:list[ReadinessBody]=Field(min_length=4,max_length=40)


class SchedulePlanCreate(TrialSolve):
    plan_name: str = Field(min_length=1, max_length=128)
    readiness: list[ReadinessBody] = Field(min_length=4, max_length=40)

    @model_validator(mode="after")
    def complete_readiness(self):
        pairs = {(r.work_order_id, r.readiness_kind_code) for r in self.readiness}
        expected = {(order, kind) for order in self.work_order_ids for kind in ("material", "drawing", "program", "tool")}
        if pairs != expected or len(pairs) != len(self.readiness):
            raise ValueError("必须逐项确认每张工单材料、图纸、程序、刀具的预计就绪时间")
        return self


class SchedulePlanQuery(PageParams):
    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=128)
    status_code: str | None = Field(default=None, max_length=64)


class SchedulePlanCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_no: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=500)
