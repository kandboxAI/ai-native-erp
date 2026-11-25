from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_menu.models import SysRoleMenu
from app.modules.user_role.models import SysUserRole
from app.modules.navigation.repository import RETIRED_MENU_KEYS
from app.framework.deployment import is_menu_enabled, menu_plugin_owner
from app.framework.catalog import default_menu_permissions, menu_display_component, menu_display_icon, menu_display_name, embedded_menu_owners, retired_menu_keys, menu_display_parent_definitions, single_tag_menu_paths
from app.framework.menu_composition import compose_menus

from .models import SysMenu
from .schemas import MenuItem

WRITABLE_COLUMNS = [
    "menu_key",
    "menu_name",
    "menu_type_code",
    "parent_id",
    "path",
    "component",
    "icon",
    "permission_id",
    "permission_key",
    "is_external",
    "external_url",
    "open_target_code",
    "sort_no",
    "is_visible",
    "is_active",
    "remark",
    "flex_form",
]


async def normalize_menu_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysMenu | None,
) -> dict[str, Any]:
    data = dict(payload)
    if entity is not None and "menu_key" in data and data["menu_key"] != entity.menu_key:
        raise AppException("菜单标识创建后不可修改", status_code=status.HTTP_400_BAD_REQUEST)
    if entity is None:
        menu_key = str(data.get("menu_key") or "").strip()
        if not menu_key:
            raise AppException("菜单标识不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        exists = await session.scalar(
            select(func.count()).select_from(SysMenu).where(SysMenu.menu_key == menu_key, SysMenu.deleted_at.is_(None))
        )
        if exists:
            raise AppException("菜单标识已存在", status_code=status.HTTP_409_CONFLICT)
        data["menu_key"] = menu_key

    permission_key = data.pop("permission_key", None)
    if permission_key:
        permission_id = await session.scalar(
            select(SysPermission.id).where(SysPermission.permission_key == permission_key.strip(), SysPermission.deleted_at.is_(None))
        )
        if permission_id is None:
            raise AppException(f"权限不存在：{permission_key}", status_code=status.HTTP_400_BAD_REQUEST)
        data["permission_id"] = permission_id
    elif data.get("permission_id") is not None:
        found = await session.get(SysPermission, data["permission_id"])
        if found is None or found.deleted_at is not None:
            raise AppException("权限不存在", status_code=status.HTTP_400_BAD_REQUEST)

    is_external = data.get("is_external", getattr(entity, "is_external", False))
    external_url = data.get("external_url", getattr(entity, "external_url", None))
    if is_external and not external_url:
        raise AppException("外链菜单必须填写外链地址", status_code=status.HTTP_400_BAD_REQUEST)

    parent_id = data.get("parent_id")
    if parent_id is not None:
        current: UUID | None = UUID(str(parent_id))
        seen: set[UUID] = set()
        while current is not None and current not in seen:
            if entity is not None and current == entity.id:
                raise AppException("上级菜单不能是自己或自己的下级", status_code=status.HTTP_400_BAD_REQUEST)
            seen.add(current)
            parent = await session.get(SysMenu, current)
            if parent is None or parent.deleted_at is not None:
                raise AppException("上级菜单不存在", status_code=status.HTTP_400_BAD_REQUEST)
            current = parent.parent_id
    return data


def _node(row: SysMenu, permission_keys: dict[UUID, str]) -> dict[str, Any]:
    item = MenuItem.model_validate(row)
    item.menu_name = menu_display_name(row.menu_key, row.menu_name)
    item.icon = menu_display_icon(row.menu_key, row.icon)
    if not row.is_external and row.deleted_at is None:
        item.component = menu_display_component(row.menu_key, row.path, row.component, row.menu_type_code)
    item.permission_key = permission_keys.get(row.permission_id) if row.permission_id else None
    return {**item.model_dump(mode="json"), "children": []}


