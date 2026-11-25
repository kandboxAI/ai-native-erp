"""物资与库存、供应商的权限（module_code = inventory）。

库存菜单由本插件声明，页面按授权目录动态装配。
权限标识沿用原有页面：库存单据按单据类型的表单（constants.FORM_PERMISSION_RESOURCE）对应到
inventory_inbound / inventory_outbound / inventory_transfer / inventory_lend / inventory_damage / inventory_stocktake。
"""

from dataclasses import replace

from app.framework.catalog import MenuDef, MiniappMenuDef, PermissionDef, crud_permissions

MODULE = "inventory"
RETIRED_MENU_KEYS = ("InventoryOrderTypes",)
MINIAPP_MENUS = [
    MiniappMenuDef("standard", "inventory_stock_alert", "低库存预警",
                   path="/pages/inventory-alerts/index", group_key="logistics", group_name="后勤管理", sort_no=56,
                   previous_groups=(("applications", "业务应用"), ("logistics", "后勤科"))),
]
CRUD_EXPORT = ("list", "detail", "create", "update", "delete", "export")
ORDER_ACTIONS = {
    "list": "查询",
    "detail": "查看",
    "create": "新增及提交",
    "update": "修改及作废",
    "delete": "删除草稿",
    "approve": "审批",
    "confirm": "确认记账及冲销",
}
ORDER_RESOURCES = {
    "inventory_inbound": "入库单",
    "inventory_outbound": "出库单",
    "inventory_transfer": "调拨单",
    "inventory_lend": "借出归还单",
    "inventory_damage": "报损单",
    "inventory_stocktake": "盘点调整单",
}

PERMISSIONS = [
    PermissionDef("inventory_item:list", "查看库存", MODULE),
    PermissionDef("inventory_stock_alert:list", "查看低库存补货预警", MODULE),
    PermissionDef("inventory_warehouse:requisition_scope", "配置仓库申领范围", MODULE),
    PermissionDef("inventory_warehouse:authorize", "配置仓库管理账号", MODULE),
    PermissionDef("inventory_product:manage_shared", "维护跨仓库共用物料基础信息", MODULE),
    PermissionDef("inventory_item:import", "导入库存盘点", MODULE),
    PermissionDef("inventory_movement:list", "查看库存流水", MODULE),
    *crud_permissions("inventory_product", "物料", MODULE, actions=(*CRUD_EXPORT, "import")),
    *crud_permissions("inventory_product_category", "物料分类", MODULE, actions=(*CRUD_EXPORT, "import")),
    *crud_permissions("inventory_warehouse", "仓库", MODULE, actions=("list", "detail", "create", "update", "delete", "export")),
    *crud_permissions("inventory_stock_order_type", "库存单据类型", MODULE, actions=("list", "detail", "export")),
    *[
        PermissionDef(f"{resource}:{action}", f"{verb}{label}", MODULE)
        for resource, label in ORDER_RESOURCES.items()
        for action, verb in ORDER_ACTIONS.items()
    ],
    *crud_permissions("supplier", "供应商", MODULE, actions=CRUD_EXPORT),
    *crud_permissions("supplier_category", "供应商分类", MODULE, actions=CRUD_EXPORT),
    PermissionDef("supplier_bank_account:list", "查看供应商收款账户（脱敏）", MODULE),
    PermissionDef("supplier_bank_account:update", "维护供应商收款账户", MODULE),
]

MENUS = [
    MenuDef("Inventory", "物资与库存", "directory", path="/inventory", icon="ri:archive-line", sort_no=20),
    MenuDef('InventoryStock', '库存查询', "menu", parent_key="Inventory", path="/inventory/stock", component="inventory/inventory-query/index", permission_key='inventory_item:list', sort_no=1, is_visible=True),
    MenuDef('InventoryStockSettings', '安全库存设置', "menu", parent_key="Inventory",
        path="/inventory/stock-settings", component="inventory/stock-settings/index", icon="ri:shield-check-line",
        permission_key='inventory_item:list', sort_no=2, is_visible=True, previous_icons=(None,)),
    MenuDef('InventoryGoods', '物料与基础资料', "menu", parent_key="Inventory", path="/inventory/goods", component="inventory/goods-management/index", permission_key='inventory_product:list', sort_no=3, is_visible=True),
    MenuDef('InventoryInbound', '入库管理', "menu", parent_key="Inventory", path="/inventory/inbound", component="inventory/inbound-list/index", permission_key='inventory_inbound:list', sort_no=4, is_visible=True, previous_names=('入库单',)),
    MenuDef('InventoryOutbound', '出库管理', "menu", parent_key="Inventory", path="/inventory/outbound", component="inventory/outbound-list/index", permission_key='inventory_outbound:list', sort_no=5, is_visible=True, previous_names=('出库单',)),
    MenuDef('InventoryTransfer', '调拨管理', "menu", parent_key="Inventory", path="/inventory/transfer", component="inventory/transfer-list/index", permission_key='inventory_transfer:list', sort_no=6, is_visible=True, previous_names=('调拨单',)),
    MenuDef('InventoryBorrow', '借用归还', "menu", parent_key="Inventory", path="/inventory/borrow", component="inventory/borrow-return/index", permission_key='inventory_lend:list', sort_no=7, is_visible=True, previous_names=('借出归还',)),
    MenuDef('InventoryDamage', '报损管理', "menu", parent_key="Inventory", path="/inventory/damage", component="inventory/damage-list/index", permission_key='inventory_damage:list', sort_no=8, is_visible=True, previous_names=('报损单',)),
    MenuDef('InventoryInboundForm', '入库单表单', "menu", parent_key="Inventory", path="/inventory/inbound/form", component="inventory/inbound-list/form", permission_key='inventory_inbound:create', sort_no=9, is_visible=False),
    MenuDef('InventoryOutboundForm', '出库单表单', "menu", parent_key="Inventory", path="/inventory/outbound/form", component="inventory/outbound-list/form", permission_key='inventory_outbound:create', sort_no=10, is_visible=False),
]


