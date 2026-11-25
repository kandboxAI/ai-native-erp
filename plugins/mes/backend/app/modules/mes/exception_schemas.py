from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.db.pagination import PageParams

ExceptionStatus = Literal["pending", "in_progress", "waiting_confirmation", "closed"]
ExceptionAction = Literal["assign", "start", "progress", "resolve", "approve", "reject", "reopen"]


class ExceptionQuery(PageParams):
    keyword: str | None = Field(default=None, max_length=128)
    status_code: ExceptionStatus | None = None
    work_order_id: UUID | None = None
    assigned_to_me: bool = False
    overdue_only: bool = False


class ExceptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    work_order_id: UUID
    operation_id: UUID | None = None
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=4000)
    exception_type_code: Literal["material_shortage", "equipment_failure", "quality_abnormal", "changeover", "other"]
    assigned_user_id: UUID | None = None
    due_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("due_at")
    @classmethod
    def aware_date(cls, value):
        if value.utcoffset() is None: raise ValueError("处理期限必须包含时区")
        return value


class ExceptionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version_no: int = Field(ge=1)
    note: str = Field(default="", max_length=4000)
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def aware_date(cls, value):
        return ExceptionCreate.aware_date(value) if value else value
