from app.framework.catalog import PermissionDef, MenuDef

PERMISSIONS = [PermissionDef("md_location:list", "查询位置信息", "inventory"),
               PermissionDef("md_location:manage", "维护位置信息", "inventory")]
MENUS = [MenuDef("LocationRoot", "位置信息", "menu", parent_key="SystemManagement", path="/location", component="location/index",
                 permission_key="md_location:list", icon="ri:map-pin-line", sort_no=10,
                 previous_parent_keys=("Inventory", "LogisticsManagement"), previous_sort_nos=(40, 5),
                 display_parent_from_catalog=True)]
