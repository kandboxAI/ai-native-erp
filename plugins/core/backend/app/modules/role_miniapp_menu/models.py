"""表模型（sys_role_miniapp_menu）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class SysRoleMiniappMenu(SQLModel, table=True):
    """角色小程序菜单：一行为一个角色在小程序中可见的一个菜单。"""

    __tablename__ = "sys_role_miniapp_menu"
    __table_args__ = (
        Index("uk_sys_role_miniapp_menu_role_id_miniapp_menu_id", "role_id", "miniapp_menu_id", unique=True),
        {'comment': '角色小程序菜单：一行为一个角色在小程序中可见的一个菜单。'},
    )

    id: UUID = id_field()
    role_id: UUID = Field(foreign_key="sys_role.id", nullable=False, sa_column_kwargs={'comment': '角色'})
    miniapp_menu_id: UUID = Field(foreign_key="sys_miniapp_menu.id", index=True, nullable=False, sa_column_kwargs={'comment': '小程序菜单'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
