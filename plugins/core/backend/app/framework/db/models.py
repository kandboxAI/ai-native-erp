"""ORM 公共定义：约束命名约定与标准字段（数据库命名与建模规范 §8、§16）。

- 每个租户一个 schema（t_<租户编号>），业务表不含 tenant_id、不写 schema，由当前请求的 search_path 定位到租户 schema；
  只有认证表与租户目录写 schema="public"。
- 主键统一 UUIDv7：应用生成（uuid7），数据库默认值 uuidv7() 兜底。
- 时间点统一 timestamptz；写入使用带时区的当前时间 utc_now()。
- 标准字段：org_id、created_at/by、updated_at/by、deleted_at/by、flex_form。
- 外键字段建索引；审计字段（created_by / updated_by / deleted_by）不建索引（规范 §12）。
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.ids import uuid7

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uk_%(table_name)s_%(column_0_N_name)s",
    "ix": "idx_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

# 所有表模型共用 SQLModel.metadata；在任何表模型定义之前设置命名约定
SQLModel.metadata.naming_convention = NAMING_CONVENTION

AUDIT_COLUMNS = frozenset({"created_by", "updated_by", "deleted_by"})


def utc_now() -> datetime:
    return datetime.now(UTC)


def _comment(label: str) -> dict[str, Any]:
    return {"comment": label}


def id_field() -> Any:
    return Field(
        default_factory=uuid7,
        primary_key=True,
        sa_column_kwargs={"server_default": text("uuidv7()"), **_comment("主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底")},
    )


def org_field(*, index: bool = True, ondelete: Literal["CASCADE", "SET NULL", "RESTRICT"] | None = None) -> Any:
    options = {"ondelete": ondelete} if ondelete is not None else {}
    return Field(foreign_key="sys_org.id", index=index, sa_column_kwargs=_comment("所属组织；学校或校区；数据范围按它过滤"), **options)


def created_at_field() -> Any:
    return Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": text("now()"), **_comment("创建时间")},
    )


def updated_at_field() -> Any:
    return Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": text("now()"), "onupdate": utc_now, **_comment("修改时间")},
    )


def deleted_at_field() -> Any:
    return Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs=_comment("删除时间；软删除；有效数据为空"))


def audit_user_field(comment: str, *, target: str = "sys_user.id", ondelete: Literal["CASCADE", "SET NULL", "RESTRICT"] | None = None) -> Any:
    """created_by / updated_by / deleted_by：声明外键，不建索引。"""
    options = {"ondelete": ondelete} if ondelete is not None else {}
    return Field(default=None, foreign_key=target, sa_column_kwargs=_comment(comment), **options)


def flex_form_field(comment: str = "扩展字段；租户自定义字段，结构见动态表单定义；默认 {}") -> Any:
    return Field(
        default_factory=dict,
        sa_type=JSONB,
        nullable=False,
        sa_column_kwargs={"server_default": text("'{}'::jsonb"), **_comment(comment)},
    )


def bool_field(comment: str, *, default: bool = False) -> Any:
    return Field(
        default=default,
        sa_type=Boolean,
        nullable=False,
        sa_column_kwargs={"server_default": text("true" if default else "false"), **_comment(comment)},
    )


__all__ = [
    "AUDIT_COLUMNS",
    "NAMING_CONVENTION",
    "UUID",
    "audit_user_field",
    "bool_field",
    "created_at_field",
    "deleted_at_field",
    "flex_form_field",
    "id_field",
    "org_field",
    "updated_at_field",
    "utc_now",
    "uuid7",
]
