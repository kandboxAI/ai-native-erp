from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams

MenuTypeCode = Literal["directory", "menu", "button"]  # 字典 sys_menu_type
OpenTargetCode = Literal["self", "blank", "iframe"]  # 字典 sys_open_target


class MenuWritable(BaseModel):
    menu_name: str = Field(..., max_length=128)
    menu_type_code: MenuTypeCode = "menu"
    parent_id: UUID | None = None
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=128)
    permission_id: UUID | None = None
    permission_key: str | None = Field(default=None, max_length=128, description="可代替 permission_id 传入")
    is_external: bool = False
    external_url: str | None = Field(default=None, max_length=1024)
    open_target_code: OpenTargetCode | None = "self"
    sort_no: int | None = None
    is_visible: bool = True
    is_active: bool = True
    remark: str | None = None
    flex_form: dict[str, Any] = Field(default_factory=dict)


class MenuCreate(MenuWritable):
    menu_key: str = Field(..., max_length=128, description="菜单标识；创建后不可修改")


class MenuUpdate(BaseModel):
    """menu_key 创建后不可修改。"""

    menu_name: str | None = Field(default=None, max_length=128)
    menu_type_code: MenuTypeCode | None = None
    parent_id: UUID | None = None
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=128)
    permission_id: UUID | None = None
    permission_key: str | None = Field(default=None, max_length=128)
    is_external: bool | None = None
    external_url: str | None = Field(default=None, max_length=1024)
    open_target_code: OpenTargetCode | None = None
    sort_no: int | None = None
    is_visible: bool | None = None
    is_active: bool | None = None
    remark: str | None = None
    flex_form: dict[str, Any] | None = None


class MenuListQuery(PageParams):
    page_size: int = Field(default=10, ge=1, le=1000)
    parent_id: UUID | None = None
    menu_type_code: MenuTypeCode | None = None
    is_external: bool | None = None
    is_visible: bool | None = None
    is_active: bool | None = None


class MenuItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None = None
    menu_key: str
    menu_name: str
    menu_type_code: str
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission_id: UUID | None = None
    permission_key: str | None = None
    is_external: bool = False
    external_url: str | None = None
    open_target_code: str | None = None
    sort_no: int | None = None
    is_visible: bool = True
    is_active: bool = True
    remark: str | None = None
    flex_form: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None = None


class MenuTreeItem(MenuItem):
    children: list["MenuTreeItem"] = Field(default_factory=list)
