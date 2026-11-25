"""流程定义接口的请求与响应模型（字段名与数据库一致）。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin


class WorkflowDefinitionBase(BaseModel):
    definition_name: str = Field(..., max_length=128)
    business_type_code: str = Field(..., max_length=64)
    org_id: UUID | None = None
    description: str | None = None
    is_active: bool = False
    is_default: bool = True


class WorkflowDefinitionCreate(WorkflowDefinitionBase):
    definition_no: str = Field(..., max_length=64)


class WorkflowDefinitionUpdate(BaseModel):
    definition_name: str | None = Field(default=None, max_length=128)
    business_type_code: str | None = Field(default=None, max_length=64)
    org_id: UUID | None = None
    description: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class WorkflowDefinitionVersionItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("published_at", "created_at")

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    definition_id: UUID
    version_no: int
    bpmn_process_no: str
    status_code: str
    published_at: datetime | None = None
    remark: str | None = None
    created_at: datetime
    created_by: UUID | None = None
    design: dict | None = None
    source: str | None = None
    is_current: bool | None = None


class WorkflowDefinitionItem(DisplayDatetimeJsonMixin, WorkflowDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    definition_no: str
    org_name: str | None = None
    current_version_id: UUID | None = None
    current_version_no: int | None = None
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    updated_by: UUID | None = None


class WorkflowDefinitionDetailItem(WorkflowDefinitionItem):
    versions: list[WorkflowDefinitionVersionItem] = Field(default_factory=list)


class WorkflowDefinitionListQuery(PageParams):
    business_type_code: str | None = None
    org_id: UUID | None = None
    is_active: bool | None = None


class VersionUploadBody(BaseModel):
    definition_id: UUID
    bpmn_xml: str
    bpmn_process_no: str | None = None
    remark: str | None = None


class VersionPublishBody(BaseModel):
    remark: str | None = None


class VersionSaveDesignBody(BaseModel):
    definition_id: UUID
    design: dict
    remark: str | None = None


class VersionPreviewDesignBody(BaseModel):
    business_type_code: str = Field(..., min_length=1, max_length=64)
    design: dict
