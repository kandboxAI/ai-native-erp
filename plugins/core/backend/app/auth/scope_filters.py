"""数据范围过滤（SQLAlchemy 条件）。

1. 租户隔离由 schema 完成（每个租户一个 schema，请求开始时切换 search_path），这里不再按租户过滤。
2. 数据范围：按权限上配置的 data_scope_code（字典 sys_data_scope）过滤：
   - all：本租户全部；
   - organization：用户可访问的组织（org_id；sys_org 表按 id）；
   - department：本部门（department_id），表上没有部门字段时退化为 organization；
   - self：本人（user_id 字段，否则 created_by）；
   - related：关联关系（如班主任与本班学生、家长与子女），由业务模块通过 register_related_scope 按表注册。
代码中不按角色判断。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import false, or_

from app.auth.data_scope import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_DEPARTMENT,
    DATA_SCOPE_ORGANIZATION,
    DATA_SCOPE_RELATED,
    DATA_SCOPE_SELF,
    ORG_ACCESS_ALL,
    effective_data_scope,
    normalize_data_scope,
)
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException

RelatedScopeBuilder = Callable[[Any, AuthenticatedUser], Any]
_RELATED_SCOPE_BUILDERS: dict[str, RelatedScopeBuilder] = {}


def register_related_scope(table_name: str, builder: RelatedScopeBuilder) -> None:
    """登记某张表在 related 数据范围下的过滤条件（由业务模块在导入时调用）。"""
    _RELATED_SCOPE_BUILDERS[table_name] = builder


# ───────── 软删除 ─────────
def alive_condition(table_model):
    """软删除表只取有效数据（deleted_at 为空）。"""
    column = getattr(table_model, "deleted_at", None)
    return None if column is None else column.is_(None)


# ───────── 数据范围 ─────────
def resolve_effective_data_scope(
    current_user: AuthenticatedUser,
    permission_key: str | None = None,
    *,
    scope: str | None = None,
) -> str:
    if scope is not None:
        return normalize_data_scope(scope)
    if permission_key is None:
        raise AppException("permission key is required for data scope evaluation", status_code=status.HTTP_403_FORBIDDEN)
    resolved = effective_data_scope(permission_key, current_user.permission_scopes)
    if resolved is None:
        raise AppException(f"data scope is not configured for permission: {permission_key}", status_code=status.HTTP_403_FORBIDDEN)
    return resolved


def has_global_access(current_user: AuthenticatedUser, permission_key: str | None = None) -> bool:
    """本租户内不受组织限制（数据范围为 all）。"""
    return resolve_effective_data_scope(current_user, permission_key) == DATA_SCOPE_ALL


def has_all_organization_access(current_user: AuthenticatedUser, permission_key: str | None = None) -> bool:
    if current_user.org_access_mode_code == ORG_ACCESS_ALL:
        return True
    return has_global_access(current_user, permission_key)


def accessible_org_ids(current_user: AuthenticatedUser) -> list[UUID]:
    if current_user.org_access_mode_code == ORG_ACCESS_ALL:
        return []
    ids: list[UUID] = []
    for value in [*current_user.org_ids, current_user.org_id]:
        if value is not None and value not in ids:
            ids.append(value)
    return ids


def require_user_id(current_user: AuthenticatedUser) -> UUID:
    return current_user.user_id


def require_org_id(current_user: AuthenticatedUser) -> UUID:
    if current_user.org_id is None:
        raise AppException("current user is not bound to any organization", status_code=status.HTTP_403_FORBIDDEN)
    return current_user.org_id


def require_accessible_org_ids(current_user: AuthenticatedUser) -> list[UUID]:
    if current_user.org_access_mode_code == ORG_ACCESS_ALL:
        return []
    ids = accessible_org_ids(current_user)
    if not ids:
        raise AppException("current user is not bound to any organization", status_code=status.HTTP_403_FORBIDDEN)
    return ids


def require_department_id(current_user: AuthenticatedUser) -> UUID:
    if current_user.department_id is None:
        raise AppException("current user is not bound to any department", status_code=status.HTTP_403_FORBIDDEN)
    return current_user.department_id


def ensure_org_access(current_user: AuthenticatedUser, org_id: UUID | None, permission_key: str | None = None) -> UUID:
    if org_id is None:
        raise AppException("org_id is required", status_code=status.HTTP_400_BAD_REQUEST)
    if has_all_organization_access(current_user, permission_key):
        return org_id
    if org_id not in require_accessible_org_ids(current_user):
        raise AppException("无权访问该组织", status_code=status.HTTP_403_FORBIDDEN)
    return org_id


def resolve_write_org_id(current_user: AuthenticatedUser, org_id: UUID | None, permission_key: str | None = None) -> UUID:
    """写入时确定 org_id：传入的须可访问；未传时用户只能访问一个组织则取它。"""
    if org_id is not None:
        return ensure_org_access(current_user, org_id, permission_key)
    if not has_all_organization_access(current_user, permission_key):
        ids = require_accessible_org_ids(current_user)
        if len(ids) == 1:
            return ids[0]
    if current_user.org_id is not None:
        return current_user.org_id
    raise AppException("请选择所属组织", status_code=status.HTTP_400_BAD_REQUEST)


def org_column_scope_condition(column, current_user: AuthenticatedUser, permission_key: str | None = None):
    if has_all_organization_access(current_user, permission_key):
        return None
    ids = require_accessible_org_ids(current_user)
    return column == ids[0] if len(ids) == 1 else column.in_(ids)


def _owner_column(table_model):
    if hasattr(table_model, "user_id"):
        return table_model.user_id
    return getattr(table_model, "created_by", None)


def _self_scope_condition(table_model, current_user: AuthenticatedUser):
    column = _owner_column(table_model)
    return false() if column is None else column == current_user.user_id


def _related_scope_condition(table_model, current_user: AuthenticatedUser):
    builder = _RELATED_SCOPE_BUILDERS.get(getattr(table_model, "__tablename__", ""))
    return false() if builder is None else builder(table_model, current_user)


def _organization_scope_condition(table_model, current_user: AuthenticatedUser, permission_key: str | None = None):
    if getattr(table_model, "__tablename__", "") == "sys_org":
        return org_column_scope_condition(table_model.id, current_user, permission_key)
    if hasattr(table_model, "org_id"):
        return org_column_scope_condition(table_model.org_id, current_user, permission_key)
    return None


def _department_scope_condition(table_model, current_user: AuthenticatedUser, permission_key: str | None = None):
    if hasattr(table_model, "department_id"):
        return table_model.department_id == require_department_id(current_user)
    return _organization_scope_condition(table_model, current_user, permission_key)


def table_scope_condition(
    table_model,
    current_user: AuthenticatedUser,
    permission_key: str | None = None,
    *,
    data_scope: str | None = None,
):
    """数据范围条件；None 表示本租户内不加过滤。"""
    resolved = resolve_effective_data_scope(current_user, permission_key, scope=data_scope)
    if resolved == DATA_SCOPE_ALL:
        return None
    if resolved == DATA_SCOPE_RELATED:
        return _related_scope_condition(table_model, current_user)
    if resolved == DATA_SCOPE_SELF:
        return _self_scope_condition(table_model, current_user)
    if resolved == DATA_SCOPE_DEPARTMENT:
        return _department_scope_condition(table_model, current_user, permission_key)
    return _organization_scope_condition(table_model, current_user, permission_key)


def scoped_conditions(
    table_model,
    current_user: AuthenticatedUser,
    permission_key: str | None = None,
    *,
    data_scope: str | None = None,
    include_deleted: bool = False,
) -> list[Any]:
    """软删除 + 数据范围，供 Repository 直接 .where(*conditions)。"""
    conditions = []
    if not include_deleted:
        conditions.append(alive_condition(table_model))
    if permission_key is not None or data_scope is not None:
        conditions.append(table_scope_condition(table_model, current_user, permission_key, data_scope=data_scope))
    return [item for item in conditions if item is not None]
