"""租户开通模板：登记租户、建出租户 schema，并生成该租户的基础数据。

由 scripts/bootstrap.py 调用（本地开发使用配置指定的默认租户）；以后做 SaaS 时，
“开通租户”的接口也调用这里。可以重复执行：只补齐缺少的字典项、权限、菜单，并把全部权限和菜单授予内置管理员，
不覆盖租户已修改的名称、配置和密码。

步骤：
1. public：登记租户（auth_tenant），创建管理员登录账号（auth_user）与成员关系（auth_membership）；
2. 创建租户 schema 并升级到最新版本（Alembic tenant 迁移）；
3. 租户 schema：内置字典、根组织、权限、菜单、小程序菜单、内置管理员角色、管理员用户；
4. 各模块的开通步骤：app/modules/<模块>/tenant_setup.py 中的 ``async def setup_tenant(session, ctx)``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import AuthMembership, AuthTenant, AuthUser
from app.auth.password import hash_password
from app.auth.tenants import list_tenants  # noqa: F401 - 供 bootstrap 等沿用 tenant_template.list_tenants
from app.core.config import tenant_schema_name, validate_tenant_no
from app.framework.catalog import (
    MenuDef,
    collect_catalog,
    compatible_menu_component,
    iter_module_attr,
    miniapp_menu_display_name,
)
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.db.tenant import use_tenant_schema
from app.framework.plugin import loaded_plugin_manifests
from app.modules.dictionary.builtin_dicts import builtin_dict_specs
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.masterdata.models import MdParty, MdPerson
from app.modules.menu.models import SysMenu
from app.modules.miniapp_menu.models import SysMiniappMenu
from app.modules.organization.models import SysOrg
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_menu.models import SysRoleMenu
from app.modules.role_miniapp_menu.models import SysRoleMiniappMenu
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_profile.models import SysUser, SysUserOrg
from app.modules.user_role.models import SysUserRole

BACKEND_DIR = Path(__file__).resolve().parents[3]
BUILTIN_ADMIN_ROLE_NO = "admin"  # 仅用于首次创建内置管理员角色；之后按 is_builtin 识别，代码不按角色编号判断权限


@dataclass(frozen=True)
class TenantSpec:
    tenant_no: str
    tenant_name: str
    org_no: str
    org_name: str
    admin_email: str
    admin_password: str
    admin_display_name: str = "管理员"
    org_type_code: str = "organization"


@dataclass
class TenantContext:
    """开通过程中各模块可以使用的信息。"""

    tenant: AuthTenant
    schema: str
    root_org_id: UUID
    admin_user_id: UUID
    admin_role_id: UUID


# ───────── 1. public ─────────
async def _ensure_public(session: AsyncSession, spec: TenantSpec) -> tuple[AuthTenant, AuthUser]:
    tenant_no = validate_tenant_no(spec.tenant_no)
    tenant = (await session.exec(select(AuthTenant).where(AuthTenant.tenant_no == tenant_no))).scalars().first()
    if tenant is None:
        tenant = AuthTenant(tenant_no=tenant_no, tenant_name=spec.tenant_name, schema_name=tenant_schema_name(tenant_no))
        session.add(tenant)
    email = spec.admin_email.strip().lower()
    admin = (await session.exec(select(AuthUser).where(AuthUser.email == email))).scalars().first()
    if admin is None:
        admin = AuthUser(
            email=email,
            password_hash=hash_password(spec.admin_password),
            is_email_verified=True,
            password_changed_at=utc_now(),
        )
        session.add(admin)
    await session.flush()
    membership = (
        await session.exec(
            select(AuthMembership).where(AuthMembership.auth_user_id == admin.id, AuthMembership.tenant_id == tenant.id)
        )
    ).scalars().first()
    if membership is None:
        session.add(AuthMembership(auth_user_id=admin.id, tenant_id=tenant.id))
    await session.commit()
    return tenant, admin


# ───────── 2. 租户 schema ─────────
def tenant_alembic_config(schema: str):
    """解析所有保留的插件迁移，共用租户 alembic_version。"""
    from app.framework.plugin_migrations import plugin_migration_config
    return plugin_migration_config(schema)


def upgrade_tenant_schema(schema: str, plugin_keys: set[str] | None = None) -> None:
    """升级底座及当前组合/指定插件；保留组合外插件的已执行历史。"""
    from alembic import command
    from app.framework.plugin_migrations import tenant_upgrade_targets

    targets = tenant_upgrade_targets(plugin_keys)
    from app.framework.environment_migrations import environment_active, selected_scopes, upgrade_environment_scope
    if plugin_keys is not None or environment_active(schema):
        for scope in selected_scopes(plugin_keys):
            if scope != "public":
                upgrade_environment_scope(schema, scope)
        return
    config = tenant_alembic_config(schema)
    for target in targets:
        command.upgrade(config, target)


def upgrade_public_schema() -> None:
    from alembic import command
    from alembic.config import Config

    from app.framework.environment_migrations import environment_active, upgrade_environment_scope
    if environment_active("public"):
        upgrade_environment_scope("public", "public")
    else:
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini"), ini_section="public"), "head")


# ───────── 3. 租户 schema 中的基础数据 ─────────
async def _sync_dicts(session: AsyncSession, *, retire_missing: bool = True) -> None:
    """内置字典：缺少的字典与内置项补齐；租户改过的名称不覆盖。"""
    existing = {item.dict_code: item for item in (await session.exec(select(SysDict))).scalars().all()}
    for spec in builtin_dict_specs():
        dict_row = existing.get(spec["dict_code"])
        if dict_row is None:
            dict_row = SysDict(
                dict_code=spec["dict_code"],
                dict_name=spec["dict_name"],
                is_tenant_extensible=spec["scope"] == "tenant",
            )
            session.add(dict_row)
            await session.flush()
        codes = set(
            (await session.exec(select(SysDictItem.item_code).where(SysDictItem.dict_id == dict_row.id))).scalars().all()
        )
        for sort_no, (item_code, item_name) in enumerate(spec["items"], start=1):
            if item_code not in codes:
                session.add(
                    SysDictItem(dict_id=dict_row.id, item_code=item_code, item_name=item_name, sort_no=sort_no, is_builtin=True)
                )
        # 平台已去掉的内置项：停用（不删除，历史数据仍可显示标签）；租户自己加的项不动
        if not retire_missing:
            continue
        retired = {item_code for item_code, _ in spec["items"]}
        for item in (
            await session.exec(
                select(SysDictItem).where(
                    SysDictItem.dict_id == dict_row.id,
                    SysDictItem.is_builtin.is_(True),
                    SysDictItem.is_active.is_(True),
                    SysDictItem.item_code.not_in(retired),
                )
            )
        ).scalars().all():
            item.is_active = False


async def _ensure_root_org(session: AsyncSession, spec: TenantSpec) -> SysOrg:
    org = (
        await session.exec(select(SysOrg).where(SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None)).order_by(SysOrg.created_at))
    ).scalars().first()
    if org is None:
        org = SysOrg(org_no=spec.org_no, org_name=spec.org_name, org_type_code=spec.org_type_code, sort_no=1)
        session.add(org)
        await session.flush()
    return org


def relocate_catalog_menu(row: SysMenu, item: MenuDef, menus: dict[str, SysMenu], menus_by_id: dict[UUID, SysMenu]) -> bool:
    """目录调整了菜单层级时，移动已开通租户中未被手工调整的菜单；返回是否移动。

    只有菜单仍挂在目录以前声明过的上级（``previous_parent_keys``）时才移动，并同时采用目录中的排序；
    租户手工移到其他位置的菜单不动。
    """
    parent = menus_by_id.get(row.parent_id) if row.parent_id else None
    if row.parent_id and parent is None:
        return False
    current_parent_key = parent.menu_key if parent else None
    if current_parent_key == item.parent_key or current_parent_key not in item.previous_parent_keys:
        return False
    target = menus.get(item.parent_key) if item.parent_key else None
    if item.parent_key and (target is None or target.deleted_at is not None):
        return False
    row.parent_id = target.id if target else None
    row.sort_no = item.sort_no
    return True


def resort_catalog_menu(row: SysMenu, item: MenuDef, menus_by_id: dict[UUID, SysMenu]) -> bool:
    """菜单仍在目录声明的上级且使用旧默认排序时，更新为新的默认排序。"""
    parent = menus_by_id.get(row.parent_id) if row.parent_id else None
    if row.parent_id and parent is None:
        return False
    current_parent_key = parent.menu_key if parent else None
    if current_parent_key != item.parent_key or row.sort_no not in item.previous_sort_nos:
        return False
    row.sort_no = item.sort_no
    return True


def convert_catalog_menu_to_directory(row: SysMenu, item: MenuDef) -> bool:
    """只将已声明的历史页面转换为目录，保留原菜单 ID、授权及租户定制。"""
    if (
        item.menu_type_code != "directory"
        or item.component is not None
        or row.menu_type_code != "menu"
        or row.component not in item.previous_components
        or row.path != item.path
        or row.is_external
        or row.deleted_at is not None
    ):
        return False
    row.menu_type_code = "directory"
    row.component = None
    return True


def upgrade_catalog_page_defaults(row: SysMenu, item: MenuDef, permissions: dict) -> None:
    """同路径页面仅升级已声明的旧默认值，不覆盖学校自定义路由。"""
    if not (item.previous_permission_keys or item.previous_route_meta or item.previous_redirects):
        return
    if row.path != item.path or row.is_external or row.deleted_at is not None:
        return
    previous_ids = {permissions[key].id for key in item.previous_permission_keys if key in permissions}
    if row.permission_id in previous_ids and item.permission_key in permissions:
        row.permission_id = permissions[item.permission_key].id
    flex = dict(row.flex_form or {})
    route = dict(flex.get("route") or {})
    meta = dict(route.get("meta") or {})
    target = (item.flex_form or {}).get("route") or {}
    target_meta = target.get("meta") or {}
    for key, previous in item.previous_route_meta.items():
        if key in meta and meta[key] in previous:
            if key in target_meta:
                meta[key] = target_meta[key]
            else:
                meta.pop(key)
    if route.get("redirect") in item.previous_redirects:
        if "redirect" in target:
            route["redirect"] = target["redirect"]
        else:
            route.pop("redirect", None)
    route["meta"] = meta
    flex["route"] = route
    row.flex_form = flex


async def _sync_permissions_and_menus(session: AsyncSession, *, catalog=None) -> tuple[list[UUID], list[UUID], list[UUID], list[UUID]]:
    """按各模块 catalog 补齐权限、菜单、小程序菜单；返回全部有效的权限、菜单、小程序菜单 ID。"""
    catalog = collect_catalog() if catalog is None else catalog

    permissions = {row.permission_key: row for row in (await session.exec(select(SysPermission))).scalars().all()}
    for item in catalog.permissions:
        if item.key not in permissions:
            row = SysPermission(permission_key=item.key, permission_name=item.name, module_code=item.module_code)
            session.add(row)
            permissions[item.key] = row
    # 多个开发分支共享租户库，本地 catalog 不是完整目录。
    # 这里只补齐缺失项；权限停用由显式操作处理，不能将本地未知项自动停用。
    await session.flush()

    menus = {row.menu_key: row for row in (await session.exec(select(SysMenu))).scalars().all()}
    created: set[str] = set()
    for item in catalog.menus:
        if item.key in menus:
            row = menus[item.key]
            upgrade_catalog_page_defaults(row, item, permissions)
            convert_catalog_menu_to_directory(row, item)
            if not row.is_external and row.deleted_at is None:
                row.component = compatible_menu_component(item, row.path, row.component, row.menu_type_code)
            # 只更新明确声明的历史默认值；租户手工调整的菜单配置不覆盖。
            if row.menu_name in item.previous_names:
                row.menu_name = item.name
            if row.icon in item.previous_icons:
                row.icon = item.icon
            if not row.path and item.path:
                row.path = item.path
            if not row.component and item.component:
                row.component = item.component
            # 权限键同样只补空值：catalog 后来才绑上的权限键（如收费菜单）对已有租户生效，
            # 已经绑定过的（无论来源）不动，避免覆盖学校在后台手工调整的可见性。
            if not row.permission_id and item.permission_key:
                permission_row = permissions.get(item.permission_key)
                if permission_row is not None:
                    row.permission_id = permission_row.id
            current_flex = dict(row.flex_form or {})
            catalog_route = dict((item.flex_form or {}).get("route") or {})
            if catalog_route:
                current_route = dict(current_flex.get("route") or {})
                if not current_route:
                    current_flex["route"] = catalog_route
                else:
                    for key, value in catalog_route.items():
                        if key == "meta" and isinstance(value, dict):
                            current_meta = dict(current_route.get("meta") or {})
                            for meta_key, meta_value in value.items():
                                current_meta.setdefault(meta_key, meta_value)
                            current_route["meta"] = current_meta
                        else:
                            current_route.setdefault(key, value)
                    current_flex["route"] = current_route
                row.flex_form = current_flex
            continue
        created.add(item.key)
        row = SysMenu(
            menu_key=item.key,
            menu_name=item.name,
            menu_type_code=item.menu_type_code,
            path=item.path,
            component=item.component,
            icon=item.icon,
            permission_id=permissions[item.permission_key].id if item.permission_key else None,
            is_external=item.is_external,
            external_url=item.external_url,
            open_target_code=item.open_target_code,
            sort_no=item.sort_no,
            is_visible=item.is_visible,
            flex_form=item.flex_form,
        )
        session.add(row)
        menus[item.key] = row
    await session.flush()
    for item in catalog.menus:  # 只设置本次新建菜单的上级；已有菜单可能被租户调整过，不覆盖
        if item.key in created and item.parent_key:
            menus[item.key].parent_id = menus[item.parent_key].id
    menus_by_id = {row.id: row for row in menus.values()}
    for item in catalog.menus:
        if item.key not in created:
            row = menus[item.key]
            if not relocate_catalog_menu(row, item, menus, menus_by_id):
                resort_catalog_menu(row, item, menus_by_id)

    miniapp = {(row.portal_code, row.menu_key): row for row in (await session.exec(select(SysMiniappMenu))).scalars().all()}
    for item in catalog.miniapp_menus:
        if (item.portal_code, item.menu_key) not in miniapp:
            row = SysMiniappMenu(
                portal_code=item.portal_code,
                menu_key=item.menu_key,
                menu_name=item.menu_name,
                group_key=item.group_key,
                group_name=item.group_name,
                path=item.path,
                sort_no=item.sort_no,
            )
            session.add(row)
            miniapp[(item.portal_code, item.menu_key)] = row
    # 只持久化目录声明过的历史默认名称和分组，也兼容旧门户的同一菜单。
    miniapp_definitions = {item.menu_key: item for item in catalog.miniapp_menus}
    for row in miniapp.values():
        definition = miniapp_definitions.get(row.menu_key)
        if row.deleted_at is not None or definition is None:
            continue
        row.menu_name = miniapp_menu_display_name(row.menu_key, row.menu_name)
        if (row.group_key, row.group_name) in definition.previous_groups:
            row.group_key, row.group_name = definition.group_key, definition.group_name
    await session.flush()

    alive = lambda rows: [row.id for row in rows if row.deleted_at is None and row.is_active]  # noqa: E731
    return (
        alive(permissions.values()),
        alive(menus.values()),
        alive(miniapp.values()),
        [menus[key].id for key in created],
    )


async def _grant_new_menus_by_permissions(session: AsyncSession, menu_ids: list[UUID]) -> None:
    """按已有接口权限或所属列表页给普通角色补本次新增菜单。

    只处理刚由 catalog 创建的菜单，避免重复执行 bootstrap 时把租户管理员主动
    移除的旧菜单重新授予。隐藏详情页的上级已授权时会随之补授。
    """
    if not menu_ids:
        return

    # 原页面变为目录后，已有目录授权不能顺带授予需要更高读取权限的新功能。
    # 无绑定权限的旧业务和隐藏详情仍沿用原父菜单继承规则。
    catalog = collect_catalog()
    converted_directories = {item.key for item in catalog.menus if item.previous_components and item.menu_type_code == "directory"}
    permission_only = {
        item.key for item in catalog.menus
        if (
            item.parent_key in converted_directories
            or bool(item.flex_form.get("route", {}).get("meta", {}).get("embeddedIn"))
        ) and item.permission_key and item.is_visible
    }

    roles = list(
        (
            await session.exec(
                select(SysRole).where(
                    SysRole.is_builtin.is_(False),
                    SysRole.is_active.is_(True),
                    SysRole.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    if not roles:
        return

    role_ids = [role.id for role in roles]
    permissions_by_role: dict[UUID, set[UUID]] = {role_id: set() for role_id in role_ids}
    for role_id, permission_id in (
        await session.exec(
            select(SysRolePermission.role_id, SysRolePermission.permission_id).where(
                SysRolePermission.role_id.in_(role_ids)
            )
        )
    ).all():
        permissions_by_role[role_id].add(permission_id)

    menus = list((await session.exec(select(SysMenu).where(SysMenu.id.in_(menu_ids)))).scalars().all())
    specs = {item.key: item for item in catalog.menus}
    extra_permissions = {
        key for menu in menus for key in getattr(specs.get(menu.menu_key), "auto_grant_permissions_any", ())
    }
    extra_permission_ids = dict(
        (await session.exec(select(SysPermission.permission_key, SysPermission.id).where(
            SysPermission.permission_key.in_(extra_permissions)
        ))).all()
    ) if extra_permissions else {}
    existing = set(
        (
            await session.exec(
                select(SysRoleMenu.role_id, SysRoleMenu.menu_id).where(
                    SysRoleMenu.role_id.in_(role_ids),
                )
            )
        ).all()
    )
    menu_ids_by_role: dict[UUID, set[UUID]] = {role_id: set() for role_id in role_ids}
    for role_id, menu_id in existing:
        menu_ids_by_role[role_id].add(menu_id)
    session.add_all(
        SysRoleMenu(role_id=role.id, menu_id=menu.id)
        for role in roles
        for menu in menus
        if (
            menu.permission_id in permissions_by_role[role.id]
            or (menu.menu_key not in permission_only and menu.parent_id is not None and menu.parent_id in menu_ids_by_role[role.id])
        )
        and (
            not getattr(specs.get(menu.menu_key), "auto_grant_permissions_any", ())
            or any(extra_permission_ids.get(key) in permissions_by_role[role.id]
                   for key in specs[menu.menu_key].auto_grant_permissions_any)
        )
        and (role.id, menu.id) not in existing
    )


async def _ensure_builtin_admin_role(session: AsyncSession) -> SysRole:
    role = (
        await session.exec(
            select(SysRole)
            .where(SysRole.is_builtin.is_(True), SysRole.data_scope_code == "all", SysRole.deleted_at.is_(None))
            .order_by(SysRole.created_at)
        )
    ).scalars().first()
    if role is None:
        role = SysRole(
            role_no=BUILTIN_ADMIN_ROLE_NO,
            role_name="管理员",
            description="内置管理员：拥有全部权限，数据范围为全部；不可删除",
            data_scope_code="all",
            is_builtin=True,
        )
        session.add(role)
        await session.flush()
    return role


async def _grant_all(session: AsyncSession, role: SysRole, permission_ids, menu_ids, miniapp_menu_ids) -> None:
    async def existing(model, column):
        return set((await session.exec(select(column).where(model.role_id == role.id))).scalars().all())

    have = await existing(SysRolePermission, SysRolePermission.permission_id)
    session.add_all(SysRolePermission(role_id=role.id, permission_id=pid) for pid in permission_ids if pid not in have)
    have = await existing(SysRoleMenu, SysRoleMenu.menu_id)
    session.add_all(SysRoleMenu(role_id=role.id, menu_id=mid) for mid in menu_ids if mid not in have)
    have = await existing(SysRoleMiniappMenu, SysRoleMiniappMenu.miniapp_menu_id)
    session.add_all(SysRoleMiniappMenu(role_id=role.id, miniapp_menu_id=mid) for mid in miniapp_menu_ids if mid not in have)


async def _ensure_admin_user(session: AsyncSession, admin: AuthUser, spec: TenantSpec, org: SysOrg, role: SysRole) -> SysUser:
    user = (await session.exec(select(SysUser).where(SysUser.auth_user_id == admin.id, SysUser.deleted_at.is_(None)))).scalars().first()
    if user is None:
        user = SysUser(org_id=org.id, auth_user_id=admin.id, display_name=spec.admin_display_name, org_access_mode_code="all")
        session.add(user)
        await session.flush()
        party = MdParty(party_type_code="person", display_name=spec.admin_display_name)
        session.add(party)
        await session.flush()
        session.add(MdPerson(party_id=party.id, full_name=spec.admin_display_name, user_id=user.id))
        session.add(SysUserOrg(org_id=org.id, user_id=user.id, access_type_code="primary", is_primary=True))
    has_role = (
        await session.exec(select(SysUserRole).where(SysUserRole.user_id == user.id, SysUserRole.role_id == role.id))
    ).scalars().first()
    if has_role is None:
        session.add(SysUserRole(user_id=user.id, role_id=role.id))
    return user


async def _sync_catalog(session: AsyncSession, *, retire_missing_dict_items: bool = True) -> SysRole:
    """内置字典、权限、菜单补齐，并授予内置管理员。"""
    await _sync_dicts(session, retire_missing=retire_missing_dict_items)
    permission_ids, menu_ids, miniapp_menu_ids, new_menu_ids = await _sync_permissions_and_menus(session)
    role = await _ensure_builtin_admin_role(session)
    await _grant_new_menus_by_permissions(session, new_menu_ids)
    await _grant_all(session, role, permission_ids, menu_ids, miniapp_menu_ids)
    return role


async def sync_catalog_entries(session: AsyncSession, catalog):
    """租户维护的选择性补缺入口；仅接受代码声明，不删除目录或自动授予权限。

    调用方负责已授权的租户上下文、事务及角色授权；避免补齐一项功能时同步无关目录。
    """
    from app.framework.catalog import Catalog
    from app.framework.db.tenant import get_tenant_schema
    if not isinstance(catalog,Catalog) or get_tenant_schema() is None:
        raise ValueError('选择性目录同步需要可信Catalog与显式租户上下文')
    await _sync_permissions_and_menus(session,catalog=catalog)


async def grant_catalog_menus_for_permissions(session: AsyncSession, menu_ids):
    """租户维护时按已有权限补齐指定新菜单；不增加接口权限。"""
    from app.framework.db.tenant import get_tenant_schema
    if get_tenant_schema() is None:raise ValueError('菜单补齐需要显式租户上下文')
    menu_ids=list(menu_ids)
    await _grant_new_menus_by_permissions(session,menu_ids)
    admins=(await session.exec(select(SysRole).where(SysRole.is_builtin.is_(True),SysRole.is_active.is_(True),
        SysRole.data_scope_code=='all',SysRole.deleted_at.is_(None)))).scalars().all()
    for role in admins:
        await _grant_all(session,role,[],menu_ids,[])


async def _run_module_setups(session: AsyncSession, ctx: TenantContext, modules: set[str] | None = None) -> None:
    if modules is not None and "navigation" not in modules:
        # 单插件开通及限定模块的 bootstrap 同样处理底座维护的旧导航，
        # 避免目录补齐后因跳过 navigation 而留下已退役入口。
        from app.modules.navigation.tenant_setup import setup_tenant as setup_navigation

        await setup_navigation(session, ctx)
        await session.commit()
    for module in iter_module_attr("tenant_setup", modules):
        await module.setup_tenant(session, ctx)
        await session.commit()
    if modules is not None and "notification_center" not in modules:
        # 单插件开通/升级只运行业务模块 setup；补跑这些模块声明的通知场景，
        # 避免业务 notification_scenes.py 已加载但 ntf_scene 尚未落库。
        from app.modules.notification_center.tenant_setup import setup_tenant as setup_notification_scenes

        await setup_notification_scenes(session, ctx, only=modules)
        await session.commit()
    if modules is not None and "workflow" not in modules:
        # 单插件开通/升级也要安装该插件声明的审批模板。
        from app.modules.workflow.tenant_setup import setup_tenant as setup_workflow

        await setup_workflow(session, ctx, only=modules)
        await session.commit()


async def provision_tenant(spec: TenantSpec, *, upgrade_schema: bool = True, modules: set[str] | None = None) -> TenantContext:
    """开通（或补齐）一个租户，返回开通上下文。"""
    async with get_session_context() as session:
        tenant, admin = await _ensure_public(session, spec)
    if upgrade_schema:
        upgrade_tenant_schema(tenant.schema_name)

    with use_tenant_schema(tenant.schema_name):
        async with get_session_context() as session:
            role = await _sync_catalog(session)
            org = await _ensure_root_org(session, spec)
            user = await _ensure_admin_user(session, admin, spec, org, role)
            await session.commit()
            ctx = TenantContext(tenant=tenant, schema=tenant.schema_name, root_org_id=org.id, admin_user_id=user.id, admin_role_id=role.id)
            await _run_module_setups(session, ctx, modules)
    from app.framework.tenant_plugins import mark_bootstrap_ready

    await mark_bootstrap_ready(tenant.id, modules)
    return ctx


async def sync_existing_tenant(
    tenant: AuthTenant,
    *,
    upgrade_schema: bool = True,
    modules: set[str] | None = None,
    mark_plugins_ready: bool = True,
    retire_missing_dict_items: bool = True,
) -> TenantContext | None:
    """升级已开通的租户：迁移到最新版本，补齐字典、权限、菜单与各模块的开通数据。"""
    if upgrade_schema:
        upgrade_tenant_schema(tenant.schema_name)
    with use_tenant_schema(tenant.schema_name):
        async with get_session_context() as session:
            role = await _sync_catalog(session, retire_missing_dict_items=retire_missing_dict_items)
            org = (
                await session.exec(select(SysOrg).where(SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None)).order_by(SysOrg.created_at))
            ).scalars().first()
            admin_user = (
                await session.exec(
                    select(SysUser).join(SysUserRole, SysUserRole.user_id == SysUser.id).where(SysUserRole.role_id == role.id).order_by(SysUser.created_at)
                )
            ).scalars().first()
            await session.commit()
            if org is None or admin_user is None:
                return None
            ctx = TenantContext(tenant=tenant, schema=tenant.schema_name, root_org_id=org.id, admin_user_id=admin_user.id, admin_role_id=role.id)
            await _run_module_setups(session, ctx, modules)
    if mark_plugins_ready:
        from app.framework.tenant_plugins import mark_bootstrap_ready

        await mark_bootstrap_ready(tenant.id, modules)
    return ctx
