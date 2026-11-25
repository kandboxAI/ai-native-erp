from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin


class WorkflowTaskListQuery(PageParams):
    status_code: str | None = Field(default="pending", description="pending 待我办理 / completed 我已办理 / 空=全部")
    business_type_code: str | None = None
    business_id: UUID | None = None


class WorkflowCcListQuery(PageParams):
    status_code: str | None = Field(default=None, description="unread/read")
    business_type_code: str | None = None
    business_id: UUID | None = None


class WorkflowSupervisionListQuery(PageParams):
    status_code: str | None = Field(default="running", description="running/completed/rejected/cancelled")
    business_type_code: str | None = None


class WorkflowSupervisionListItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("started_at",)

    instance_id: UUID
    business_type_code: str
    business_id: UUID
    org_id: UUID
    instance_status_code: str
    task_name: str | None = None
    task_key: str | None = None
    approver_names: list[str] = Field(default_factory=list)
    business_summary: str | None = None
    started_at: datetime | None = None


class WorkflowTaskCompleteBody(BaseModel):
    comment: str | None = Field(default=None, max_length=500, description="审批意见")


class WorkflowCommentBody(BaseModel):
    comment: str = Field(..., min_length=1, max_length=1000, description="沟通内容")


class WorkflowResubmitBody(BaseModel):
    comment: str = Field(..., min_length=1, max_length=500, description="重新发起说明")
    starter_choices: dict[str, list[UUID]] | None = Field(default=None, description="当前流程要求由发起人选择的审批人或抄送人")


class WorkflowTaskListItem(DisplayDatetimeJsonMixin):
    business_avatar_url: str | None = None
    __display_datetime_fields__ = ("arrived_at", "completed_at", "ai_analysis_generated_at")

    id: UUID
    instance_id: UUID
    business_type_code: str
    business_id: UUID
    task_key: str
    task_name: str
    assignee_type_code: str
    assignee_value: str | None = None
    approval_mode_code: str = "single"
    required_count: int = 1
    approved_count: int = 0
    status_code: str
    outcome_code: str | None = None
    arrived_at: datetime | None = None
    completed_at: datetime | None = None
    instance_status_code: str
    business_summary: str | None = None
    candidate_names: list[str] = Field(default_factory=list)
    ai_analysis: str | None = None
    ai_analysis_status_code: str = "not_applicable"
    ai_analysis_generated_at: datetime | None = None
    can_direct_approve: bool = False



class WorkflowTimelineItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("occurred_at",)

    occurred_at: datetime | None = None
    action_code: str
    action_label: str
    actor_name: str | None = None
    comment: str | None = None
    task_name: str | None = None
    task_key: str | None = None
    assignee_label: str | None = None
    assignee_names: list[str] = Field(default_factory=list)
    approval_mode_code: str = "single"
    approved_count: int = 0
    required_count: int = 1
    instance_id: str | None = None
    instance_status_code: str | None = None


class WorkflowTimelineResult(BaseModel):
    business_type_code: str
    business_id: UUID
    items: list[WorkflowTimelineItem] = Field(default_factory=list)
    latest_instance_status_code: str | None = None
    org_id: UUID | None = None
    can_comment: bool = False
    can_resubmit: bool = False
    requires_edit_before_resubmit: bool = False
    edit_saved_after_rejection: bool = False


def empty_business_detail() -> dict[str, Any]:
    return {"fields": [], "tables": []}
