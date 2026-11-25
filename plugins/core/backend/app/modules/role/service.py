from __future__ import annotations

import re
from typing import Any

from fastapi import status

from app.auth.data_scope import DATA_SCOPE_VALUES
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.framework.deployment import blocked_plugin_module_codes
from app.modules.menu.repository import repository as menu_repository
from app.modules.role_permission.repository import repository as role_permission_repository

from .permission_template import build_role_permission_template, parse_template_rows
from .repository import is_builtin_admin, repository
from .schemas import RoleListQuery

ROLE_NO_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_TEMPLATE_IMPORT_BYTES = 8 * 1024 * 1024
MAX_TEMPLATE_IMPORT_ROWS = 1000
SAMPLE_TEMPLATE_ROLE = {
    "role_no": "test_role",
    "role_name": "测试角色",
    "description": "示例角色，可直接改成需要的新角色",
    "data_scope_code": "organization",
    "menu_keys": [],
    "permission_keys": [],
}


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    data = {}
    for key in ("role_no", "role_name", "description", "data_scope_code", "is_active"):
        if key in payload:
            value = payload[key]
            data[key] = value.strip() if isinstance(value, str) else value
    return data


def _validate(role_no: str, role_name: str, data_scope_code: str) -> None:
    if not ROLE_NO_PATTERN.fullmatch(role_no or ""):
        raise AppException("角色编号只能使用小写字母、数字、下划线，且以小写字母开头")
    if not role_name:
        raise AppException("角色名称不能为空")
    if data_scope_code not in DATA_SCOPE_VALUES:
        raise AppException("数据范围无效")


