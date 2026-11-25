from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.framework.datetime_pydantic import CoerceDatetimeQueryMixin, DisplayDatetimeJsonMixin


class OperationLogListQuery(CoerceDatetimeQueryMixin):
    __coerce_datetime_fields__ = ("created_start", "created_end")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None
    actor_name: str | None = Field(default=None, max_length=128)
    actor_user_id: UUID | None = None
    ip_address: str | None = Field(default=None, max_length=64)
    module_code: str | None = Field(default=None, max_length=64)
    action_code: str | None = Field(default=None, max_length=64)
    org_id: UUID | None = None
    sensitive_only: bool = False
    target_type_code: str | None = Field(default=None, max_length=64)
    target_id: UUID | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    successful: bool | None = None
    created_start: datetime | None = None
    created_end: datetime | None = None


class OperationLogItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("created_at",)

    id: UUID
    org_id: UUID
    module_code: str
    action_code: str
    target_type_code: str | None = None
    target_id: UUID | None = None
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    is_agent_action: bool = False
    is_sensitive: bool = False
    request_id: UUID | None = None
    request_method: str | None = None
    request_path: str | None = None
    http_status: int | None = None
    content: str | None = None
    ip_address: str | None = None
    created_at: datetime
