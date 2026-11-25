"""部门岗位；任职由人事模块维护。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class PositionWrite(BaseModel):
    org_id: UUID
    position_no: str = Field(min_length=1, max_length=64)
    position_name: str = Field(min_length=1, max_length=128)
    department_id: UUID
    parent_position_id: UUID | None = None
    is_department_head: bool = False
    headcount: int | None = Field(default=None, ge=1)
    sort_no: int | None = None
    is_active: bool = True


class PositionItem(PositionWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    updated_at: datetime


class PositionQuery(PageParams):
    org_id: UUID | None = None
    is_active: bool | None = None

