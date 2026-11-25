"""代码定义的权限、菜单、小程序菜单目录。

每个模块在自己目录下的 ``catalog.py``（app/modules/<模块>/catalog.py）中声明：

    PERMISSIONS: list[PermissionDef]
    MENUS: list[MenuDef]                         # 管理端菜单（可选）
    MENU_PLACEMENTS: list[MenuPlacementDef]      # 组合部署中的菜单位置调整（可选）
    MINIAPP_MENUS: list[MiniappMenuDef]          # 小程序菜单（可选）

开通租户时（tenant_template）收集全部模块的目录，为该租户生成 sys_permission / sys_menu / sys_miniapp_menu，
并把全部权限授予内置管理员角色。``permission_key`` / ``menu_key`` 由代码定义，创建后不可修改。
"""

from __future__ import annotations

import importlib
import pkgutil
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from functools import lru_cache

import app.modules as modules_pkg

from app.framework.deployment import is_menu_enabled, is_module_enabled

_collection_modules: ContextVar[frozenset[str] | None] = ContextVar("catalog_collection_modules", default=None)


@contextmanager
def use_module_selection(modules: set[str]):
    """限定一次开通/同步中所有嵌套收集器，退出或失败后恢复原范围。"""
    current = _collection_modules.get()
    selected = frozenset(modules) if current is None else current.intersection(modules)
    token = _collection_modules.set(selected)
    try:
        yield
    finally:
        _collection_modules.reset(token)


@dataclass(frozen=True)
class PermissionDef:
    key: str
    name: str
    module_code: str  # 字典 sys_module


@dataclass(frozen=True)
class MenuDef:
    key: str
    name: str
    menu_type_code: str  # 字典 sys_menu_type：directory / menu / button
    parent_key: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission_key: str | None = None
    sort_no: int = 0
    is_visible: bool = True
    is_external: bool = False
    external_url: str | None = None
    open_target_code: str = "self"  # 字典 sys_open_target
    flex_form: dict = field(default_factory=dict)
    # 目录以前为该菜单声明过的上级（None 表示顶层）。已开通租户中，菜单仍挂在这些上级之一时
    # 视为未被手工调整，开通同步会把它移到当前的 parent_key；挂在其他位置的不动。
    previous_parent_keys: tuple[str | None, ...] = ()
    # 显式开启时，仅在授权导航中迁移已声明的旧默认父级；存储和自定义挂载保持不变。
    display_parent_from_catalog: bool = False
    # 仅替换代码曾下发过的旧图标；租户自行设置的图标保持不变。
    previous_icons: tuple[str | None, ...] = ()
    # 只兼容代码曾下发的旧默认名称；租户自定义名称保持不变。
    previous_names: tuple[str, ...] = ()
    # 只兼容代码曾下发的旧默认排序；租户自定义排序保持不变。
    previous_sort_nos: tuple[int, ...] = ()
    # 同路径菜单使用这些历史组件时，可升级为目录或新的页面包装组件；不覆盖租户自定义组件。
    previous_components: tuple[str, ...] = ()
    # 自动补授新菜单时额外要求角色已拥有其中一个权限；不增加接口权限或替代手工菜单授权。
    auto_grant_permissions_any: tuple[str, ...] = ()
    # 仅替换明确声明的历史默认权限、路由元数据和跳转；保留租户自定义值。
    previous_permission_keys: tuple[str, ...] = ()
    previous_route_meta: dict[str, tuple] = field(default_factory=dict)
    previous_redirects: tuple[str, ...] = ()
    # 具备任一权限时默认提供入口；不授予接口权限或数据访问许可。
    default_permissions_any: tuple[str, ...] = ()


@dataclass(frozen=True)
class MenuPlacementDef:
    """上层插件启用时，对依赖插件已有菜单进行组合式布局。"""

    key: str
    parent_key: str | None
    sort_no: int


@dataclass(frozen=True)
class MiniappMenuDef:
    portal_code: str  # 字典 sys_miniapp_portal
    menu_key: str
    menu_name: str
    path: str | None = None
    group_key: str | None = None
    group_name: str | None = None
    sort_no: int = 0
    permission_key: str | None = None
    # 只兼容明确列出的历史分组（标识、名称），保留租户自定义分组。
    previous_groups: tuple[tuple[str | None, str | None], ...] = ()


@dataclass
class Catalog:
    permissions: list[PermissionDef] = field(default_factory=list)
    menus: list[MenuDef] = field(default_factory=list)
    miniapp_menus: list[MiniappMenuDef] = field(default_factory=list)


@lru_cache(maxsize=1)
def miniapp_menu_group_aliases() -> dict[tuple[str, str | None, str | None], tuple[str | None, str | None]]:
    # 同一业务菜单的旧门户也沿用此兼容声明，不改变门户或授权。
    return {
        (item.menu_key, *old): (item.group_key, item.group_name)
        for item in collect_catalog().miniapp_menus
        for old in item.previous_groups
    }


