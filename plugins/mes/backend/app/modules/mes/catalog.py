"""MES 能力包目录：权限、管理端菜单、字典取值和小程序入口。"""

from app.framework.catalog import MenuDef, MiniappMenuDef, PermissionDef
from app.framework.menu_composition import MenuComposition

# 组合制造导航；其他消费者需要保留的共享视图由其自身声明。
MENU_COMPOSITIONS = [MenuComposition(
    plugin_key="mes", source_key="Inventory", target_key="MesWarehouse",
    aliases=(("InventoryStock", "MesWarehouseStock"), ("InventoryInbound", "MesWarehouseInbound"),
             ("InventoryOutbound", "MesWarehouseOutbound"), ("InventoryGoods", "MesArchiveGoods")),
    placements=(("InventoryTransfer", 7), ("InventoryBorrow", 8), ("InventoryDamage", 9), ("InventoryStockSettings", 10)),
    route_meta=(("warehouse_scope_key", "mes"),),
    hidden_placements=("InventoryTransfer", "InventoryBorrow", "InventoryDamage"),
), MenuComposition(
    plugin_key="mes", source_key="Inventory", target_key="MesArchives",
    placements=(("AssetManagement", 10),),
    hidden_placements=("AssetManagement",),
)]

PERMISSIONS = [
    PermissionDef("mes:quote:list", "查看加工询价与报价快照", "mes"),
    PermissionDef("mes:quote:manage", "维护询价零件与核价", "mes"),
    PermissionDef("mes:quote:analyze", "解析图纸及生成工艺初稿", "mes"),
    PermissionDef("mes:quote:approve", "审核加工报价", "mes"),
    PermissionDef("mes:quote:rules", "维护组织报价规则", "mes"),
    PermissionDef("mes:dashboard:view", "查看交付驾驶舱", "mes"),
    PermissionDef("mes:work_order:list", "查询生产工单", "mes"),
    PermissionDef("mes:work_order:create", "创建生产工单", "mes"),
    PermissionDef("mes:work_order:manage", "变更及管理生产工单", "mes"),
    PermissionDef("mes:process_change:approve", "审批生产工单工艺变更", "mes"),
    # 销售询价已接入真实数据；客户订单与出货来源演示仍单独保留。
    PermissionDef("mes:quotation:list", "查看询价报价", "mes"),
    PermissionDef("mes:quotation:manage", "录入及提交询价需求", "mes"),
    PermissionDef("mes:quotation:price", "工程核价及完成报价", "mes"),
    PermissionDef("mes:quotation:export", "导出报价明细及图纸", "mes"),
    PermissionDef("mes:quotation:approve", "审核销售报价及退回工程", "mes"),
    PermissionDef("mes:quotation:approve_self", "审核本人提交的销售报价", "mes"),
    PermissionDef("mes:sales_order:list", "查看客户订单", "mes"),
    PermissionDef("mes:sales_order:manage", "确认客户订单", "mes"),
    PermissionDef("mes:sales_order:approve", "审核客户订单", "mes"),
    PermissionDef("mes:sales_order:release", "按客户订单下达生产需求", "mes"),
    PermissionDef("mes:production_report:create", "提交现场报工", "mes"),
    PermissionDef("mes:production_report:change", "申请报工更正或冲销", "mes"),
    PermissionDef("mes:production_report:change:list", "查询报工变更申请", "mes"),
    PermissionDef("mes:production_report:approve", "复核报工变更", "mes"),
    PermissionDef("mes:production_report:list", "查询现场报工", "mes"),
    PermissionDef("mes:operation_task:list", "查询生产任务", "mes"),
    PermissionDef("mes:operation_task:detail", "查看生产任务详情", "mes"),
    PermissionDef("mes:operation_task:manage", "管理全部生产任务", "mes"),
    PermissionDef("mes:schedule:list", "查询生产排程", "mes"),
    PermissionDef("mes:schedule:manage", "调整生产排程", "mes"),
    PermissionDef("mes:schedule_resource:list", "查看生产人员技能与日历", "mes"),
    PermissionDef("mes:schedule_resource:manage", "维护生产人员技能与日历", "mes"),
    PermissionDef("mes:schedule:apply", "确认并应用自动排程方案", "mes"),
    PermissionDef("mes:process_template:list", "查询工序模板", "mes"),
    PermissionDef("mes:process_template:manage", "维护工序模板", "mes"),
    PermissionDef("mes:shipment:list", "查询出货单", "mes"),
    PermissionDef("mes:shipment:manage", "维护及确认出货", "mes"),
    PermissionDef("mes:shipment:documents", "查看及下载出货单据", "mes"),
    PermissionDef("mes:shipment:invoice", "登记正式发票", "mes"),
    PermissionDef("mes:reconciliation:list", "查询客户出货对账", "mes"),
    PermissionDef("mes:reconciliation:manage", "维护及确认客户出货对账", "mes"),
    PermissionDef("mes:inventory:list", "查询生产库存业务", "mes"),
    PermissionDef("mes:inventory:manage", "办理生产领退料及成品入库", "mes"),
    PermissionDef("mes:warehouse:list", "查看制造仓库配置", "mes"),
    PermissionDef("mes:warehouse:manage", "维护制造仓库配置", "mes"),
    PermissionDef("mes:quality:list", "查询工序检验及记录", "mes"),
    PermissionDef("mes:quality:inspect", "检验放行或退回返工", "mes"),
    PermissionDef("mes:exception:list", "查询制造异常", "mes"),
    PermissionDef("mes:exception:create", "登记制造异常", "mes"),
    PermissionDef("mes:exception:manage", "指派异常及调整期限", "mes"),
    PermissionDef("mes:exception:handle", "处理本人负责的异常", "mes"),
    PermissionDef("mes:exception:review", "复核、退回及重开异常", "mes"),
]

