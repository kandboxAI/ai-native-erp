from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class SupplierCategoryCreate(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True


class SupplierCategoryUpdate(BaseModel):
    category_name: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None


class SupplierCategoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_name: str
    is_active: bool
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class SupplierCategoryListQuery(PageParams):
    is_active: bool | None = None