def build_tree(rows: list[SysMenu], permission_keys: dict[UUID, str], *, embedded_owners=None, single_tag_paths=None) -> list[dict[str, Any]]:
    nodes = {row.id: _node(row, permission_keys) for row in rows}
    visible_owners = {row.menu_key: row for row in rows if row.is_active and row.is_visible and row.path}
    for row in rows:
        node = nodes[row.id]
        if (row.path and row.path == (single_tag_paths or {}).get(row.menu_key)
                and row.menu_type_code == "menu" and not row.is_external):
            node.setdefault("flex_form", {}).setdefault("route", {}).setdefault("meta", {})["dynamicLevel"] = 1
        owner = visible_owners.get((embedded_owners or {}).get(row.menu_key))
        if owner is not None:
            # 子配置保留路由和原授权；只有主入口也已授权时才折叠导航。
            node['is_visible'] = False
            flex = node.setdefault('flex_form', {})
            flex.setdefault('route', {}).setdefault('meta', {})['activePath'] = owner.path
    roots: list[dict[str, Any]] = []
    for row in rows:
        if row.parent_id is not None and row.parent_id in nodes:
            nodes[row.parent_id]["children"].append(nodes[row.id])
        else:
            roots.append(nodes[row.id])
    return roots


def display_parent_rows(rows: list[SysMenu]) -> list[SysMenu]:
    """只复制授权导航中的历史默认挂载；祖先授权使用投影后的树计算。"""
    definitions = menu_display_parent_definitions()
    by_id, by_key = {row.id: row for row in rows}, {row.menu_key: row for row in rows}
    result = []
    for row in rows:
        definition = definitions.get(row.menu_key)
        old_parent = by_id.get(row.parent_id)
        old_key = old_parent.menu_key if old_parent else None
        target = by_key.get(definition.parent_key) if definition else None
        if (definition and target and target.id != row.id and target.menu_type_code == "directory"
                and old_key in definition.previous_parent_keys and row.path == definition.path
                and row.component in (definition.component, *definition.previous_components)
                and row.menu_type_code == definition.menu_type_code and not row.is_external):
            # 目标祖先链必须有效且不形成循环；缺失时保留原入口。
            current, seen, valid = target, {row.id}, False
            while current is not None and current.id not in seen:
                seen.add(current.id)
                if current.parent_id is None:
                    valid = True
                    break
                current = by_id.get(current.parent_id)
            if valid:
                values = {"parent_id": target.id}
                if row.sort_no in definition.previous_sort_nos:
                    values["sort_no"] = definition.sort_no
                row = row.model_copy(update=values)
        result.append(row)
    return result


def visible_menu_rows(
    rows: list[SysMenu],
    profile: str | None = None,
    permission_module_codes: dict[UUID, str] | None = None,
    enabled_plugin_keys: set[str] | None = None,
) -> list[SysMenu]:
    """按能力包归属过滤已有目录，并隐藏挂在已移除目录下的自定义菜单。"""

    module_codes = permission_module_codes or {}
    blocked = {
        row.id for row in rows
        if row.menu_key in RETIRED_MENU_KEYS or row.menu_key in retired_menu_keys()
        or not is_menu_enabled(row.menu_key, profile, module_codes.get(row.permission_id))
        or (
            enabled_plugin_keys is not None
            and (owner := menu_plugin_owner(row.menu_key, module_codes.get(row.permission_id))) is not None
            and owner not in enabled_plugin_keys
        )
    }
    while True:
        descendants = {row.id for row in rows if row.parent_id in blocked}
        if descendants <= blocked:
            break
        blocked.update(descendants)
    return [row for row in rows if row.id not in blocked]