for _resource, _name in (("customer", "客户档案"), ("stage", "项目阶段"), ("process", "工艺档案"), ("equipment", "设备档案"), ("requirement", "工艺要求")):
    PERMISSIONS.extend([PermissionDef(f"mes:archive:{_resource}:list", f"查询{_name}", "mes"),
        PermissionDef(f"mes:archive:{_resource}:manage", f"维护{_name}", "mes")])

# 按工作流程分组，兼容旧外层目录和上一版平铺菜单。
_PREVIOUS_PARENTS = ("Mes", None)
MENU_GROUPS = {
    "MesSales": ("MesQuotations", "MesSalesOrders"),
    "MesProduction": ("MesQuoting", "MesWorkOrders", "MesRepairOrders", "MesScheduling", "MesReworkDetails", "MesProductionPeople", "MesResourceCalendars", "MesSchedulePlans"),
    "MesArchives": ("MesProcessTemplates",),
    "MesReporting": ("MesExecution", "MesManualReporting", "MesProductionReports", "MesReportChanges", "MesQuality", "MesExceptions"),
    "MesDelivery": ("MesShipments", "MesReconciliations"),
    "MesExtensions": ("MesProductProcess", "MesTraceability", "MesEquipment"),
    "MesWarehouse": ("MesInventory",),  # 旧库存协同保留隐藏路由，不重复展示入口。
}
_PAGE_PARENTS = {key: group for group, keys in MENU_GROUPS.items() for key in keys}


def _menu(key: str, name: str, path: str, component: str, icon: str, permission_key: str, sort_no: int, domain: str | None = None, *, single_tag: bool = False) -> MenuDef:
    meta: dict[str, str | int] = {"mes_domain": domain} if domain else {}
    if single_tag:
        meta["dynamicLevel"] = 1
    return MenuDef(
        key,
        name,
        "menu",
        _PAGE_PARENTS.get(key),
        path,
        component,
        icon,
        permission_key,
        sort_no,
        flex_form={"route": {"meta": meta}} if meta else {},
        previous_parent_keys=_PREVIOUS_PARENTS + (("MesProduction",) if key == "MesProcessTemplates" else ("MesExtensions",) if key == "MesQuality" else ()),
        previous_names=("MES 工作台",) if key == "MesDashboard" else ("有限产能排程",) if key == "MesScheduling" else ("工序模板",) if key == "MesProcessTemplates" else ("质量管理",) if key == "MesQuality" else (),
        is_visible=key != "MesInventory",
    )