def miniapp_menu_display_group(
    menu_key: str, group_key: str | None, group_name: str | None,
) -> tuple[str | None, str | None]:
    """显示声明过的历史默认分组；不读取 PC 菜单，不修改存储。"""
    return miniapp_menu_group_aliases().get((menu_key, group_key, group_name), (group_key, group_name))


@lru_cache(maxsize=1)
def _miniapp_menu_name_aliases() -> dict[tuple[str, str], str]:
    return {
        (item.menu_key, old): item.menu_name
        for module in iter_module_attr("catalog")
        for item in getattr(module, "MINIAPP_MENUS", ())
        for old in getattr(module, "MINIAPP_MENU_PREVIOUS_NAMES", {}).get(item.menu_key, ())
    }


def miniapp_menu_display_name(menu_key: str, current_name: str) -> str:
    """更新目录声明的历史默认名称，保留租户自定义名称。"""
    return _miniapp_menu_name_aliases().get((menu_key, current_name), current_name)


@lru_cache(maxsize=1)
def _menu_name_aliases() -> dict[tuple[str, str], str]:
    return {(item.key, old): item.name for item in collect_catalog().menus for old in item.previous_names}


def menu_display_name(menu_key: str, current_name: str) -> str:
    """将历史默认菜单名投影为当前名称，不修改数据库或覆盖客户命名。"""
    return _menu_name_aliases().get((menu_key, current_name), current_name)


@lru_cache(maxsize=1)
def _menu_icon_aliases() -> dict[tuple[str, str | None], str]:
    return {
        (item.key, old.replace("/", ":") if old else old): item.icon
        for item in collect_catalog().menus if item.icon
        for old in item.previous_icons
    }


def menu_display_icon(menu_key: str, current_icon: str | None) -> str | None:
    """按菜单声明更新历史默认图标，保留自定义图标。"""
    icon_key = current_icon.replace("/", ":") if current_icon else current_icon
    return _menu_icon_aliases().get((menu_key, icon_key), current_icon)


@lru_cache(maxsize=1)
def retired_menu_keys() -> frozenset[str]:
    """收集模块声明的退役入口，供已有租户的授权导航过滤使用。"""
    return frozenset(key for module in iter_module_attr("catalog")
                     for key in getattr(module, "RETIRED_MENU_KEYS", ()))


@lru_cache(maxsize=1)
def embedded_menu_owners() -> dict[str, str]:
    """业务目录声明的合并入口；只影响导航展示，不改菜单授权和存储。"""
    return {item.key: owner for item in collect_catalog().menus
            if isinstance(owner := (item.flex_form.get('route', {}).get('meta', {}).get('embeddedIn')), str)
            and owner != item.key}


@lru_cache(maxsize=1)
def single_tag_menu_paths() -> dict[str, str]:
    """代码声明共用一个页签的页面，兼容已开通租户的菜单记录。"""
    return {item.key: item.path for item in collect_catalog().menus
            if item.menu_type_code == "menu" and item.path
            and item.flex_form.get("route", {}).get("meta", {}).get("dynamicLevel") == 1}


@lru_cache(maxsize=1)
def default_menu_permissions() -> dict[str, tuple[str, ...]]:
    return {item.key: item.default_permissions_any for item in collect_catalog().menus
            if item.default_permissions_any}


@lru_cache(maxsize=1)
def menu_display_parent_definitions() -> dict[str, MenuDef]:
    return {item.key: item for item in collect_catalog().menus if item.display_parent_from_catalog}


def compatible_menu_component(
    definition: MenuDef, current_path: str | None, current_component: str | None, current_type: str
) -> str | None:
    """同一页面仅兼容明确声明的旧组件；目录转换仍须显式菜单同步。"""
    if (
        current_type == definition.menu_type_code == "menu"
        and definition.path is not None
        and current_path == definition.path
        and definition.component
        and current_component in definition.previous_components
    ):
        return definition.component
    return current_component


@lru_cache(maxsize=1)
def _menu_component_definitions() -> dict[str, MenuDef]:
    return {
        item.key: item for item in collect_catalog().menus
        if item.menu_type_code == "menu" and item.component and item.previous_components
    }


def menu_display_component(
    menu_key: str, current_path: str | None, current_component: str | None, current_type: str
) -> str | None:
    """授权菜单响应兼容系统旧组件，不修改菜单记录或增加可访问入口。"""
    definition = _menu_component_definitions().get(menu_key)
    if definition is None:
        return current_component
    return compatible_menu_component(definition, current_path, current_component, current_type)


