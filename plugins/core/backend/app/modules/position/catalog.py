from app.framework.catalog import MenuDef, crud_permissions

PERMISSIONS = [
    *crud_permissions("position", "岗位", "system", actions=("list", "detail", "create", "update", "delete", "export")),
]
MENUS = [MenuDef("SystemPosition", "岗位管理", "menu", parent_key="SystemManagement",
    path="/system/position/index", component="system/position/index", icon="ri:briefcase-line",
    permission_key="position:list", sort_no=6)]

