from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams


class UserRoleCreate(BaseModel):
    user_id: UUID
    role_id: UUID


class UserRoleListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    user_id: UUID | None = None
    role_id: UUID | None = None


class UserRoleItem(BaseModel):
    id: UUID
    user_id: UUID
    role_id: UUID
    display_name: str
    role_no: str
    role_name: str
    created_at: datetime