class RoleService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def list(self, params: RoleListQuery) -> dict[str, Any]:
        async with self.session_getter() as session:
            return await repository.list(session, params)

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def permission_config(self, item_id: str, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            return await repository.permission_config(session, item_id, blocked_plugin_module_codes(current_user.enabled_plugin_keys))

    async def create(self, payload: dict[str, Any], current_user: AuthenticatedUser):
        data = _clean(payload)
        _validate(data.get("role_no", ""), data.get("role_name", ""), data.get("data_scope_code", ""))
        async with self.session_getter() as session:
            if await repository.exists_by_no(session, data["role_no"]):
                raise AppException("角色编号已存在", status_code=status.HTTP_409_CONFLICT)
            role = await repository.create(session, data, current_user)
            return await repository.detail(session, role.id)

    async def update(self, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        data = _clean(payload)
        async with self.session_getter() as session:
            role = await repository.get(session, item_id, for_update=True)
            if role is None:
                return None
            if role.is_builtin:
                if "role_no" in data and data["role_no"] != role.role_no:
                    raise AppException("内置角色的编号不可修改", status_code=status.HTTP_403_FORBIDDEN)
                if data.get("is_active") is False:
                    raise AppException("内置角色不可停用", status_code=status.HTTP_403_FORBIDDEN)
                if is_builtin_admin(role) and data.get("data_scope_code", role.data_scope_code) != role.data_scope_code:
                    raise AppException("内置管理员的数据范围不可修改", status_code=status.HTTP_403_FORBIDDEN)
            _validate(
                data.get("role_no", role.role_no),
                data.get("role_name", role.role_name),
                data.get("data_scope_code", role.data_scope_code),
            )
            if "role_no" in data and await repository.exists_by_no(session, data["role_no"], exclude_id=role.id):
                raise AppException("角色编号已存在", status_code=status.HTTP_409_CONFLICT)
            if data:
                await repository.update(session, role, data, current_user)
            return await repository.detail(session, role.id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        async with self.session_getter() as session:
            role = await repository.get(session, item_id, for_update=True)
            if role is None:
                return False
            if role.is_builtin:
                raise AppException("内置角色不可删除", status_code=status.HTTP_403_FORBIDDEN)
            if await repository.count_users(session, role.id):
                raise AppException("角色已分配给用户，请先解除后再删除", status_code=status.HTTP_409_CONFLICT)
            await repository.soft_delete(session, role, current_user)
            return True

    async def build_permission_template(self, current_user: AuthenticatedUser, *, include_existing_roles: bool = False) -> bytes:
        async with self.session_getter() as session:
            data = await repository.permission_template_data(session)
            visible_menu_ids = await menu_repository.visible_menu_ids(session, set(current_user.enabled_plugin_keys))
            allowed_menus = {row["menu_key"] for row in data["menus"] if row["id"] in visible_menu_ids}
            blocked = blocked_plugin_module_codes(current_user.enabled_plugin_keys)
            data["menus"] = [row for row in data["menus"] if row["menu_key"] in allowed_menus]
            data["permissions"] = [row for row in data["permissions"] if row["module_code"] not in blocked]
            allowed_permissions = {row["permission_key"] for row in data["permissions"]}
            for role in data["roles"]:
                role["menu_keys"] = [key for key in role["menu_keys"] if key in allowed_menus]
                role["permission_keys"] = [key for key in role["permission_keys"] if key in allowed_permissions]
                role["permission_scopes"] = {key: scope for key, scope in role["permission_scopes"].items() if key in allowed_permissions}
        return build_role_permission_template(
            roles=data["roles"] if include_existing_roles else [SAMPLE_TEMPLATE_ROLE],
            menus=data["menus"],
            permissions=data["permissions"],
        )

    @staticmethod
    def _validate_template_rows(rows, refs: dict[str, dict[str, Any]]) -> None:
        errors: list[str] = []
        seen: set[str] = set()
        if not rows:
            errors.append("角色信息中没有可导入的数据")
        if len(rows) > MAX_TEMPLATE_IMPORT_ROWS:
            errors.append(f"单次导入最多 {MAX_TEMPLATE_IMPORT_ROWS} 个角色")
        for item in rows:
            prefix = f"第 {item.row_number} 行"
            if not ROLE_NO_PATTERN.fullmatch(item.role_no or ""):
                errors.append(f"{prefix}：角色编号只能使用小写字母、数字、下划线，且必须以小写字母开头")
            elif item.role_no in seen:
                errors.append(f"{prefix}：角色编号 {item.role_no} 在模板中重复")
            seen.add(item.role_no)
            existing = refs["roles"].get(item.role_no)
            if existing is not None and is_builtin_admin(existing):
                errors.append(f"{prefix}：内置管理员角色不能通过导入修改")
            if not item.role_name:
                errors.append(f"{prefix}：角色名称不能为空")
            if item.data_scope_code not in DATA_SCOPE_VALUES:
                errors.append(f"{prefix}：默认数据范围无效")
            errors.extend(f"{prefix}：菜单不存在或不可配置：{key}" for key in item.menu_keys if key not in refs["menus"])
            for key, scope in item.permission_scopes.items():
                if key not in refs["permissions"]:
                    errors.append(f"{prefix}：权限标识不存在：{key}")
                if scope not in DATA_SCOPE_VALUES:
                    errors.append(f"{prefix}：权限 {key} 的数据范围无效")
            if len(errors) > 50:
                break
        if errors:
            suffix = f"；另有 {len(errors) - 20} 个错误" if len(errors) > 20 else ""
            raise AppException(f"导入失败：{'；'.join(errors[:20])}{suffix}")

    async def import_permission_template(self, content: bytes, current_user: AuthenticatedUser):
        if not content:
            raise AppException("请上传 Excel 模板文件")
        if len(content) > MAX_TEMPLATE_IMPORT_BYTES:
            raise AppException("模板文件不能超过 8MB")
        rows = parse_template_rows(content)
        async with self.session_getter() as session:
            refs = await repository.permission_template_import_reference(session)
            visible_menu_ids = await menu_repository.visible_menu_ids(session, set(current_user.enabled_plugin_keys))
            blocked = blocked_plugin_module_codes(current_user.enabled_plugin_keys)
            visible_permission_ids = await role_permission_repository.allowed_permission_ids(
                session, list(refs["permissions"].values()), blocked
            )
            refs["menus"] = {key: value for key, value in refs["menus"].items() if value in visible_menu_ids}
            refs["permissions"] = {key: value for key, value in refs["permissions"].items() if value in visible_permission_ids}
            self._validate_template_rows(rows, refs)
            return await repository.import_permission_template(session, rows, current_user, visible_menu_ids, visible_permission_ids)


service = RoleService(session_getter=get_session_context)