def iter_module_attr(module_name: str, only: set[str] | None = None, *, exclude: set[str] | None = None):
    """收集模块声明；only 限定目录，exclude 在导入前排除目录。"""
    selected = _collection_modules.get()
    if selected is not None:
        only = set(selected) if only is None else only.intersection(selected)
    for info in sorted(pkgutil.iter_modules(modules_pkg.__path__), key=lambda item: item.name):
        if not info.ispkg or not is_module_enabled(info.name) or (only is not None and info.name not in only) or (exclude and info.name in exclude):
            continue
        try:
            yield importlib.import_module(f"app.modules.{info.name}.{module_name}")
        except ModuleNotFoundError as exc:
            if exc.name != f"app.modules.{info.name}.{module_name}":
                raise


def collect_catalog() -> Catalog:
    catalog = Catalog()
    placements: list[MenuPlacementDef] = []
    for module in iter_module_attr("catalog"):
        catalog.permissions.extend(getattr(module, "PERMISSIONS", []))
        catalog.menus.extend(getattr(module, "MENUS", []))
        catalog.miniapp_menus.extend(getattr(module, "MINIAPP_MENUS", []))
        placements.extend(getattr(module, "MENU_PLACEMENTS", []))
    # 集中式 navigation catalog 同时包含多个业务域。按 plugin.toml 中稳定的
    # menu_key 归属裁剪，不依赖可能被租户修改的路径、权限或菜单层级。
    retired = retired_menu_keys()
    catalog.menus = [item for item in catalog.menus if item.key not in retired and is_menu_enabled(item.key)]
    _check_unique("menu placement key", [item.key for item in placements])
    menus_by_key = {item.key: item for item in catalog.menus}
    for placement in placements:
        menu = menus_by_key.get(placement.key)
        # 依赖插件没有参与本次收集，或目标目录不属于当前部署时，保留所属插件的默认布局。
        if menu is None or (placement.parent_key and placement.parent_key not in menus_by_key):
            continue
        previous_parent_keys = tuple(
            dict.fromkeys((*menu.previous_parent_keys, menu.parent_key))
        )
        placed = replace(
            menu,
            parent_key=placement.parent_key,
            sort_no=placement.sort_no,
            previous_parent_keys=previous_parent_keys,
        )
        catalog.menus[catalog.menus.index(menu)] = placed
        menus_by_key[placement.key] = placed
    permission_keys = {item.key for item in catalog.permissions}
    while True:
        menu_keys = {item.key for item in catalog.menus}
        remaining = [
            item for item in catalog.menus
            if (item.permission_key is None or item.permission_key in permission_keys)
            and (item.parent_key is None or item.parent_key in menu_keys)
        ]
        if len(remaining) == len(catalog.menus):
            break
        catalog.menus = remaining
    _check_unique("permission_key", [item.key for item in catalog.permissions])
    _check_unique("menu_key", [item.key for item in catalog.menus])
    _check_unique("miniapp menu_key", [(item.portal_code, item.menu_key) for item in catalog.miniapp_menus])
    permission_keys = {item.key for item in catalog.permissions}
    menu_keys = {item.key for item in catalog.menus}
    for menu in catalog.menus:
        if set(menu.auto_grant_permissions_any) - permission_keys:
            raise ValueError(f"菜单 {menu.key} 的自动授权条件引用了未声明的权限")
        if menu.permission_key and menu.permission_key not in permission_keys:
            raise ValueError(f"菜单 {menu.key} 引用了未声明的权限 {menu.permission_key}")
        if menu.parent_key and menu.parent_key not in menu_keys:
            raise ValueError(f"菜单 {menu.key} 引用了未声明的上级菜单 {menu.parent_key}")
    for menu in catalog.miniapp_menus:
        if menu.permission_key and menu.permission_key not in permission_keys:
            raise ValueError(
                f"小程序菜单 {menu.portal_code}/{menu.menu_key} 引用了未声明的权限 {menu.permission_key}"
            )
    return catalog


@lru_cache(maxsize=1)
def _miniapp_menu_permissions() -> dict[tuple[str, str], str]:
    """代码目录声明的小程序入口权限；未声明的入口仍只按角色菜单控制。"""

    return {
        (item.portal_code, item.menu_key): item.permission_key
        for item in collect_catalog().miniapp_menus
        if item.permission_key
    }


def can_access_miniapp_menu(
    portal_code: str,
    menu_key: str,
    permissions: list[str] | set[str] | frozenset[str],
) -> bool:
    required = _miniapp_menu_permissions().get((portal_code, menu_key))
    return required is None or required in permissions


def _check_unique(label: str, values: list) -> None:
    seen: set = set()
    for value in values:
        if value in seen:
            raise ValueError(f"重复的 {label}: {value}")
        seen.add(value)


def crud_permissions(resource: str, label: str, module_code: str, *, actions: tuple[str, ...] = ("list", "detail", "create", "update", "delete", "export")) -> list[PermissionDef]:
    """常用的增删改查导出权限。"""
    names = {"list": "查询", "detail": "查看", "create": "新增", "update": "修改", "delete": "删除", "export": "导出", "import": "导入"}
    return [PermissionDef(f"{resource}:{action}", f"{names.get(action, action)}{label}", module_code) for action in actions]
