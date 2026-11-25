from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class DictionaryCreate(BaseModel):
    dict_code: str = Field(..., max_length=64, description="字典编码；创建后不可修改")
    dict_name: str = Field(..., max_length=128)
    description: str | None = None
    is_tenant_extensible: bool = True
    is_active: bool = True


class DictionaryUpdate(BaseModel):
    dict_name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    is_tenant_extensible: bool | None = None
    is_active: bool | None = None


class DictionaryListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=500)
    is_active: bool | None = None
    is_tenant_extensible: bool | None = None


class DictionaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dict_code: str
    dict_name: str
    description: str | None = None
    is_tenant_extensible: bool = True
    is_active: bool = True
    is_builtin: bool = False  # 平台内置字典（builtin_dicts），不可删除
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None


class DictionaryEntryListQuery(PageParams):
    """字典项平铺列表：一行一个字典项，带所属字典。"""

    page_size: int = Field(default=10, ge=1, le=500)
    dict_id: UUID | None = None
    dict_code: str | None = Field(default=None, max_length=64)
    item_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class DictionaryEntryRow(BaseModel):
    id: UUID
    dict_id: UUID
    dict_code: str
    dict_name: str
    is_tenant_extensible: bool
    item_code: str
    item_name: str
    sort_no: int | None = None
    is_builtin: bool = False
    is_active: bool = True
    remark: str | None = None
    updated_at: datetime


class DictionaryOption(BaseModel):
    item_code: str
    item_name: str
    sort_no: int | None = None
    is_active: bool = True
