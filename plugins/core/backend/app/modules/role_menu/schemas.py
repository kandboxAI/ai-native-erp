from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams


class RoleMenuCreate(BaseModel):
    role_id: UUID
    menu_id: UUID


class RoleMenuBatchSync(BaseModel):
    role_id: UUID
    menu_ids: list[UUID] = Field(default_factory=list)


class RoleMenuListQuery(PageParams):
    page_size: int = Field(default=500, ge=1, le=2000)
    role_id: UUID | None = None
    menu_id: UUID | None = None


class RoleMenuItem(BaseModel):
    id: UUID
    role_id: UUID
    menu_id: UUID
    role_no: str
    role_name: str
    menu_key: str
    menu_name: str
    menu_type_code: str
    created_at: datetime
