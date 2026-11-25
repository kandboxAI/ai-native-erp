from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BannerSave(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    file_id: UUID
    sort_no: int = Field(default=0, ge=0, le=999999)
    is_active: bool = Field(default=True, strict=True)


class BannerImage(BaseModel):
    id: UUID
    file_name: str
    url: str
    width: int | None = None
    height: int | None = None


class BannerItem(BaseModel):
    id: UUID
    org_id: UUID
    sort_no: int
    is_active: bool
    image: BannerImage | None = None
