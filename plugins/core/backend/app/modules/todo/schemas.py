from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class TodoQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status_code: Literal["pending"] = "pending"
    keyword: str = Field(default="", max_length=100)
    sort_by: Literal["priority", "arrived_at"] = "priority"
    include_overdue: bool = False


class TodoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    todo_type_key: str = Field(max_length=128)
    source_id: UUID
    # 同一次创建重试复用 round_key；周期业务由所属类型校验。
    round_key: str = Field(min_length=1, max_length=64)
    due_at: AwareDatetime | None = None
    user_ids: list[UUID] = Field(default_factory=list, max_length=100)
    role_ids: list[UUID] = Field(default_factory=list, max_length=20)
    notify_assignees: bool = True


class TodoAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    comment: str = Field(default="", max_length=10000)
