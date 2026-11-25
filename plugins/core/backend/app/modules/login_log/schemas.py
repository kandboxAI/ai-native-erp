from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.framework.datetime_pydantic import CoerceDatetimeQueryMixin, DisplayDatetimeJsonMixin


class LoginLogListQuery(CoerceDatetimeQueryMixin):
    __coerce_datetime_fields__ = ("created_start", "created_end")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None
    login_name: str | None = Field(default=None, max_length=128)
    ip_address: str | None = Field(default=None, max_length=64)
    is_success: bool | None = None
    created_start: datetime | None = None
    created_end: datetime | None = None


class LoginLogItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("created_at",)

    id: UUID
    auth_user_id: UUID | None = None
    user_id: UUID | None = None  # 本租户内用户
    display_name: str | None = None
    login_name: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    is_success: bool = False
    message: str | None = None
    created_at: datetime
