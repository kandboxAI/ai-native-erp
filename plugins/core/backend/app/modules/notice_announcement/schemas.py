"""公告接口模型（字段名与数据库字段一致）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin

TargetScope = Literal["all", "role", "user", "mixed"]
ReadStatus = Literal["all", "read", "unread"]


def _check_targets(scope: str | None, role_ids: list[UUID] | None, user_ids: list[UUID] | None) -> None:
    if scope == "role" and not role_ids:
        raise ValueError("请选择接收角色")
    if scope == "user" and not user_ids:
        raise ValueError("请选择接收用户")
    if scope == "mixed" and not role_ids and not user_ids:
        raise ValueError("请选择接收角色或用户")


class NoticeBase(BaseModel):
    title: str = Field(..., max_length=256)
    summary: str | None = None
    notice_type_code: str = Field(default="notice", max_length=64)
    is_shown_on_home: bool = False
    status_code: str = Field(default="draft", max_length=64)


class NoticeCreate(NoticeBase):
    org_id: UUID | None = None
    target_scope: TargetScope = "all"
    target_role_ids: list[UUID] = Field(default_factory=list)
    target_user_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _targets(self):
        _check_targets(self.target_scope, self.target_role_ids, self.target_user_ids)
        return self


class NoticeUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    summary: str | None = None
    notice_type_code: str | None = Field(default=None, max_length=64)
    is_shown_on_home: bool | None = None
    status_code: str | None = Field(default=None, max_length=64)
    org_id: UUID | None = None
    target_scope: TargetScope | None = None
    target_role_ids: list[UUID] | None = None
    target_user_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _targets(self):
        if self.target_scope is not None:
            _check_targets(self.target_scope, self.target_role_ids, self.target_user_ids)
        return self


class NoticeListQuery(PageParams):
    notice_type_code: str | None = None
    is_shown_on_home: bool | None = None
    status_code: str | None = None
    org_id: UUID | None = None
    read_status: ReadStatus = "all"


class NoticeReaderListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    read_status: ReadStatus = "all"


class NoticeItem(DisplayDatetimeJsonMixin, NoticeBase):
    __display_datetime_fields__ = ("published_at", "read_at", "created_at", "updated_at")
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    published_by: UUID | None = None
    publisher_name_snapshot: str | None = None
    published_at: datetime | None = None
    target_scope: TargetScope = "all"
    target_role_ids: list[UUID] = Field(default_factory=list)
    target_user_ids: list[UUID] = Field(default_factory=list)
    target_roles: list[dict] = Field(default_factory=list)
    target_users: list[dict] = Field(default_factory=list)
    is_read: bool = False
    read_at: datetime | None = None
    read_count: int = 0
    unread_count: int = 0
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class NoticeReaderItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("read_at",)

    user_id: UUID
    display_name: str
    is_read: bool = False
    read_at: datetime | None = None
