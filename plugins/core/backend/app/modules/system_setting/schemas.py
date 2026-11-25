from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import DisplayDatetimeJsonMixin

ValueTypeCode = Literal["string", "number", "boolean", "json"]  # 字典 sys_value_type


class SystemSettingUpdate(BaseModel):
    """setting_key 由代码定义，不可修改。"""

    setting_name: str | None = Field(default=None, max_length=128)
    setting_value: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


class SystemSettingCreate(BaseModel):  # 仅为路由签名；参数由代码定义，不开放新增
    setting_key: str = Field(..., max_length=128)


class SystemSettingListQuery(PageParams):
    page_size: int = Field(default=50, ge=1, le=200)
    setting_group_code: str | None = None
    is_active: bool | None = None


class SystemSettingItem(DisplayDatetimeJsonMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    setting_key: str
    setting_name: str
    setting_value: str | None = None
    value_type_code: str
    setting_group_code: str | None = None
    description: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None
