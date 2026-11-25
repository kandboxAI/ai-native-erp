"""表模型（sys_miniapp_menu）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)


class SysMiniappMenu(SQLModel, table=True):
    """小程序菜单：一行为小程序某个门户中的一个菜单项。"""

    __tablename__ = "sys_miniapp_menu"
    __table_args__ = (
        Index("uk_sys_miniapp_menu_portal_code_menu_key", "portal_code", "menu_key", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '小程序菜单：一行为小程序某个门户中的一个菜单项。'},
    )

    id: UUID = id_field()
    portal_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '门户；字典 sys_miniapp_portal'})
    menu_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '菜单标识；门户内唯一'})
    menu_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '菜单名称'})
    group_key: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '分组标识'})
    group_name: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '分组名称'})
    path: str | None = Field(default=None, max_length=512, nullable=True, sa_column_kwargs={'comment': '页面路径'})
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class SysUserMiniappFavorite(SQLModel, table=True):
    """用户小程序常用菜单：一行为一个租户用户固定的一个小程序入口。"""

    __tablename__ = "sys_user_miniapp_favorite"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["sys_user.id"],
            name="fk_sys_user_miniapp_favorite_user_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["miniapp_menu_id"],
            ["sys_miniapp_menu.id"],
            name="fk_sys_user_miniapp_favorite_miniapp_menu_id",
            ondelete="CASCADE",
        ),
        CheckConstraint("sort_no >= 0", name="sort_no_nonnegative"),
        Index(
            "uk_sys_user_miniapp_favorite_user_id_miniapp_menu_id",
            "user_id",
            "miniapp_menu_id",
            unique=True,
        ),
        Index(
            "uk_sys_user_miniapp_favorite_user_id_sort_no",
            "user_id",
            "sort_no",
            unique=True,
        ),
        Index("idx_sys_user_miniapp_favorite_miniapp_menu_id", "miniapp_menu_id"),
        {
            "comment": "用户小程序常用菜单：一行为一个租户用户固定的一个小程序入口；数量不设业务上限，顺序由用户维护。"
        },
    )

    id: UUID = id_field()
    user_id: UUID = Field(
        nullable=False,
        sa_column_kwargs={"comment": "收藏用户；引用 sys_user.id"},
    )
    miniapp_menu_id: UUID = Field(
        nullable=False,
        sa_column_kwargs={"comment": "小程序菜单；引用 sys_miniapp_menu.id"},
    )
    sort_no: int = Field(
        ge=0,
        nullable=False,
        sa_column_kwargs={"comment": "常用菜单展示顺序；从 0 开始"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；系统任务创建时为空")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field(
        "扩展字段；租户自定义字段，结构见动态表单定义；默认 {}"
    )


class SysMiniappBanner(SQLModel, table=True):
    """小程序首页轮播配置；图片通过文件模块按本记录绑定，不存外部 URL。"""

    __tablename__ = "sys_miniapp_banner"
    __table_args__ = (
        CheckConstraint("sort_no >= 0", name="sort_no_nonnegative"),
        Index("idx_sys_miniapp_banner_org_id_is_active_sort_no", "org_id", "is_active", "sort_no"),
        {"comment": "小程序首页轮播：一行为一个组织的轮播图片配置；图片由 file_attachment 多态绑定，业务类型 sys_miniapp_banner、场景 miniapp_banner。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    image_file_id: UUID = Field(foreign_key="file_attachment.id", ondelete="RESTRICT", index=True,
                               nullable=False, sa_column_kwargs={"comment": "当前展示的轮播图片；引用 file_attachment.id；敏感级别：内部，按组织可见"})
    # 历史兼容列：业务已停用标题，保留原列定义；新建由 Repository 写入空字符串。
    title: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "图片标题；用于管理和无障碍展示，不包含敏感信息"})
    sort_no: int = Field(default=0, ge=0, nullable=False, sa_column_kwargs={"comment": "轮播排序；数值越小越靠前", "server_default": text("0")})
    is_active: bool = bool_field("是否启用；停用后不在小程序展示", default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；引用 sys_user.id", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；引用 sys_user.id", ondelete="SET NULL")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；引用 sys_user.id", ondelete="SET NULL")
    flex_form: dict[str, Any] = flex_form_field()