MENUS = [
    MenuDef("MesSales", "销售管理", "directory", path="/mes/sales", icon="ri:price-tag-3-line", sort_no=2),
    MenuDef("MesProduction", "生产管理", "directory", path="/mes/production", icon="ri:file-list-3-line", sort_no=3, previous_sort_nos=(2,)),
    MenuDef("MesReporting", "执行与报工", "directory", path="/mes/reporting-center", icon="ri:edit-box-line", sort_no=4, previous_sort_nos=(3,)),
    MenuDef("MesDelivery", "出货与对账", "directory", path="/mes/delivery", icon="ri:truck-line", sort_no=5, previous_sort_nos=(4,)),
    MenuDef("MesExtensions", "制造扩展", "directory", path="/mes/extensions", icon="ri:apps-2-line", sort_no=8, previous_sort_nos=(6, 7)),
    _menu("MesQuoting", "加工询价", "/mes/quoting", "mes/quoting/index", "ri:calculator-line", "mes:quote:list", 1),
    _menu("MesDashboard", "交付驾驶舱", "/mes/dashboard", "mes/dashboard/index", "ri:dashboard-3-line", "mes:dashboard:view", 1),
    _menu("MesQuotations", "询价报价", "/mes/quotations", "mes/quotations/index", "ri:file-paper-2-line", "mes:quotation:list", 1, single_tag=True),
    _menu("MesSalesOrders", "客户订单", "/mes/sales-orders", "mes/sales-orders/index", "ri:shopping-bag-3-line", "mes:sales_order:list", 2),
    _menu("MesWorkOrders", "生产工单", "/mes/work-orders", "mes/work-orders/index", "ri:file-list-3-line", "mes:work_order:list", 2),
    _menu("MesRepairOrders", "返修工单", "/mes/repair-orders", "mes/repair-orders/index", "ri:tools-line", "mes:work_order:list", 3),
    _menu("MesReworkDetails", "返工明细", "/mes/reworks", "mes/reworks/index", "ri:repeat-line", "mes:production_report:list", 5),
    _menu("MesProductionPeople", "生产人员与技能", "/mes/production-people", "mes/resources/people/index", "ri:team-line", "mes:schedule_resource:list", 6),
    _menu("MesResourceCalendars", "工作日历", "/mes/resource-calendars", "mes/resources/calendars/index", "ri:calendar-schedule-line", "mes:schedule_resource:list", 7),
    _menu("MesSchedulePlans", "排程方案", "/mes/schedule-plans", "mes/schedule-plans/index", "ri:calendar-check-line", "mes:schedule:list", 8),
    _menu("MesProcessTemplates", "工艺路线", "/mes/process-templates", "mes/archives/routes/index", "ri:list-check-3", "mes:process_template:list", 9),
    _menu("MesExecution", "执行控制与派工", "/mes/execution", "mes/execution/index", "ri:flow-chart", "mes:operation_task:manage", 7),
    _menu("MesProductionReports", "现场报工台账", "/mes/production-reports", "mes/production-reports/index", "ri:edit-2-line", "mes:production_report:list", 9),
    _menu("MesManualReporting", "手动报工", "/mes/reporting", "mes/reporting/index", "ri:edit-box-line", "mes:production_report:create", 8),
    _menu("MesReportChanges", "报工变更 / 审批", "/mes/report-changes", "mes/report-changes/index", "ri:git-pull-request-line", "mes:production_report:change:list", 10),
    _menu("MesShipments", "出货单", "/mes/shipments", "mes/shipments/index", "ri:truck-line", "mes:shipment:list", 11, single_tag=True),
    _menu("MesReconciliations", "对账单", "/mes/reconciliations", "mes/reconciliations/index", "ri:bill-line", "mes:reconciliation:list", 12),
    _menu("MesProductProcess", "产品与工艺版本", "/mes/product-process", "mes/capability/index", "ri:git-branch-line", "mes:operation_task:manage", 13, "product_process"),
    _menu("MesQuality", "工序检验", "/mes/quality", "mes/quality/index", "ri:verified-badge-line", "mes:quality:list", 11),
    _menu("MesExceptions", "异常处理", "/mes/exceptions", "mes/exceptions/index", "ri:alarm-warning-line", "mes:exception:list", 12),
    _menu("MesTraceability", "追溯与谱系", "/mes/traceability", "mes/capability/index", "ri:route-line", "mes:operation_task:manage", 15, "traceability"),
    _menu("MesEquipment", "设备集成", "/mes/equipment", "mes/capability/index", "ri:cpu-line", "mes:operation_task:manage", 16, "equipment"),
    _menu("MesScheduling", "生产排程", "/mes/scheduling", "mes/scheduling/index", "ri:calendar-schedule-line", "mes:schedule:list", 4),
    _menu("MesInventory", "MES 库存协同", "/mes/inventory", "mes/warehouse/consumption/index", "ri:archive-stack-line", "mes:inventory:list", 17),
    MenuDef("MesWarehouse", "仓库管理", "directory", path="/mes/warehouse", icon="ri:store-2-line", sort_no=6, previous_parent_keys=_PREVIOUS_PARENTS, previous_sort_nos=(5, 13, 18)),
    MenuDef("MesWarehouseInbound", "入库作业", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/inbound", component="mes/warehouse/inbound/index", icon="ri:inbox-archive-line",
        permission_key="inventory_inbound:list", sort_no=1, previous_icons=(None,)),
    MenuDef("MesWarehouseOutbound", "出库作业", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/outbound", component="mes/warehouse/outbound/index", icon="ri:inbox-unarchive-line",
        permission_key="inventory_outbound:list", sort_no=2, previous_icons=(None,)),
    MenuDef("MesWarehouseConsumption", "生产消耗", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/consumption", component="mes/warehouse/consumption/index", icon="ri:archive-stack-line",
        permission_key="mes:inventory:list", sort_no=3, previous_icons=(None,)),
    MenuDef("MesWarehouseMovements", "出入明细", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/movements", component="mes/warehouse/movements/index", icon="ri:file-list-2-line",
        permission_key="inventory_movement:list", sort_no=4, previous_icons=(None,)),
    MenuDef("MesWarehouseStock", "实时库存", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/stock", component="mes/warehouse/stock/index", icon="ri:stack-line",
        permission_key="inventory_item:list", sort_no=5, previous_icons=(None,)),
    MenuDef("MesWarehouseSettings", "制造仓库配置", "menu", parent_key="MesWarehouse",
        path="/mes/warehouse/settings", component="mes/warehouse/settings/index", icon="ri:settings-3-line",
        permission_key="mes:warehouse:list", sort_no=6, previous_icons=(None,)),
]

