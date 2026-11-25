"""代码维护的菜单兼容同步，不修改其余菜单或角色授权。"""
from sqlalchemy import update
from sqlmodel import select

from app.framework.db.models import utc_now
from app.framework.catalog import retired_menu_keys
from app.modules.menu.models import SysMenu


RETIRED_MENU_KEYS = (
    "Foundation", "FndAcademicYears", "FndAcademicTerms", "FndTimeSlots",
    "FndStudentBatches", "FndEducationSettings", "FndOrganization",
    "FndDepartments", "FndMajors", "FndClasses",
    "StuAcademicStatusApprovals",
    "StuLeaveApprovals",
    "AdmissionsPortal", "AdmSite", "AdmApply",
    "StuFamilyBinding",
    "StudentsReports", "StuRptAbsent", "StuRptMonthly", "StuRptBatch", "StuRptContacts",
    "StudentsPortal", "StuPortalChildren", "StuPortalSchedule", "StuPortalGrades",
    "StuPortalFees", "StuPortalAttendance", "StuPortalLeave",
    "LogisticsDormitoryAllocation", "LogisticsDormitory", "TrainingRoomLogistics",
    "LogisticsSafety", "LogisticsDashboard", "LogisticsAccess", "LogisticsRepair",
    "LogisticsUtility", "LogisticsHazard", "LogisticsWorkOrders", "LogisticsReviews",
    "LogisticsDormitoryCapacity", "LogisticsDormitoryResidents",
    "LogisticsDormitoryInspections", "LogisticsDormitoryOccupancy", "LogisticsDormitoryRooms",
    "LogisticsIncident", "LogisticsAlerts",
)

CONSUMABLE_REQUISITION_MENU_KEY = "AssetConsumableRequisitions"
LEGACY_CONSUMABLE_REQUISITION_COMPONENT = "logistics-management/warehouse-requisitions/index"
CONSUMABLE_REQUISITION_COMPONENT = "logistics-management/consumable-requisitions/index"
CONSUMABLE_REQUISITION_WRITE_AUTHS = {
    "inventory_requisition:approve",
    "inventory_requisition:issue",
}


async def sync_consumable_requisition_menu(session):
    """把仍指向旧审批页的耗材菜单切换到独立只读台账页。"""
    menu = (
        await session.exec(
            select(SysMenu).where(
                SysMenu.menu_key == CONSUMABLE_REQUISITION_MENU_KEY,
                SysMenu.deleted_at.is_(None),
            )
        )
    ).first()
    if menu is None or menu.component != LEGACY_CONSUMABLE_REQUISITION_COMPONENT:
        return

    menu.component = CONSUMABLE_REQUISITION_COMPONENT
    current_flex = dict(menu.flex_form or {})
    route = dict(current_flex.get("route") or {})
    meta = dict(route.get("meta") or {})
    auths = meta.get("auths")
    if isinstance(auths, list):
        meta["auths"] = [item for item in auths if item not in CONSUMABLE_REQUISITION_WRITE_AUTHS]
        route["meta"] = meta
        current_flex["route"] = route
        menu.flex_form = current_flex
    menu.updated_at = utc_now()


async def retire_obsolete_menus(session):
    """只退役明确列出的旧入口，保留业务数据、权限和角色绑定。"""
    await session.execute(update(SysMenu).where(
        SysMenu.menu_key.in_((*RETIRED_MENU_KEYS, *retired_menu_keys())),
        SysMenu.deleted_at.is_(None),
        (SysMenu.is_active.is_(True) | SysMenu.is_visible.is_(True)),
    ).values(is_active=False, is_visible=False, updated_at=utc_now()))
