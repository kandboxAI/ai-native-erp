"""交付驾驶舱只读筛选；交期窗口和风险分类不改变生产状态。"""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from app.db.pagination import PageParams


class DeliveryCockpitQuery(PageParams):
    keyword: str | None = Field(default=None, max_length=128)
    customer: str | None = Field(default=None, max_length=128)
    org_id: UUID | None = None
    due_from: date | None = None
    due_to: date | None = None
    soon_days: int = Field(default=7, ge=1, le=30)
    focus: Literal["outstanding", "all", "overdue", "due_soon", "waiting_quality", "unplanned", "released_output", "delivered", "blocked", "no_due", "exceptions", "overdue_exceptions"] = "outstanding"

    @model_validator(mode="after")
    def valid_range(self):
        if self.due_from and self.due_to and self.due_from > self.due_to:
            raise ValueError("交期开始日期不能晚于结束日期")
        return self
