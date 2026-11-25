"""仓库领用申请权限与小程序入口。"""

from app.framework.catalog import MiniappMenuDef, PermissionDef

PERM_CREATE = "inventory_requisition:create"
PERM_LIST = "inventory_requisition:list"
PERM_DETAIL = "inventory_requisition:detail"
PERM_APPROVE = "inventory_requisition:approve"
PERM_ISSUE = "inventory_requisition:issue"
PERM_EXPORT = "inventory_requisition:export"
PERM_APPLY_CANTEEN = "inventory_requisition:apply_canteen"

RETIRED_MENU_KEYS = ("InventoryRequisitionTodoDetail",)

PERMISSIONS = [
    PermissionDef(PERM_CREATE, "提交、查看并签收本人物资领用申请", "inventory"),
    PermissionDef(PERM_LIST, "查询物资领用申请", "inventory"),
    PermissionDef(PERM_DETAIL, "查看物资领用申请详情", "inventory"),
    PermissionDef(PERM_APPROVE, "审批物资领用申请", "inventory"),
    PermissionDef(PERM_ISSUE, "发放出库及处理收货异常", "inventory"),
    PermissionDef(PERM_EXPORT, "导出物资领用台账", "inventory"),
    PermissionDef(PERM_APPLY_CANTEEN, "申请食堂食材（各仓库）", "inventory"),
]

MINIAPP_MENUS = [
    MiniappMenuDef("standard", "material_requisition", "物资领用", path="/pages/material/index", group_key="logistics", group_name="后勤管理", sort_no=54,
                   previous_groups=(("applications", "业务应用"), ("logistics", "后勤科"))),
]
