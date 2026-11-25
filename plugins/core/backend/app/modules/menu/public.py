"""供插件租户配置使用的导航维护契约；事务由调用方提交。"""
from app.framework.catalog import collect_catalog
from .repository import repository


async def hide_legacy_entry(session, *, menu_key: str, expected_path: str, user_id) -> bool:
    """仅可同步 catalog 明确声明为隐藏的旧入口。"""
    definition = next((item for item in collect_catalog().menus if item.key == menu_key), None)
    if definition is None or definition.is_visible or definition.path != expected_path:
        raise ValueError("仅允许隐藏 catalog 明确声明的兼容入口")
    return await repository.hide_legacy_entry(session, menu_key, expected_path, user_id)


async def retire_empty_directory(session, *, menu_key: str, expected_path: str, user_id) -> bool:
    """退役插件已不再声明的空目录；仍在活动目录中的菜单不得停用。"""
    if any(item.key == menu_key for item in collect_catalog().menus):
        raise ValueError("不能退役仍在 catalog 声明的目录")
    return await repository.retire_empty_directory(session, menu_key, expected_path, user_id)


async def upgrade_legacy_page(session, *, menu_key: str, expected_path: str, previous_component: str,
                              previous_permission_key: str, obsolete_route_meta: dict, user_id) -> bool:
    """按插件显式声明升级旧页面；目标组件和权限必须取自当前 catalog。"""
    definition = next((item for item in collect_catalog().menus if item.key == menu_key), None)
    if definition is None or definition.menu_type_code != "menu" or definition.path != expected_path or not definition.component or not definition.permission_key:
        raise ValueError("页面升级目标必须是当前 catalog 声明的有效页面及权限")
    return await repository.upgrade_legacy_page(session, definition, previous_component=previous_component,
        previous_permission_key=previous_permission_key, obsolete_route_meta=obsolete_route_meta, user_id=user_id)
