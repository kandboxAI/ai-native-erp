"""表模型（sys_menu）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class SysMenu(SQLModel, table=True):
    """菜单：一行为管理端的一个菜单、目录或按钮。"""

    __tablename__ = "sys_menu"
    __table_args__ = (
        Index("uk_sys_menu_menu_key", "menu_key", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '菜单：一行为管理端的一个菜单、目录或按钮。菜单每个租户一份，`menu_key` 对应前端页面组件。'},
    )

    id: UUID = id_field()
    menu_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '菜单标识'})
    menu_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '菜单名称'})
    menu_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '菜单类型；字典 sys_menu_type'})
    parent_id: UUID | None = Field(default=None, foreign_key="sys_menu.id", index=True, nullable=True, sa_column_kwargs={'comment': '上级菜单'})
    path: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '路由路径'})
    component: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '页面组件'})
    icon: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '图标'})
    permission_id: UUID | None = Field(default=None, foreign_key="sys_permission.id", index=True, nullable=True, sa_column_kwargs={'comment': '所需权限'})
    is_external: bool = bool_field('是否外链', default=False)
    external_url: str | None = Field(default=None, max_length=1024, nullable=True, sa_column_kwargs={'comment': '外链地址'})
    open_target_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '打开方式；字典 sys_open_target'})
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    is_visible: bool = bool_field('是否显示', default=True)
    is_active: bool = bool_field('是否启用', default=True)
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class SysUserFavorite(SQLModel, table=True):
    """用户菜单收藏：一行为一个租户用户收藏的一个管理端菜单。"""

    __tablename__ = "sys_user_favorite"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["sys_user.id"],
            name="fk_sys_user_favorite_user_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["menu_id"],
            ["sys_menu.id"],
            name="fk_sys_user_favorite_menu_id",
            ondelete="CASCADE",
        ),
        CheckConstraint("sort_no >= 0", name="sort_no"),
        Index(
            "uk_sys_user_favorite_user_id_menu_id",
            "user_id",
            "menu_id",
            unique=True,
        ),
        Index(
            "uk_sys_user_favorite_user_id_sort_no",
            "user_id",
            "sort_no",
            unique=True,
        ),
        Index("idx_sys_user_favorite_menu_id", "menu_id"),
        {
            "comment": "用户菜单收藏：一行为一个租户用户收藏的一个管理端菜单；顺序由用户维护。"
        },
    )

    id: UUID = id_field()
    user_id: UUID = Field(
        nullable=False,
        sa_column_kwargs={"comment": "收藏用户；引用 sys_user.id"},
    )
    menu_id: UUID = Field(
        nullable=False,
        sa_column_kwargs={"comment": "收藏菜单；引用 sys_menu.id"},
    )
    sort_no: int = Field(
        ge=0,
        nullable=False,
        sa_column_kwargs={"comment": "收藏展示顺序；从 0 开始"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；系统任务创建时为空")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field(
        "扩展字段；租户自定义字段，结构见动态表单定义；默认 {}"
    )