MENUS.append(MenuDef("MesArchives", "档案管理", "directory", path="/mes/archives", icon="ri:folder-3-line", sort_no=7, previous_sort_nos=(6,)))
for _index, (_key, _name, _path, _icon, _permission) in enumerate([
    ("MesArchiveGoods", "货品档案", "goods", "ri:box-3-line", "inventory_product:list"),
    ("MesArchiveCustomers", "客户档案", "customers", "ri:contacts-book-3-line", "mes:archive:customer:list"),
    ("MesArchiveSuppliers", "供应商档案", "suppliers", "ri:truck-line", "supplier:list"),
    ("MesArchivePrices", "采购价格表", "prices", "ri:price-tag-3-line", "inventory_supplier_price:list"),
    ("MesArchiveStages", "项目阶段", "project-stages", "ri:flag-2-line", "mes:archive:stage:list"),
    ("MesArchiveProcesses", "工艺档案", "processes", "ri:git-branch-line", "mes:archive:process:list"),
    ("MesArchiveEquipment", "设备档案", "equipment", "ri:cpu-line", "mes:archive:equipment:list"),
    ("MesArchiveRequirements", "工艺要求", "requirements", "ri:file-check-line", "mes:archive:requirement:list"),
], 1):
    MENUS.append(MenuDef(_key, _name, "menu", parent_key="MesArchives", path=f"/mes/archives/{_path}",
        component=f"mes/archives/{_path}/index", icon=_icon, permission_key=_permission, sort_no=_index,
        previous_parent_keys=_PREVIOUS_PARENTS, previous_icons=(None,)))

MINIAPP_MENUS = [
    MiniappMenuDef("standard", "mes_production_report", "扫码报工",
        path="/pages/production-report/index", group_key="mes", group_name="生产执行", sort_no=10),
    MiniappMenuDef("standard", "mes_operation_progress", "加工进度",
        path="/pages/production-progress/index", group_key="mes", group_name="生产执行", sort_no=20,
        permission_key="mes:work_order:list"),
]

MINIAPP_MENU_PREVIOUS_NAMES = {"mes_production_report": ("手机报工",)}