class MenuRepository(SqlModelCrudRepository):
    async def upgrade_legacy_page(self, session, definition, *, previous_component, previous_permission_key,
                                  obsolete_route_meta, user_id) -> bool:
        """只替换指定页面的已知默认组件/权限；保留菜单 ID、角色绑定和自定义配置。"""
        from app.framework.db.models import utc_now

        row = (await session.execute(select(SysMenu).where(SysMenu.menu_key == definition.key,
            SysMenu.path == definition.path, SysMenu.deleted_at.is_(None)).with_for_update())).scalars().first()
        if row is None or row.menu_type_code != "menu" or row.is_external or row.component not in (previous_component, definition.component):
            return False
        current_permission = await session.get(SysPermission, row.permission_id) if row.permission_id else None
        replace_permission = row.permission_id is None or (current_permission is not None and current_permission.permission_key == previous_permission_key)
        target_permission = None
        if replace_permission:
            target_permission = (await session.execute(select(SysPermission).where(
                SysPermission.permission_key == definition.permission_key, SysPermission.deleted_at.is_(None),
                SysPermission.is_active.is_(True)))).scalars().first()
            if target_permission is None:
                raise AppException("页面新权限尚未配置，请先同步插件权限目录", status_code=status.HTTP_409_CONFLICT)
        changed = False
        if row.component == previous_component and row.component != definition.component:
            row.component = definition.component
            changed = True
        if target_permission is not None and row.permission_id != target_permission.id:
            row.permission_id = target_permission.id
            changed = True
        flex = dict(row.flex_form or {})
        route = dict(flex.get("route") or {})
        meta = dict(route.get("meta") or {})
        removable = [key for key, value in obsolete_route_meta.items() if key in meta and meta[key] == value]
        if removable:
            for key in removable:
                del meta[key]
            if meta:
                route["meta"] = meta
            else:
                route.pop("meta", None)
            if route:
                flex["route"] = route
            else:
                flex.pop("route", None)
            row.flex_form = flex
            changed = True
        if changed:
            row.updated_at, row.updated_by = utc_now(), user_id
        return changed

    async def hide_legacy_entry(self, session, menu_key, expected_path, user_id) -> bool:
        """保留旧路由、授权和 ID，仅收起重复导航入口。"""
        from app.framework.db.models import utc_now

        row = (await session.execute(select(SysMenu).where(SysMenu.menu_key == menu_key,
            SysMenu.deleted_at.is_(None)).with_for_update())).scalars().first()
        if row is None or row.menu_type_code != "menu" or row.path != expected_path or not row.is_visible:
            return False
        row.is_visible = False
        row.updated_at, row.updated_by = utc_now(), user_id
        await session.flush()
        return True

    async def retire_empty_directory(self, session, menu_key, expected_path, user_id) -> bool:
        """显式退役旧目录；不删除授权或收藏，不影响仍有子菜单的自定义目录。"""
        from app.framework.db.models import utc_now

        row = (await session.execute(select(SysMenu).where(SysMenu.menu_key == menu_key,
            SysMenu.deleted_at.is_(None)).with_for_update())).scalars().first()
        if row is None or row.menu_type_code != "directory" or row.path != expected_path or row.component:
            return False
        children = await session.scalar(select(func.count()).select_from(SysMenu).where(
            SysMenu.parent_id == row.id, SysMenu.deleted_at.is_(None)))
        if children or not (row.is_active or row.is_visible):
            return False
        row.is_active = row.is_visible = False
        row.updated_at, row.updated_by = utc_now(), user_id
        await session.flush()
        return True

    """菜单每个租户一份，属于系统配置，不按组织数据范围过滤。"""

    async def _permission_keys(self, session: AsyncSession, permission_ids) -> dict[UUID, str]:
        ids = [pid for pid in set(permission_ids) if pid]
        if not ids:
            return {}
        rows = (await session.exec(select(SysPermission.id, SysPermission.permission_key).where(SysPermission.id.in_(ids)))).all()
        return {row[0]: row[1] for row in rows}

    async def _with_permission_key(self, session: AsyncSession, item):
        if item is not None and item.permission_id:
            item.permission_key = (await self._permission_keys(session, [item.permission_id])).get(item.permission_id)
        return item

    async def list(self, session, params, current_user) -> dict[str, Any]:
        result = await super().list(session, params, current_user)
        keys = await self._permission_keys(session, [UUID(i["permission_id"]) for i in result["items"] if i.get("permission_id")])
        for item in result["items"]:
            if item.get("permission_id"):
                item["permission_key"] = keys.get(UUID(item["permission_id"]))
        return result

    async def detail(self, session, item_id, current_user):
        return await self._with_permission_key(session, await super().detail(session, item_id, current_user))

    async def create(self, session, payload, current_user):
        return await self._with_permission_key(session, await super().create(session, payload, current_user))

    async def update(self, session, item_id, payload, current_user):
        return await self._with_permission_key(session, await super().update(session, item_id, payload, current_user))

    async def delete(self, session, item_id, current_user) -> bool:
        children = await session.scalar(
            select(func.count()).select_from(SysMenu).where(SysMenu.parent_id == self._normalize_id(item_id), SysMenu.deleted_at.is_(None))
        )
        if children:
            raise AppException("请先删除下级菜单", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)

    async def _all_alive(self, session: AsyncSession, enabled_plugin_keys: set[str] | None = None) -> list[SysMenu]:
        statement = select(SysMenu).where(SysMenu.deleted_at.is_(None)).order_by(SysMenu.sort_no.nulls_last(), SysMenu.created_at)
        rows = list((await session.exec(statement)).scalars().all())
        permission_ids = {row.permission_id for row in rows if row.permission_id}
        module_codes: dict[UUID, str] = {}
        if permission_ids:
            module_codes = {
                permission_id: module_code
                for permission_id, module_code in (
                    await session.exec(
                        select(SysPermission.id, SysPermission.module_code).where(SysPermission.id.in_(permission_ids))
                    )
                ).all()
            }
        return visible_menu_rows(rows, permission_module_codes=module_codes, enabled_plugin_keys=enabled_plugin_keys)

    async def visible_menu_ids(self, session: AsyncSession, enabled_plugin_keys: set[str]) -> set[UUID]:
        return {row.id for row in await self._all_alive(session, enabled_plugin_keys)}

    async def tree(self, session: AsyncSession, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        rows = await self._all_alive(session, set(current_user.enabled_plugin_keys))
        return build_tree(rows, await self._permission_keys(session, [row.permission_id for row in rows]))

    async def tree_for_user(self, session: AsyncSession, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        """当前用户角色已授权且启用的菜单路由树（含隐藏页面、不含按钮）。"""
        authorized = await self.authorized_rows_for_user(session, current_user)
        roots = build_tree(authorized, await self._permission_keys(session, [row.permission_id for row in authorized]),
                           embedded_owners=embedded_menu_owners(), single_tag_paths=single_tag_menu_paths())
        roots = compose_menus(roots, set(current_user.enabled_plugin_keys))
        return _prune_empty_directories(roots)

    async def authorized_rows_for_user(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
    ) -> list[SysMenu]:
        """查询当前用户已授权菜单及其有效祖先，供菜单树和用户收藏共同复用。"""
        granted = set(
            (
                await session.exec(
                    select(SysRoleMenu.menu_id)
                    .join(SysUserRole, SysUserRole.role_id == SysRoleMenu.role_id)
                    .join(SysRole, SysRole.id == SysRoleMenu.role_id)
                    .where(
                        SysUserRole.user_id == current_user.user_id,
                        SysRole.is_active.is_(True),
                        SysRole.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        rows = [
            row for row in await self._all_alive(session, set(current_user.enabled_plugin_keys))
            if row.is_active and row.menu_type_code != "button"
        ]
        defaults = default_menu_permissions()
        granted.update(row.id for row in rows
                       if set(defaults.get(row.menu_key, ())).intersection(current_user.permissions))
        rows = display_parent_rows(rows)
        by_id = {row.id: row for row in rows}
        allowed: set[UUID] = set()
        for menu_id in granted:
            current = by_id.get(menu_id)
            chain: list[UUID] = []
            while current is not None:
                chain.append(current.id)
                if current.parent_id is None:
                    allowed.update(chain)
                    break
                current = by_id.get(current.parent_id)  # 上级停用时整条链不下发
        return [row for row in rows if row.id in allowed]


def _prune_empty_directories(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for node in nodes:
        node["children"] = _prune_empty_directories(node["children"])
        if node["menu_type_code"] == "directory" and not node["children"]:
            continue
        result.append(node)
    return result


repository = MenuRepository(
    table_model=SysMenu,
    item_model=MenuItem,
    writable_columns=WRITABLE_COLUMNS,
    searchable_columns=["menu_key", "menu_name", "path", "external_url", "remark"],
    filterable_columns=["parent_id", "menu_type_code", "is_external", "is_visible", "is_active"],
    create_payload_normalizer=normalize_menu_payload,
    update_payload_normalizer=normalize_menu_payload,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="menu",
)
