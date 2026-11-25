from __future__ import annotations

from uuid import UUID

from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.catalog import can_access_miniapp_menu, miniapp_menu_display_group, miniapp_menu_display_name
from app.framework.db.session import get_session_context
from app.framework.deployment import miniapp_menu_plugin_owner
from app.modules.miniapp_menu.schemas import MINIAPP_PORTALS
from app.modules.role.repository import is_builtin_admin

from .repository import repository
from .schemas import (
    CurrentMiniappMenuConfig,
    RoleMiniappMenuBatchSync,
    RoleMiniappMenuCreate,
    RoleMiniappMenuListQuery,
    RoleMiniappMenuRoleConfig,
)

BUILTIN_ADMIN_MESSAGE = "内置管理员可见全部小程序菜单，不能减少"


async def grant_for_permission(session, menu_id, permission_key):
    """租户开通/显式补齐菜单授权；复用角色已有业务权限。"""
    from .repository import grant_for_permission as grant
    await grant(session, menu_id, permission_key)


async def ensure_default_grants(session, menu_id, role_nos):
    """模块开通显式补齐菜单；调用方负责事务，不替代运行时权限和关系校验。"""
    from .repository import ensure_default_grants as grant
    await grant(session, menu_id, role_nos)


def _group(menus) -> list[dict]:
    groups: list[dict] = []
    index: dict[str | None, dict] = {}
    for menu in menus:
        group_key, group_name = miniapp_menu_display_group(menu.menu_key, menu.group_key, menu.group_name)
        group = index.get(group_key)
        if group is None:
            group = {"group_key": group_key, "group_name": group_name, "items": []}
            index[group_key] = group
            groups.append(group)
        group["items"].append({
            "id": str(menu.id),
            "menu_key": menu.menu_key,
            "menu_name": miniapp_menu_display_name(menu.menu_key, menu.menu_name),
            "path": menu.path,
        })
    return groups


def _enabled_menus(menus, current_user: AuthenticatedUser):
    enabled = set(current_user.enabled_plugin_keys)
    permissions = set(current_user.permissions)
    return [
        menu
        for menu in menus
        if ((owner := miniapp_menu_plugin_owner(menu.menu_key)) is None or owner in enabled)
        and can_access_miniapp_menu(menu.portal_code, menu.menu_key, permissions)
    ]


class RoleMiniappMenuService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    async def _require_role(self, session, role_id: UUID):
        role = await repository.get_role(session, role_id)
        if role is None:
            raise AppException("角色不存在", status_code=status.HTTP_404_NOT_FOUND)
        return role

    async def catalog(self, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            menus = _enabled_menus(await repository.active_menus(session), current_user)
        return {"portals": {portal: _group([m for m in menus if m.portal_code == portal]) for portal in MINIAPP_PORTALS}}

    async def current_user_menus(self, current_user: AuthenticatedUser, portal_code: str) -> CurrentMiniappMenuConfig:
        """当前用户（按其角色）在指定门户可见的小程序菜单。"""
        async with self.session_getter() as session:
            allowed = await repository.menu_ids_for_user(session, current_user.user_id)
            menus = [m for m in _enabled_menus(await repository.active_menus(session), current_user) if m.portal_code == portal_code and m.id in allowed]
        return CurrentMiniappMenuConfig(portal_code=portal_code, menu_keys=[m.menu_key for m in menus], groups=_group(menus))

    async def role_config(self, role_id: UUID, current_user: AuthenticatedUser) -> RoleMiniappMenuRoleConfig:
        async with self.session_getter() as session:
            role = await self._require_role(session, role_id)
            selected = await repository.menu_ids_for_role(session, role.id)
            menus = [m for m in _enabled_menus(await repository.active_menus(session), current_user) if m.id in selected]
        by_portal: dict[str, list[str]] = {portal: [] for portal in MINIAPP_PORTALS}
        for menu in menus:
            by_portal.setdefault(menu.portal_code, []).append(menu.menu_key)
        return RoleMiniappMenuRoleConfig(role_id=role.id, miniapp_menu_ids=[m.id for m in menus], menu_keys_by_portal=by_portal)

    async def list(self, params: RoleMiniappMenuListQuery) -> dict:
        async with self.session_getter() as session:
            return await repository.list(session, params)

    async def detail(self, item_id: str):
        async with self.session_getter() as session:
            return await repository.detail(session, item_id)

    async def create(self, payload: RoleMiniappMenuCreate, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            visible_ids = {menu.id for menu in _enabled_menus(await repository.active_menus(session), current_user)}
            if payload.miniapp_menu_id not in visible_ids:
                raise AppException("小程序菜单不存在或所属能力包未启用")
            if payload.miniapp_menu_id in await repository.menu_ids_for_role(session, role.id):
                raise AppException("该角色已有此小程序菜单", status_code=status.HTTP_409_CONFLICT)
            rows = await repository.add(session, role.id, [payload.miniapp_menu_id], current_user)
            await session.commit()
            return await repository.detail(session, rows[0].id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        del current_user
        async with self.session_getter() as session:
            binding = await repository.get(session, item_id)
            if binding is None:
                return False
            if is_builtin_admin(await self._require_role(session, binding.role_id)):
                raise AppException(BUILTIN_ADMIN_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.delete_binding(session, binding)
            await session.commit()
            return True

    async def batch_sync(self, payload: RoleMiniappMenuBatchSync, current_user: AuthenticatedUser) -> dict[str, int]:
        targets = set(payload.miniapp_menu_ids)
        async with self.session_getter() as session:
            role = await self._require_role(session, payload.role_id)
            valid = {menu.id for menu in _enabled_menus(await repository.active_menus(session), current_user)}
            missing = [str(mid) for mid in targets if mid not in valid]
            if missing:
                raise AppException(f"小程序菜单不存在：{', '.join(missing)}")
            existing = await repository.menu_ids_for_role(session, role.id)
            to_remove, to_add = (existing & valid) - targets, targets - existing
            if is_builtin_admin(role) and to_remove:
                raise AppException(BUILTIN_ADMIN_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
            await repository.remove(session, role.id, to_remove)
            await repository.add(session, role.id, to_add, current_user)
            await session.commit()
            return {"added": len(to_add), "removed": len(to_remove), "total": len(targets)}


service = RoleMiniappMenuService(session_getter=get_session_context)