# 独立业务页签改为二级目录下的三级页面，保留旧入口路径与授权记录。
_source_menu = next(menu for menu in MENUS if menu.key == 'InventoryStock')
MENUS = [replace(menu, menu_type_code="directory", component=None, previous_components=('inventory/inventory-query/index',), flex_form={"route": {"redirect": '/inventory/stock/summary'}}) if menu.key == 'InventoryStock' else menu for menu in MENUS]
MENUS.append(MenuDef('InventoryStockSummary', '库存汇总', "menu", parent_key='InventoryStock', path='/inventory/stock/summary', component='inventory/inventory-query/index', icon=_source_menu.icon, permission_key='inventory_item:list', sort_no=1, flex_form={"route": {"meta": {'menuView': 'summary', 'menuGroup': 'InventoryStock'}}}))
MENUS.append(MenuDef('InventoryStockBalances', '余额明细', "menu", parent_key='InventoryStock', path='/inventory/stock/balances', component='inventory/inventory-query/index', icon=_source_menu.icon, permission_key='inventory_item:list', sort_no=2, flex_form={"route": {"meta": {'menuView': 'balance', 'menuGroup': 'InventoryStock'}}}))
MENUS.append(MenuDef('InventoryStockMovements', '库存流水', "menu", parent_key='InventoryStock', path='/inventory/stock/movements', component='inventory/inventory-query/index', icon=_source_menu.icon, permission_key='inventory_movement:list', sort_no=3, flex_form={"route": {"meta": {'menuView': 'transaction', 'menuGroup': 'InventoryStock'}}}))
_source_menu = next(menu for menu in MENUS if menu.key == 'InventoryGoods')
MENUS = [replace(menu, menu_type_code="directory", component=None, previous_components=('inventory/goods-management/index',), flex_form={"route": {"redirect": '/inventory/goods/items'}}) if menu.key == 'InventoryGoods' else menu for menu in MENUS]
MENUS.append(MenuDef('InventoryProducts', '物料', "menu", parent_key='InventoryGoods', path='/inventory/goods/items', component='inventory/goods-management/index', icon=_source_menu.icon, permission_key='inventory_product:list', sort_no=1, flex_form={"route": {"meta": {'menuView': 'items', 'menuGroup': 'InventoryGoods'}}}))
MENUS.append(MenuDef('InventoryProductCategories', '物料分类', "menu", parent_key='InventoryGoods', path='/inventory/goods/categories', component='inventory/goods-management/index', icon=_source_menu.icon, permission_key='inventory_product_category:list', sort_no=2, flex_form={"route": {"meta": {'menuView': 'categories', 'menuGroup': 'InventoryGoods'}}}))
MENUS.append(MenuDef('InventoryWarehouses', '仓库', "menu", parent_key='InventoryGoods', path='/inventory/goods/warehouses', component='inventory/goods-management/index', icon=_source_menu.icon, permission_key='inventory_warehouse:list', sort_no=3, flex_form={"route": {"meta": {'menuView': 'warehouses', 'menuGroup': 'InventoryGoods'}}}))
MENUS.append(MenuDef('InventorySuppliers', '供应商', "menu", parent_key='InventoryGoods', path='/inventory/goods/suppliers', component='inventory/goods-management/index', icon=_source_menu.icon, permission_key='supplier:list', sort_no=4, flex_form={"route": {"meta": {'menuView': 'suppliers', 'menuGroup': 'InventoryGoods'}}}))
MENUS.append(MenuDef('InventorySupplierCategories', '供应商分类', "menu", parent_key='InventoryGoods', path='/inventory/goods/supplier-categories', component='inventory/goods-management/index', icon=_source_menu.icon, permission_key='supplier_category:list', sort_no=5, flex_form={"route": {"meta": {'menuView': 'supplierCategories', 'menuGroup': 'InventoryGoods'}}}))

# 从教育组合切回 inv 独立部署并同步目录时，恢复曾由上层编排的默认位置；
# 只识别历史默认父级，不覆盖租户自定义目录。
MENUS = [replace(menu, previous_parent_keys=("LogisticsWarehouse",))
         if menu.menu_type_code == "menu" else menu for menu in MENUS]
