from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import AppException

from app.auth.dependencies import require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import (
    MesWorkOrderListQuery,
    ProductionActionBody,
    ProductionDispatchBody,
    ProductionReportBody,
    ProductionReportListQuery,
    ProductionTaskListQuery,
    WorkOrderCreate,
    MesOptionQuery,
    WorkOrderUpdate,
    WorkOrderCommand,
    ProjectPlaceOrder,
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ScheduleQuery, ScheduleUpdate, ProcessTemplateQuery, ProcessTemplateBody, WorkOrderDrawingUpdate, DrawingHistoryQuery, ReworkQuery,
    ReportChangeBody, ReportChangeQuery,
)
from .service import service
from .order_service import order_service
from .production_service import production_service
from .report_service import report_service
from .cockpit_schemas import DeliveryCockpitQuery
from .cockpit_service import cockpit_service
from .delivery_api import router as delivery_router
from .inventory_api import router as inventory_router
from .warehouse_api import router as warehouse_router
from .archive_api import router as archive_router
from .quality_api import router as quality_router
from .exception_api import router as exception_router
from .process_change_api import router as process_change_router

router = APIRouter(prefix="/api/mes", tags=["mes"])
from .cnc.api import router as cnc_router
router.include_router(cnc_router)
router.include_router(delivery_router, prefix="")
router.include_router(inventory_router, prefix="")
router.include_router(warehouse_router)
router.include_router(archive_router)
router.include_router(quality_router)
router.include_router(exception_router)
router.include_router(process_change_router)
from .quotation_api import router as quotation_router
router.include_router(quotation_router)
from .sales_order_api import router as sales_order_router
router.include_router(sales_order_router)
from .schedule_trial_api import router as schedule_trial_router
router.include_router(schedule_trial_router)
from .schedule_resource_api import router as schedule_resource_router
router.include_router(schedule_resource_router)
from .schedule_plan_api import router as schedule_plan_router
router.include_router(schedule_plan_router)


