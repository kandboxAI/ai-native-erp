from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy import Text, and_, case, cast, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.catalog import miniapp_menu_display_group, miniapp_menu_group_aliases
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository

from .models import SysMiniappMenu
from .schemas import MiniappMenuItem


async def ensure_catalog_entries(session, definitions, *, previous_names=None):
    """开通/显式补齐模块菜单；保留租户对已有菜单的名称、路径和启停设置。"""
    from sqlmodel import select as model_select
    rows = []
    for definition in definitions:
        row = (await session.exec(model_select(SysMiniappMenu).where(
            SysMiniappMenu.portal_code == definition.portal_code,
            SysMiniappMenu.menu_key == definition.menu_key,
            SysMiniappMenu.deleted_at.is_(None)))).first()
        if row is None:
            row = SysMiniappMenu(portal_code=definition.portal_code, menu_key=definition.menu_key,
                menu_name=definition.menu_name, path=definition.path, group_key=definition.group_key,
                group_name=definition.group_name, sort_no=definition.sort_no)
            session.add(row)
        elif row.menu_name == (previous_names or {}).get(definition.menu_key):
            row.menu_name = definition.menu_name
        if (row.group_key, row.group_name) in definition.previous_groups:
            row.group_key, row.group_name = definition.group_key, definition.group_name
        rows.append(row)
    await session.flush()
    return rows


async def retire_catalog_entry(session, portal_code, menu_key, path, *, actor_id=None):
    from app.framework.db.models import utc_now

    await session.execute(update(SysMiniappMenu).where(
        SysMiniappMenu.portal_code == portal_code, SysMiniappMenu.menu_key == menu_key,
        SysMiniappMenu.path == path, SysMiniappMenu.deleted_at.is_(None), SysMiniappMenu.is_active.is_(True),
    ).values(is_active=False, updated_at=utc_now(), updated_by=actor_id))


async def merge_catalog_entry(session, definition, *, previous_key, previous_path):
    from sqlmodel import select as model_select
    from app.framework.db.models import utc_now
    from app.modules.role_miniapp_menu.models import SysRoleMiniappMenu

    menu, = await ensure_catalog_entries(session, [definition])
    if menu.path == previous_path:
        menu.path = definition.path
        menu.updated_at = utc_now()

    previous = (await session.exec(model_select(SysMiniappMenu).where(
        SysMiniappMenu.portal_code == definition.portal_code,
        SysMiniappMenu.menu_key == previous_key,
        SysMiniappMenu.deleted_at.is_(None),
    ))).first()
    if previous is None:
        return

    grants = model_select(SysRoleMiniappMenu.role_id)
    existing = set((await session.exec(grants.where(SysRoleMiniappMenu.miniapp_menu_id == menu.id))).all())
    old_roles = (await session.exec(grants.where(SysRoleMiniappMenu.miniapp_menu_id == previous.id))).all()
    session.add_all(SysRoleMiniappMenu(role_id=role_id, miniapp_menu_id=menu.id)
                    for role_id in old_roles if role_id not in existing)
    previous.is_active = False
    previous.deleted_at = previous.updated_at = utc_now()
    await session.flush()


async def normalize_miniapp_menu_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysMiniappMenu | None,
) -> dict[str, Any]:
    data = dict(payload)
    if entity is not None:
        for key in ("portal_code", "menu_key"):
            if key in data and data[key] != getattr(entity, key):
                raise AppException("门户与菜单标识创建后不可修改", status_code=status.HTTP_400_BAD_REQUEST)
    for key in ("menu_key", "menu_name", "group_key", "group_name", "path"):
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip() or None
    if entity is None:
        from app.modules.dictionary.models import SysDict
        from app.modules.dictionary_item.models import SysDictItem
        portal = await session.scalar(select(SysDictItem.id).join(SysDict, SysDictItem.dict_id == SysDict.id).where(
            SysDict.dict_code == "sys_miniapp_portal", SysDict.is_active.is_(True), SysDict.deleted_at.is_(None),
            SysDictItem.item_code == data.get("portal_code"), SysDictItem.is_active.is_(True), SysDictItem.deleted_at.is_(None)))
        if portal is None:
            raise AppException("门户不存在或已停用，请检查系统字典", status_code=400)
        if not data.get("menu_key") or not data.get("menu_name"):
            raise AppException("菜单标识与名称不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        duplicate = (
            await session.exec(
                select(SysMiniappMenu.id).where(
                    SysMiniappMenu.portal_code == data["portal_code"],
                    SysMiniappMenu.menu_key == data["menu_key"],
                    SysMiniappMenu.deleted_at.is_(None),
                )
            )
        ).first()
        if duplicate is not None:
            raise AppException("同一门户下菜单标识已存在", status_code=status.HTTP_409_CONFLICT)
    return data


class MiniappMenuRepository(SqlModelCrudRepository):
    def _group_column(self, name: str):
        column = getattr(SysMiniappMenu, name)
        index = 0 if name == "group_key" else 1
        aliases = miniapp_menu_group_aliases()
        if not aliases:
            return column
        return case(*[
            (and_(SysMiniappMenu.menu_key == key,
                  SysMiniappMenu.group_key == old_key,
                  SysMiniappMenu.group_name == old_name), current[index])
            for (key, old_key, old_name), current in aliases.items()
        ], else_=column)

    def _search_expressions(self, params):
        # 存储仍为旧默认值时，关键字搜索与响应显示使用同一分组口径。
        if not params.keyword:
            return []
        return [
            cast(self._group_column(name) if name in ("group_key", "group_name")
                 else getattr(self.table_model, name), Text).ilike(f"%{params.keyword}%")
            for name in self.searchable_columns
        ]

    def _filter_conditions(self, params):
        filters = params.model_dump(exclude_none=True)
        return [
            (self._group_column(name) if name == "group_key" else getattr(SysMiniappMenu, name)) == filters[name]
            for name in self.filterable_columns if name in filters
        ]

    def _parse_entity(self, entity: SysMiniappMenu) -> MiniappMenuItem:
        item = super()._parse_entity(entity)
        item.group_key, item.group_name = miniapp_menu_display_group(
            entity.menu_key, entity.group_key, entity.group_name,
        )
        return item


repository = MiniappMenuRepository(
    table_model=SysMiniappMenu,
    item_model=MiniappMenuItem,
    writable_columns=["portal_code", "menu_key", "menu_name", "group_key", "group_name", "path", "sort_no", "is_active"],
    searchable_columns=["menu_key", "menu_name", "group_key", "group_name", "path"],
    filterable_columns=["portal_code", "group_key", "is_active"],
    create_payload_normalizer=normalize_miniapp_menu_payload,
    update_payload_normalizer=normalize_miniapp_menu_payload,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="miniapp_menu",
)
