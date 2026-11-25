from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.pagination import PageParams


class UserOrgCreate(BaseModel):
    """为用户额外授权一个可访问的组织（用户的组织访问方式须为 assigned 才生效）。"""

    user_id: UUID
    org_id: UUID


class UserOrgListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    user_id: UUID | None = None
    org_id: UUID | None = None


class UserOrgItem(BaseModel):
    id: UUID
    user_id: UUID
    org_id: UUID
    display_name: str
    org_name: str
    access_type_code: str
    is_primary: bool
    created_at: datetime