@router.get("/reporting/tasks", summary="可报工任务；包括本人派工、开放任务和授权代录任务")
async def reporting_tasks(query: ProductionTaskListQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"]))):
    return paginated_response(**await service.list_my_tasks(query, user))


@router.get("/reporting/tasks/{task_id}", summary="读取 Web 报工任务当前版本")
async def reporting_task(task_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"]))):
    return success_response((await service.detail(task_id, user, permission="mes:production_report:create")).model_dump(mode="json"))


@router.post("/reporting/tasks/{task_id}/{action}", summary="Web 开工、暂停、恢复或结束执行")
async def reporting_action(task_id: UUID, action: str, body: ProductionActionBody, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"]))):
    actions = {"track-in": service.track_in, "hold": service.hold, "release": service.release, "track-out": service.track_out, "stage": service.change_execution_stage}
    if action not in actions: raise AppException("不支持的生产执行动作", 422)
    return success_response((await actions[action](task_id, body, user)).model_dump(mode="json"))


@router.post("/reporting/tasks/{task_id}/reports/submit", summary="Web 提交手动报工；来源由服务端指定")
async def web_report(task_id: UUID, body: ProductionReportBody, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"]))):
    return success_response((await service.report(task_id, body, user, source_code="web")).model_dump(mode="json"))


@router.get("/production-reports/{report_id}", summary="查询报工详情及附件")
async def report_detail(report_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:list"]))):
    return success_response(await report_service.detail(report_id, user))


@router.post("/production-reports/{report_id}/changes", summary="提交报工更正或冲销审批")
async def request_report_change(report_id: UUID, body: ReportChangeBody, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:change"]))):
    try:
        return success_response(await report_service.create_change(report_id, body, user))
    except IntegrityError as error:
        raise AppException("该报工已有变更申请或幂等键已被使用，请刷新后重试", 409) from error


@router.get("/report-changes", summary="查询报工变更申请")
async def report_changes(query: ReportChangeQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:change:list"]))):
    return paginated_response(**await report_service.changes(query, user))


@router.post("/report-changes/{change_id}/withdraw", summary="撤回本人审批中的报工变更")
async def withdraw_report_change(change_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:change"]))):
    return success_response(await report_service.withdraw(change_id, user))


@router.get("/delivery-cockpit", summary="查询授权工单的交期风险和履约汇总")
async def delivery_cockpit(query: DeliveryCockpitQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:dashboard:view", "mes:work_order:list"]))):
    return success_response(await cockpit_service.read(query, user))


@router.get("/schedules", summary="查询排程工序，可按货品工单分页")
async def schedules(query: ScheduleQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:schedule:list"]))):
    return paginated_response(**await production_service.schedules(query, user))


@router.put("/schedules", summary="原子保存工序计划时间")
async def save_schedules(body: ScheduleUpdate, user: AuthenticatedUser = Depends(require_permissions(["mes:schedule:manage"]))):
    return success_response(await production_service.schedule(body, user))


@router.get("/schedule-resources", summary="按授权范围汇总设备任务、计划工时及按日负荷")
async def schedule_resources(query: ScheduleQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:schedule:list"]))):
    return success_response(await production_service.schedule_resources(query, user))


@router.get("/schedule-options/organizations", summary="选择排程授权范围内组织")
async def schedule_organizations(query: MesOptionQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:schedule:list"]))):
    return success_response(await production_service.schedule_organizations(query, user))


@router.get("/process-templates", summary="查询可复用工序模板")
async def process_templates(query: ProcessTemplateQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:process_template:list"]))):
    return paginated_response(**await production_service.templates(query, user))


@router.get("/process-template-options", summary="按当前工单权限浏览本组织启用路线；选产品后限定适用路线")
async def process_template_options(query: ProcessTemplateQuery = Depends(), action: Literal["create", "manage"] = "create",
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:work_order:create", "mes:work_order:manage"]))):
    return paginated_response(**await production_service.template_options(query, user, action))


@router.post("/process-templates", summary="创建工序模板")
async def create_template(body: ProcessTemplateBody, user: AuthenticatedUser = Depends(require_permissions(["mes:process_template:manage"]))):
    try:
        return success_response(await production_service.save_template(body, user))
    except IntegrityError as error:
        raise AppException("模板编号重复或引用数据已变化，请检查后重试", 409) from error


@router.get("/process-template-options/organizations", summary="选择工序模板所属组织")
async def template_org_options(query: MesOptionQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:process_template:manage"]))):
    return success_response(await production_service.template_organizations(query, user))


@router.get("/process-template-options/products", summary="选择工序模板适用产品")
async def template_product_options(query: MesOptionQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:process_template:manage"]))):
    return success_response(await service.creation_options("products", query, user))


@router.put("/process-templates/{template_id}", summary="修订工序模板；不改写已有工单")
async def update_template(template_id: UUID, body: ProcessTemplateBody, user: AuthenticatedUser = Depends(require_permissions(["mes:process_template:manage"]))):
    try:
        return success_response(await production_service.save_template(body, user, template_id))
    except IntegrityError as error:
        raise AppException("模板编号重复或引用数据已变化，请检查后重试", 409) from error


@router.get("/work-orders/{work_order_id}/drawings", summary="查看工单图纸及版本")
async def drawings(work_order_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"]))):
    return success_response(await production_service.drawings(work_order_id, user))


@router.put("/work-orders/{work_order_id}/drawings", summary="保存尚未执行工单的图纸")
async def save_drawings(work_order_id: UUID, body: WorkOrderDrawingUpdate, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:manage"]))):
    return success_response(await production_service.save_drawings(work_order_id, body, user))


@router.get("/work-orders/{work_order_id}/drawings/history", summary="分页查看工单图纸修订及历史文件")
async def drawing_history(work_order_id: UUID, query: DrawingHistoryQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"]))):
    from .drawing_service import drawing_service
    return success_response(await drawing_service.history(work_order_id, query, user))


@router.get("/reworks", summary="查询返工报工明细及返修安排")
async def reworks(query: ReworkQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:list"]))):
    return paginated_response(**await production_service.reworks(query, user))


@router.get("/work-order-options/products", summary="选择生产物料")
async def product_options(
    query: MesOptionQuery = Depends(),
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:work_order:create", "mes:work_order:manage"])),
):
    return success_response(await service.creation_options("products", query, user))


@router.get("/work-order-options/organizations", summary="选择工单所属组织")
async def organization_options(
    query: MesOptionQuery = Depends(),
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:work_order:create", "mes:work_order:manage"])),
):
    return success_response(await service.creation_options("organizations", query, user))


@router.get("/work-order-options/assignees", summary="选择工单派工人员")
async def assignee_options(
    query: MesOptionQuery = Depends(), org_id: UUID | None = None, for_edit: bool = False,
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:work_order:create", "mes:work_order:manage"])),
):
    return success_response(await service.creation_options("assignees", query, user, org_id, for_edit=for_edit))


@router.get("/operation-tasks/{task_id}", summary="查看管理端工序详情")
async def manager_operation_detail(
    task_id: UUID,
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:operation_task:list", "mes:operation_task:manage", "mes:work_order:list"])),
):
    return success_response((await service.manager_detail(task_id, user)).model_dump(mode="json"))


@router.get("/operation-tasks/{task_id}/assignees", summary="查询可派工的生产人员及账号状态")
async def dispatch_assignee_options(
    task_id: UUID, query: MesOptionQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:operation_task:manage"])),
):
    return success_response(await service.dispatch_options(task_id, query, user))


@router.post("/work-orders")
async def create_work_order(
    body: WorkOrderCreate,
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:create"])),
) -> dict[str, Any]:
    try:
        result = await service.create_work_order(body, user)
        return success_response(result.model_dump(mode="json") if hasattr(result, "model_dump") else result, message="生产工单已创建")
    except IntegrityError as error:
        raise AppException("工单编号重复或引用数据已变化，请检查后重试", 409) from error


@router.post("/production-orders", summary="创建包含多个产品的生产项目")
async def create_production_order(body: ProductionOrderCreate, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:create"]))):
    try:
        return success_response(await service.create_production_order(body, user))
    except IntegrityError as error:
        raise AppException("项目/工单编号重复或引用数据已变化，请检查后重试", 409) from error


@router.get("/production-orders", summary="按项目查询生产工单")
async def list_production_orders(query: MesWorkOrderListQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"]))):
    return paginated_response(**await service.list_production_orders(query, user))


@router.put("/production-orders/{project_id}", summary="变更项目资料及追加产品")
async def update_production_order(project_id: UUID, body: ProductionOrderUpdate, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:manage"]))):
    try:
        return success_response(await service.update_production_order(project_id, body, user))
    except IntegrityError as error:
        raise AppException("项目/工单编号重复或引用数据已变化，请检查后重试", 409) from error


@router.get("/work-orders/{work_order_id}/definition", summary="读取工单配置用于变更、复制及返修")
async def order_definition(work_order_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"]))):
    return success_response(await order_service.definition(work_order_id, user))


@router.post("/production-orders/{project_id}/place", summary="整单下单；同一事务切换全部待下单货品状态")
async def place_production_order(project_id: UUID, body: ProjectPlaceOrder,
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:manage"]))):
    return success_response(await order_service.place_project(project_id, body, user))


@router.put("/work-orders/{work_order_id}", summary="变更工单配置或交期")
async def update_work_order(work_order_id: UUID, body: WorkOrderUpdate, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:manage"]))):
    return success_response(await order_service.update(work_order_id, body, user))


@router.post("/work-orders/{work_order_id}/actions/{action}", summary="执行工单生命周期动作")
async def order_action(work_order_id: UUID, action: str, body: WorkOrderCommand, user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:manage"]))):
    return success_response(await order_service.command(work_order_id, action, body, user))


@router.get("/work-orders", summary="查询生产工单")
async def list_work_orders(
    query: MesWorkOrderListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_work_orders(query, user))


@router.get("/work-orders/{work_order_id}")
async def work_order_detail(
    work_order_id: UUID,
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"])),
) -> dict[str, Any]:
    return success_response((await service.work_order_detail(work_order_id, user)).model_dump(mode="json"))


@router.get("/operation-tasks", summary="查询生产工序任务")
async def list_operation_tasks(
    query: ProductionTaskListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:operation_task:list", "mes:operation_task:manage"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_manager_tasks(query, user))


@router.get("/production-reports", summary="查询现场生产报工")
async def list_production_reports(
    query: ProductionReportListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_reports(query, user))


@router.get("/mobile/operation-tasks/mine")
async def list_my_operation_tasks(
    query: ProductionTaskListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_my_tasks(query, user))


@router.get("/mobile/work-orders", summary="查询加工进度（工单进度）")
async def list_operation_progress(
    query: MesWorkOrderListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_work_orders(query, user))


@router.get("/mobile/work-orders/{work_order_id}/drawings", summary="查询工单二维图纸")
async def work_order_drawings(
    work_order_id: UUID,
    user: AuthenticatedUser = Depends(require_permissions(["mes:work_order:list"])),
) -> dict[str, Any]:
    return success_response(await production_service.drawings(work_order_id, user))


@router.get("/mobile/operation-tasks/{task_id}")
async def operation_task_detail(
    task_id: UUID,
    user: AuthenticatedUser = Depends(require_any_permissions(["mes:production_report:create", "mes:operation_task:list", "mes:operation_task:manage"])),
) -> dict[str, Any]:
    return success_response((await service.detail(task_id, user)).model_dump(mode="json"))


@router.post("/mobile/operation-tasks/{task_id}/track-in")
async def track_in(
    task_id: UUID,
    body: ProductionActionBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return success_response((await service.track_in(task_id, body, user)).model_dump(mode="json"))


@router.post("/operation-tasks/{task_id}/dispatch")
async def dispatch(
    task_id: UUID,
    body: ProductionDispatchBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:operation_task:manage"])),
) -> dict[str, Any]:
    return success_response((await service.dispatch(task_id, body, user)).model_dump(mode="json"), message="生产任务已派工")


@router.post("/mobile/operation-tasks/{task_id}/hold")
async def hold(
    task_id: UUID,
    body: ProductionActionBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return success_response((await service.hold(task_id, body, user)).model_dump(mode="json"))


@router.post("/mobile/operation-tasks/{task_id}/release")
async def release(
    task_id: UUID,
    body: ProductionActionBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return success_response((await service.release(task_id, body, user)).model_dump(mode="json"))


@router.post("/mobile/operation-tasks/{task_id}/production-report")
async def production_report(
    task_id: UUID,
    body: ProductionReportBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return success_response((await service.report(task_id, body, user)).model_dump(mode="json"), message="报工已提交")


@router.post("/mobile/operation-tasks/{task_id}/track-out")
async def track_out(
    task_id: UUID,
    body: ProductionActionBody,
    user: AuthenticatedUser = Depends(require_permissions(["mes:production_report:create"])),
) -> dict[str, Any]:
    return success_response((await service.track_out(task_id, body, user)).model_dump(mode="json"))
