"""公告的权限与菜单。"""

from app.framework.catalog import MenuDef, PermissionDef, crud_permissions

PERMISSIONS = crud_permissions("notice_announcement", "公告", "notify", actions=("list", "detail", "create", "update", "delete"))

MENUS = [
    MenuDef(
        "NoticeAnnouncement",
        "公告管理",
        "menu",
        parent_key="SystemManagement",
        path="/system/notice/index",
        component="system/notice/index",
        icon="ri:notification-3-line",
        permission_key="notice_announcement:list",
        sort_no=8,
    ),
]

__all__ = ["MENUS", "PERMISSIONS", "PermissionDef"]
