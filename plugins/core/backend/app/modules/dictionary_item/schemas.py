from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class DictionaryItemCreate(BaseModel):
    dict_id: UUID
    item_code: str = Field(..., max_length=64)
    item_name: str = Field(..., max_length=128)
    sort_no: int | None = None
    is_active: bool = True
    remark: str | None = None


class DictionaryItemUpdate(BaseModel):
    """内置项（is_builtin）不可修改编码，不可删除，只能停用。"""

    item_code: str | None = Field(default=None, max_length=64)
    item_name: str | None = Field(default=None, max_length=128)
    sort_no: int | None = None
    is_active: bool | None = None
    remark: str | None = None


class DictionaryItemListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=500)
    dict_id: UUID | None = None
    is_active: bool | None = None
    is_builtin: bool | None = None


class DictionaryItemItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dict_id: UUID
    item_code: str
    item_name: str
    sort_no: int | None = None
    is_builtin: bool = False
    is_active: bool = True
    remark: str | None = None
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None
