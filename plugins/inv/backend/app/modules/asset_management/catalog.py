"""资产管理权限目录。管理端菜单由 navigation 模块按真实路由统一登记。"""

from dataclasses import replace

from app.framework.catalog import MiniappMenuDef, PermissionDef, MenuDef

MODULE = "inventory"
RETIRED_MENU_KEYS = ("AssetLocations",)

# 固定资产按业务常用量词登记：桌椅等家具可按“张”管理。
# 由资产模块向通用计量单位字典扩展，库存、资产交接与导入统一使用稳定编码 sheet。

PERMISSIONS = [
    PermissionDef("asset_register:list", "查询资产台账", MODULE),
    PermissionDef("asset_register:detail", "查看资产详情和变更记录", MODULE),
    PermissionDef("asset_register:create", "登记资产", MODULE),
    PermissionDef("asset_register:update", "修改资产基础信息", MODULE),
    PermissionDef("asset_register:adjust", "调整场所资产数量", MODULE),
    PermissionDef("asset_register:transfer", "调拨资产和移交责任人", MODULE),
    PermissionDef("asset_register:confirm", "确认并锁定资产登记信息", MODULE),
    PermissionDef("asset_register:void", "作废资产登记信息", MODULE),
    PermissionDef("asset_handover:list", "查询资产交接单", MODULE),
    PermissionDef("asset_handover:create", "发起资产交接", MODULE),
    PermissionDef("asset_handover:manage", "维护和提交资产交接", MODULE),
    PermissionDef("asset_handover:receive", "确认接收资产", MODULE),
    PermissionDef("asset_handover:mine", "查看并处理本人资产交接", MODULE),
    PermissionDef("asset_location:list", "查询历史地点关联", MODULE),
    PermissionDef("asset_location:manage", "维护历史地点关联", MODULE),
]

MENUS = [
    MenuDef("AssetManagement", "资产管理", "directory", parent_key="Inventory", path="/logistics-management/assets", icon="ri:archive-drawer-line", sort_no=10, previous_parent_keys=("TrainingRoomLogistics", "LogisticsManagement")),
    MenuDef("AssetManagementLedger", "资产台账", "menu", parent_key="AssetManagement", path="/logistics-management/assets/ledger", component="asset-management/index", permission_key="asset_register:list", sort_no=1, flex_form={"route": {"meta": {"menuView": "ledger"}}}),
    MenuDef("AssetHandovers", "资产交接", "menu", parent_key="AssetManagement", path="/logistics-management/assets/handovers", component="asset-management/handover", permission_key="asset_handover:list", sort_no=3, previous_sort_nos=(2,)),
]

# 组合部署移入设备资产分组后，独立部署同步仍能恢复原默认父级。
MENUS = [replace(menu, previous_parent_keys=("LogisticsEquipmentAssets",))
         if menu.parent_key == "AssetManagement" else menu for menu in MENUS]

MINIAPP_MENUS = [
    MiniappMenuDef(
        "teacher",
        "asset_handover_mine",
        "我的资产交接",
        path="/pages/asset-handovers/index",
        group_key="logistics",
        group_name="后勤管理",
        sort_no=56,
        previous_groups=(("logistics", "后勤服务"), ("logistics", "后勤科")),
    ),
]
