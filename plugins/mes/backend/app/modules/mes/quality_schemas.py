from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.db.pagination import PageParams


class QualityQuery(PageParams):
    keyword: str | None = Field(default=None, max_length=128)
    status_code: Literal["waiting_quality", "pending", "dispatched", "in_progress", "paused", "completed", "cancelled", ""] = "waiting_quality"


class QualityInspectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version_no: int = Field(ge=1)
    result_code: Literal["pass", "fail"]
    note: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    production_person_id: UUID | None = None
    production_phase_code: Literal["first","remaining"] | None = None
    rework_operation_id: UUID | None = None

    @model_validator(mode="after")
    def reason_required(self):
        self.note = self.note or None
        if self.result_code == "fail" and not self.note:
            raise ValueError("退回返工必须填写不合格原因")
        return self
