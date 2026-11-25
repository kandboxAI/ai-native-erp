from __future__ import annotations
from .archive_binding import customer_snapshot, prepare_operations

from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.file.service import PHOTO_MAX_BYTES, register_file_scene, service as file_service
from app.modules.inventory.public import get_active_item, list_active_item_options
from app.modules.user_profile.public import list_assignee_options, user_display_names
from app.modules.organization.public import list_writable_org_options

from .models import MesExecutionEvent, MesOperationExecution, MesProductionReport, MesWorkOrder, MesWorkOrderOperation, MesProductionOrder, MesWorkOrderEvent, MesReworkAssignment
from .production_repository import production_repository
from .report_repository import report_repository
from .operation_planning import configuration_plan
from .drawing_files import bind_product_drawings
from .order_status import ORDER_STATUS_LABELS, work_order_status, project_order_status
from .repository import MES_MANAGE_PERMISSION, MES_TASK_PERMISSION, repository
from .schemas import (
    MesOperationProgressItem,
    MesWorkOrderDetail,
    MesWorkOrderItem,
    MesWorkOrderListQuery,
    ProductionActionBody,
    ProductionDispatchBody,
    ProductionReportBody,
    ProductionTaskDetail,
    ProductionTaskItem,
    ProductionTaskListQuery,
    ProductionReportItem,
    ProductionReportListQuery,
    WorkOrderCreate,
    MesOptionQuery,
    ProductionOrderCreate,
)

BUSINESS_TYPE = "mes_production_report"
SCENE_REPORT = "production_report"
register_file_scene(SCENE_REPORT, kinds={"image", "document"}, max_bytes=PHOTO_MAX_BYTES, max_count=20)

STATUS_LABELS = {
    "draft": "待下单",
    "pending": "待执行",
    "dispatched": "已派工",
    "in_progress": "执行中",
    "paused": "已暂停",
    "waiting_quality": "待检验",
    "completed": "已完成",
    "cancelled": "已取消",
}
PRIORITY_LABELS = {"urgent": "紧急", "high": "高", "normal": "普通", "low": "低"}
EVENT_LABELS = {
    "phase_changed": "实际执行阶段变更",
    "created": "任务创建",
    "dispatched": "已派工",
    "tracked_in": "开工",
    "held": "已暂停",
    "released": "已恢复",
    "production_reported": "已报工",
    "tracked_out": "完工",
    "scheduled": "计划时间调整",
    "quality_released": "检验放行",
    "quality_rework_requested": "检验退回返工",
}


def _conflict(message: str) -> AppException:
    return AppException(message, status_code=HTTPStatus.CONFLICT)


def _forbidden(message: str) -> AppException:
    return AppException(message, status_code=HTTPStatus.FORBIDDEN)


def _number(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)


class MesService:
    @staticmethod
    async def _ensure_no_pending_change(session, order_id):
        if await report_repository.pending_for_order(session, order_id):
            raise _conflict("工单存在审批中的报工变更，请先完成审批或撤回申请，再执行生产操作")

    @staticmethod
    def _ensure_order_executable(work_order):
        if work_order.status_code not in {"released", "in_progress"}:
            raise _conflict("工单未发布、已暂停或已结束，当前不能执行生产操作")

    @staticmethod
    def _check_version(task, version_no: int) -> None:
        if task.version_no != version_no:
            raise _conflict("生产任务已被其他人员更新，请刷新后重试")

    @staticmethod
    async def _ensure_task_access(session, task, user: AuthenticatedUser) -> None:
        if MES_MANAGE_PERMISSION in user.permissions:
            return
        person_id = getattr(task, "assigned_production_person_id", None)
        if not person_id:
            assignment = (await repository.applied_assignments(session, [task.id])).get(task.id)
            person_id = assignment.person_id if assignment else None
        if person_id:
            if not await repository.can_report_as_person(session, task.org_id, person_id, user.user_id):
                raise _forbidden("该工序已指定生产人员，请由本人登录报工或由有权限的班组长代录")
        elif task.assigned_user_id is not None and task.assigned_user_id != user.user_id:
            raise _forbidden("该生产任务未派工给当前人员")

    @staticmethod
    def _event(session, task, user: AuthenticatedUser, event_type: str, *, execution_id: UUID | None = None, note: str | None = None, from_status: str | None = None, to_status: str | None = None) -> None:
        repository.add(
            session,
            MesExecutionEvent(
                org_id=task.org_id,
                operation_id=task.id,
                execution_id=execution_id,
                event_type_code=event_type,
                from_status_code=from_status,
                to_status_code=to_status,
                note=note,
                actor_user_id=user.user_id,
                actor_name_snapshot=(user.display_name or "当前用户").strip(),
                created_by=user.user_id,
            ),
        )

    @staticmethod
    def _touch(task, work_order, user: AuthenticatedUser) -> None:
        now = utc_now()
        task.version_no += 1
        task.updated_at = now
        task.updated_by = user.user_id
        work_order.version_no += 1
        work_order.updated_at = now
        work_order.updated_by = user.user_id

    @staticmethod
    def _task_item(task, work_order) -> ProductionTaskItem:
        return ProductionTaskItem(
            id=task.id,
            work_order_id=work_order.id,
            work_order_status_code=work_order.status_code,
            org_id=task.org_id,
            sequence_no=task.sequence_no,
            version_no=task.version_no,
            assigned_user_id=task.assigned_user_id,
            assigned_production_person_id=getattr(task, "assigned_production_person_id", None),
            process_id=getattr(task, "process_id", None),
            equipment_id=getattr(task, "equipment_id", None),
            work_order_no=work_order.work_order_no,
            operation_no=task.operation_no,
            operation_name=task.operation_name_snapshot,
            operation_description=task.operation_description,
            product_item_no=work_order.product_item_no_snapshot,
            product_item_name=work_order.product_item_name_snapshot,
            work_center_name=task.work_center_name_snapshot,
            workstation_name=task.workstation_name_snapshot,
            planned_quantity=float(task.planned_quantity),
            good_quantity=float(task.good_quantity),
            scrap_quantity=float(task.scrap_quantity),
            rework_quantity=float(task.rework_quantity),
            unit_name=work_order.unit_code,
            status_code=task.status_code,
            status_label=STATUS_LABELS.get(task.status_code, task.status_code),
            priority_code=task.priority_code,
            priority_label=PRIORITY_LABELS.get(task.priority_code, task.priority_code),
            due_at=task.due_at or work_order.due_at,
            updated_at=task.updated_at,
            planned_start_at=task.planned_start_at,
            planned_end_at=task.planned_end_at,
        )

    async def _task_items(self, session, pairs):
        items = [self._task_item(task, order) for task, order in pairs]
        assignments = await repository.applied_assignments(session, [item.id for item in items])
        names = await user_display_names(session, {item.assigned_user_id for item in items if item.assigned_user_id})
        people = await repository.production_person_names(session, {
            item.assigned_production_person_id for item in items if item.assigned_production_person_id
        } | {row.person_id for row in assignments.values() if row.person_id})
        summaries = await repository.execution_summaries(session, [item.id for item in items])
        for item in items:
            item.assigned_user_name = names.get(item.assigned_user_id)
            person = people.get(item.assigned_production_person_id)
            if person and person.org_id == item.org_id:
                item.assigned_production_person_name = person.full_name
                item.assigned_production_person_no = person.person_no
            assignment = assignments.get(item.id)
            if assignment:
                item.schedule_plan_id = assignment.plan_id
                scheduled_person = people.get(assignment.person_id)
                if scheduled_person and scheduled_person.org_id == item.org_id:
                    item.scheduled_production_person_name = scheduled_person.full_name
            summary = summaries.get(item.id)
            if summary:
                item.actual_started_at = summary.started_at
                if item.status_code == "completed":
                    item.actual_finished_at = summary.finished_at
        return items

    async def _detail(self, session, task, work_order, user: AuthenticatedUser) -> ProductionTaskDetail:
        current = await repository.current_execution(session, task.id)
        materials = await repository.materials(session, task.id)
        events = await repository.events(session, task.id)
        item = (await self._task_items(session, [(task, work_order)]))[0]
        executions = await repository.executions(session, task.id)
        people = await repository.production_person_names(session, {
            row.production_person_id for row in executions if row.production_person_id
        })

        def actual_person_name(execution):
            person = people.get(execution.production_person_id)
            return person.full_name if person and person.org_id == task.org_id else None

        current_item = None
        if current is not None:
            current_item = {
                "id": current.id,
                "tracked_in_at": current.tracked_in_at,
                "worker_name": current.worker_name_snapshot or (user.display_name if current.worker_user_id == user.user_id else None),
                "workstation_name": current.workstation_name_snapshot,
                "labor_minutes": _number(current.labor_minutes),
                "machine_minutes": _number(current.machine_minutes),
                "production_phase_id":current.production_phase_id,
                "production_person_id":current.production_person_id,
                "production_person_name": actual_person_name(current),
                "segment_type_code":current.segment_type_code,
            }
        from .schedule_execution import context as schedule_context
        return ProductionTaskDetail(
            **item.model_dump(),
            schedule_context=await schedule_context(session,task,work_order),
            required_skills=list(task.required_skills_snapshot or []),
            is_predecessor_ready=task.is_predecessor_ready,
            is_quality_required=task.is_quality_required,
            material_requirements=[
                {
                    "id": row.id,
                    "item_no": row.item_no_snapshot,
                    "item_name": row.item_name_snapshot,
                    "required_quantity": float(row.required_quantity),
                    "consumed_quantity": float(row.consumed_quantity),
                    "unit_name": row.unit_code,
                    "is_lot_controlled": row.is_lot_controlled,
                    "is_serial_controlled": row.is_serial_controlled,
                }
                for row in materials
            ],
            current_execution=current_item,
            executions=[{
                "id": row.id, "tracked_in_at": row.tracked_in_at,
                "tracked_out_at": row.tracked_out_at, "status_code": row.status_code,
                "worker_name": row.worker_name_snapshot,
                "production_person_id": row.production_person_id,
                "production_person_name": actual_person_name(row),
                "workstation_name": row.workstation_name_snapshot,
                "labor_minutes": _number(row.labor_minutes), "machine_minutes": _number(row.machine_minutes),
            } for row in executions],
            events=[
                {
                    "id": row.id,
                    "event_type_code": row.event_type_code,
                    "event_label": EVENT_LABELS.get(row.event_type_code, row.event_type_code),
                    "note": row.note,
                    "actor_name_snapshot": row.actor_name_snapshot,
                    "created_at": row.created_at,
                }
                for row in events
            ],
        )

    async def list_my_tasks(self, query: ProductionTaskListQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_tasks(session, query, user)
            return {
                "items": [item.model_dump(mode="json") for item in await self._task_items(session, rows)],
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
            }

    async def list_manager_tasks(self, query: ProductionTaskListQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_tasks(session, query, user, manager=True)
            return {
                "items": [item.model_dump(mode="json") for item in await self._task_items(session, rows)],
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
            }

    @staticmethod
    def _work_order_item(work_order, operation_count: int, completed_operation_count: int, *, operations=(), execution_summaries=None) -> MesWorkOrderItem:
        operations = [op for op in operations if op.work_order_id == work_order.id and op.org_id == work_order.org_id]
        plans = configuration_plan(operations)
        summaries = execution_summaries or {}
        return MesWorkOrderItem(
            id=work_order.id,
            org_id=work_order.org_id,
            production_order_id=work_order.production_order_id,
            source_work_order_id=work_order.source_work_order_id,
            order_type_code=work_order.order_type_code,
            processing_type_code=work_order.processing_type_code,
            processing_type_label={"in_house": "自制", "outsourced": "委外", "purchased": "采购"}.get(work_order.processing_type_code, work_order.processing_type_code),
            **{field: getattr(work_order, field, None) for field in ("material_name_snapshot", "heat_treatment_snapshot", "surface_treatment_snapshot", "process_requirement_snapshot", "outsourced_due_at")},
            version_no=work_order.version_no,
            created_at=work_order.created_at,
            created_by=work_order.created_by,
            work_order_no=work_order.work_order_no,
            product_item_no=work_order.product_item_no_snapshot,
            product_item_name=work_order.product_item_name_snapshot,
            unit_name=work_order.unit_code,
            planned_quantity=float(work_order.planned_quantity),
            good_quantity=float(work_order.good_quantity),
            scrap_quantity=float(work_order.scrap_quantity),
            rework_quantity=float(work_order.rework_quantity),
            status_code=work_order.status_code,
            is_process_change_pending=getattr(work_order, "is_process_change_pending", False),
            display_status_key=work_order_status(work_order.status_code, operation_count),
            status_label=ORDER_STATUS_LABELS.get(work_order_status(work_order.status_code, operation_count), work_order.status_code),
            priority_code=work_order.priority_code,
            priority_label=PRIORITY_LABELS.get(work_order.priority_code, work_order.priority_code),
            due_at=work_order.due_at,
            operation_count=operation_count,
            completed_operation_count=completed_operation_count,
            operation_progress=[MesOperationProgressItem(
                id=op.id, sequence_no=op.sequence_no, operation_no=op.operation_no,
                operation_name=op.operation_name_snapshot, planned_quantity=float(op.planned_quantity),
                good_quantity=float(op.good_quantity), scrap_quantity=float(op.scrap_quantity),
                rework_quantity=float(op.rework_quantity), status_code=op.status_code,
                is_imported_snapshot=getattr(op, "is_imported_snapshot", False),
                status_label=STATUS_LABELS.get(op.status_code, op.status_code),
                **plans[op.id],
                actual_started_at=summaries[op.id].started_at if op.id in summaries else None,
                actual_finished_at=summaries[op.id].finished_at if op.id in summaries and op.status_code == "completed" else None,
            ) for op in sorted(operations, key=lambda op: (op.sequence_no, str(op.id)))
                if op.work_order_id == work_order.id and op.org_id == work_order.org_id],
            updated_at=work_order.updated_at,
        )

    async def list_work_orders(self, query: MesWorkOrderListQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_work_orders(session, query, user)
            all_operations = await repository.operations_for_orders(session, [row.id for row in rows])
            executions = await repository.execution_summaries(session, [op.id for op in all_operations])
            by_order = {}
            for operation in all_operations:
                by_order.setdefault(operation.work_order_id, []).append(operation)
            items = []
            projects = await repository.projects(session, {row.production_order_id for row in rows if row.production_order_id})
            names = await user_display_names(session, {row.created_by for row in rows if row.created_by})
            for work_order in rows:
                operations = by_order.get(work_order.id, [])
                item = self._work_order_item(work_order, len(operations), sum(item.status_code == "completed" for item in operations), operations=operations, execution_summaries=executions)
                item.creator_name = names.get(work_order.created_by)
                if project := projects.get(work_order.production_order_id):
                    item.production_order_no, item.project_name = project.production_order_no, project.project_name
                    item.customer_no, item.customer_name = project.customer_no_snapshot, project.customer_name_snapshot
                items.append(item.model_dump(mode="json"))
            return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def work_order_detail(self, work_order_id: UUID, user: AuthenticatedUser) -> MesWorkOrderDetail:
        async with get_session_context() as session:
            work_order = await repository.get_work_order(session, work_order_id, user)
            if work_order is None:
                raise AppException("生产工单不存在或当前账号无权查看", status_code=HTTPStatus.NOT_FOUND)
            operations = await repository.work_order_operations(session, work_order.id)
            task_items = await self._task_items(session, [(task, work_order) for task in operations])
            events = await repository.order_events(session, work_order.id)
            source = await repository.get_work_order(session, work_order.source_work_order_id, user) if work_order.source_work_order_id else None
            from .inventory_service import inventory_service
            return MesWorkOrderDetail(
                **self._work_order_item(work_order, len(operations), sum(item.status_code == "completed" for item in operations), operations=operations).model_dump(),
                operations=task_items,
                note=work_order.note,
                source_work_order_no=source.work_order_no if source else None,
                can_edit_configuration=work_order.status_code in {"draft", "released"} and not await repository.history_exists(session, work_order.id) and not await inventory_service.has_history(session, work_order.id),
                events=[{"id": str(row.id), "event_type_code": row.event_type_code, "from_status_code": row.from_status_code,
                         "to_status_code": row.to_status_code, "version_no": row.version_no, "note": row.note, "created_at": row.created_at.isoformat()} for row in events],
            )

    async def list_reports(self, query: ProductionReportListQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            if query.operation_id or query.work_order_id:
                if "mes:work_order:list" not in user.permissions:
                    raise _forbidden("查看工序报工记录还需要生产工单查询权限")
                if query.operation_id:
                    pair = await repository.get_task(session, query.operation_id, user, permission="mes:work_order:list")
                    if pair is None or pair[0].org_id != pair[1].org_id or (query.work_order_id and pair[1].id != query.work_order_id):
                        raise AppException("工序不存在或无权查看", HTTPStatus.NOT_FOUND)
                elif await repository.get_work_order(session, query.work_order_id, user) is None:
                    raise AppException("工单不存在或无权查看", HTTPStatus.NOT_FOUND)
            rows, total = await repository.list_reports(session, query, user)
            names = await user_display_names(session, {report.created_by for report, _, _ in rows if report.created_by})
            items = [
                ProductionReportItem(
                    id=report.id,
                    operation_id=operation.id,
                    work_order_id=work_order.id,
                    report_no=report.report_no,
                    work_order_no=work_order.work_order_no,
                    operation_no=operation.operation_no,
                    operation_name=getattr(report, "operation_name_snapshot", None) or operation.operation_name_snapshot,
                    product_item_no=work_order.product_item_no_snapshot,
                    product_item_name=work_order.product_item_name_snapshot,
                    good_quantity=float(report.good_quantity),
                    scrap_quantity=float(report.scrap_quantity),
                    rework_quantity=float(report.rework_quantity),
                    labor_minutes=_number(report.labor_minutes),
                    machine_minutes=_number(report.machine_minutes),
                    exception_type_code=report.exception_type_code,
                    status_code=report.status_code,
                    reported_at=report.reported_at,
                    source_code=report.source_code,
                    created_by=report.created_by,
                    reporter_name=names.get(report.created_by), note=report.note,
                ).model_dump(mode="json")
                for report, operation, work_order in rows
            ]
            return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def detail(self, task_id: UUID, user: AuthenticatedUser, *, permission: str | None = None) -> ProductionTaskDetail:
        async with get_session_context() as session:
            permission = permission or (MES_MANAGE_PERMISSION if MES_MANAGE_PERMISSION in user.permissions else MES_TASK_PERMISSION)
            pair = await repository.get_task(session, task_id, user, permission=permission)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权查看", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            await self._ensure_task_access(session, task, user)
            return await self._detail(session, task, work_order, user)

    async def manager_detail(self, task_id: UUID, user: AuthenticatedUser) -> ProductionTaskDetail:
        # Work-order readers may inspect only operations belonging to a readable order.
        permission = next(key for key in [MES_MANAGE_PERMISSION, "mes:operation_task:list", "mes:work_order:list"] if key in user.permissions)
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, permission=permission)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权查看", status_code=HTTPStatus.NOT_FOUND)
            return await self._detail(session, *pair, user)

    async def creation_options(self, kind: str, query: MesOptionQuery, user: AuthenticatedUser, org_id: UUID | None = None, *, for_edit=False):
        async with get_session_context() as session:
            permission = "mes:work_order:create" if "mes:work_order:create" in user.permissions else "mes:work_order:manage"
            if for_edit:
                if "mes:work_order:manage" not in user.permissions: raise _forbidden("无权管理生产工单")
                permission = "mes:work_order:manage"
            if kind == "products":
                return await list_active_item_options(session, query.keyword, query.limit)
            if kind == "organizations":
                return await list_writable_org_options(session, user, permission, query.keyword, query.limit)
            org_id = resolve_write_org_id(user, org_id, permission)
            return await list_assignee_options(session, user, org_id, permission, query.keyword, query.limit)

    async def dispatch_options(self, task_id: UUID, query: MesOptionQuery, user: AuthenticatedUser):
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, permission=MES_MANAGE_PERMISSION)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权派工", status_code=HTTPStatus.NOT_FOUND)
            return await repository.production_dispatch_options(session, pair[0], query.keyword, query.limit)

    async def _validate_template(self, session, body, user, org_id, *, permission="mes:work_order:create"):
        if body.process_template_id is None:
            if body.process_template_version_snapshot is not None:
                raise AppException("模板修订号缺少对应模板")
            return
        if permission not in user.permissions:
            raise _forbidden("没有当前工单操作的工艺路线选用权限")
        template = await production_repository.template(session, body.process_template_id, user, permission=permission, lock=True)
        if template is None or not template.is_active or template.org_id != org_id or template.product_item_id not in {None, body.product_item_id}:
            raise AppException("工艺路线不存在、已停用或不适用于当前组织和产品")
        if template.version_no != body.process_template_version_snapshot:
            raise _conflict("工艺路线已更新，请重新选用后再保存")

    async def _create_order(self, session, body, user, *, production_order_id=None, permission="mes:work_order:create"):
        org_id = resolve_write_org_id(user, body.org_id, permission)
        item = await get_active_item(session, body.product_item_id)
        if item is None:
            raise AppException("生产产品物料不存在或未启用")
        # md_item is shared within this tenant and has no org_id. The order's
        # organization is validated separately through resolve_write_org_id.
        if await repository.work_order_no_exists(session, org_id, body.work_order_no):
            raise _conflict("该组织已存在相同工单号，请更换工单号")
        if body.source_work_order_id:
            source = await repository.get_work_order(session, body.source_work_order_id, user, permission=permission, for_update=True)
            if source is None or source.org_id != org_id or source.product_item_id != body.product_item_id:
                raise AppException("返修来源不存在、无权访问或与当前产品/组织不一致")
            await self._ensure_no_pending_change(session, source.id)
            if source.status_code in {"draft", "cancelled"} or body.planned_quantity > source.planned_quantity:
                raise AppException("返修来源尚未发布或数量超过原工单计划")
        if body.rework_report_id:
            if not body.source_work_order_id or "mes:production_report:list" not in user.permissions:
                raise _forbidden("从返工明细生成返修需要报工查询权限及来源工单")
            # The source parent is already locked above; all allocations of this report serialize here.
            report_pair = await production_repository.rework_report(session, body.rework_report_id, user)
            if report_pair is None or report_pair[2].id != body.source_work_order_id:
                raise AppException("返工报工不存在、无权查看或与来源工单不一致")
            allocated = await production_repository.allocated_quantity(session, body.rework_report_id)
            if allocated + body.planned_quantity > report_pair[0].rework_quantity:
                raise _conflict("安排数量超过尚未安排的返工数量，请刷新后重试")
        await self._validate_template(session, body, user, org_id, permission=permission)
        for operation in body.operations:
            if operation.assigned_user_id and not await repository.is_active_assignee(session, operation.assigned_user_id, org_id):
                raise AppException("派工人员不存在、已停用或不可访问工单组织")
        work_order = MesWorkOrder(
            org_id=org_id,
            production_order_id=production_order_id,
            source_work_order_id=body.source_work_order_id,
            process_template_id=body.process_template_id,
            process_template_version_snapshot=body.process_template_version_snapshot,
            order_type_code="repair" if body.source_work_order_id else "production",
            note=body.note,
            work_order_no=body.work_order_no.strip(),
            product_item_id=item.id,
            product_item_no_snapshot=item.item_no,
            product_item_name_snapshot=item.item_name,
            unit_code=item.unit_code,
            planned_quantity=body.planned_quantity,
            priority_code=body.priority_code,
            status_code="released" if body.publish else "draft",
            processing_type_code=body.processing_type_code,
            **{field: getattr(body, field, None) for field in ("material_name_snapshot", "heat_treatment_snapshot", "surface_treatment_snapshot", "process_requirement_snapshot", "outsourced_due_at")},
            due_at=body.due_at,
            released_at=utc_now() if body.publish else None,
            released_by=user.user_id if body.publish else None,
            created_by=user.user_id,
            updated_by=user.user_id,
        )
        repository.add(session, work_order)
        await session.flush()
        if body.rework_report_id:
            repository.add(session, MesReworkAssignment(org_id=org_id, report_id=body.rework_report_id, work_order_id=work_order.id, created_by=user.user_id))
        bindings = await prepare_operations(session, body.operations, org_id)
        first_task = None
        configured_at = utc_now()
        for sequence_no, operation in enumerate(body.operations, start=1):
            task = MesWorkOrderOperation(
                org_id=org_id,
                work_order_id=work_order.id,
                **bindings[sequence_no-1],
                operation_no=operation.operation_no.strip(),
                operation_name_snapshot=operation.operation_name.strip(),
                operation_description=operation.operation_description,
                sequence_no=sequence_no,
                work_center_name_snapshot=operation.work_center_name,
                workstation_name_snapshot=operation.workstation_name,
                assigned_user_id=operation.assigned_user_id,
                planned_quantity=operation.planned_quantity or body.planned_quantity,
                standard_minutes_per_unit=operation.standard_minutes_per_unit,
                created_at=configured_at,
                status_code=("dispatched" if operation.assigned_user_id else "pending") if body.publish else "draft",
                priority_code=body.priority_code,
                is_quality_required=operation.is_quality_required,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            repository.add(session, task)
            await session.flush()
            self._event(session, task, user, "created", to_status=task.status_code, note="生产工单创建并生成工序任务")
            if first_task is None:
                first_task = task
        repository.add(session, MesWorkOrderEvent(org_id=org_id, work_order_id=work_order.id, event_type_code="created", to_status_code=work_order.status_code, version_no=work_order.version_no, created_by=user.user_id))
        await bind_product_drawings(session, work_order, body, user)
        return work_order, first_task

    async def create_work_order(self, body: WorkOrderCreate, user: AuthenticatedUser):
        async with get_session_context() as session:
            order, first_task = await self._create_order(session, body, user)
            await session.commit()
            if first_task:
                return await self._detail(session, first_task, order, user)
            return {"id": str(order.id), "work_order_id": str(order.id)}

    async def create_production_order(self, body: ProductionOrderCreate, user: AuthenticatedUser):
        async with get_session_context() as session:
            result = await self.create_production_in_session(session, body, user)
            await session.commit()
            return result

    async def create_production_in_session(self, session, body: ProductionOrderCreate, user: AuthenticatedUser, *, source_order_id=None, source_line_ids=None):
        """订单等 MES 来源在自己的事务中创建整张生产工单；此入口不提交。"""
        if "mes:work_order:create" not in user.permissions:
            raise AppException("缺少生产工单创建权限", 403)
        org_id = resolve_write_org_id(user, body.org_id, "mes:work_order:create")
        customer_no, customer_name = await customer_snapshot(session, body, org_id)
        project = MesProductionOrder(org_id=org_id, source_sales_order_id=source_order_id, customer_id=body.customer_id, production_order_no=body.production_order_no,
            project_name=body.project_name, customer_no_snapshot=customer_no, customer_name_snapshot=customer_name,
            note=body.note, created_by=user.user_id, updated_by=user.user_id)
        repository.add(session, project)
        await session.flush()
        ids = []
        for index, product in enumerate(body.products):
            if product.org_id and product.org_id != org_id:
                raise AppException("同一项目的产品必须属于相同组织")
            order, _ = await self._create_order(session, product.model_copy(update={"org_id": org_id}), user, production_order_id=project.id)
            if source_line_ids is not None:
                order.source_sales_order_line_id = source_line_ids[index]
            ids.append(str(order.id))
        return {"id": str(project.id), "work_order_ids": ids}

    async def list_production_orders(self, query, user):
        async with get_session_context() as session:
            projects, orders, total = await repository.list_projects(session, query, user)
            items = []
            all_operations = await repository.operations_for_orders(session, [row.id for row in orders])
            executions = await repository.execution_summaries(session, [op.id for op in all_operations])
            for project in projects:
                children = [row for row in orders if row.production_order_id == project.id]
                child_ids = {row.id for row in children}
                operations = [row for row in all_operations if row.work_order_id in child_ids]
                configured = {row.work_order_id for row in operations}
                display_status = project_order_status(children, configured)
                items.append({"id": str(project.id), "org_id": str(project.org_id), "version_no": project.version_no, "note": project.note, "production_order_no": project.production_order_no,
                    "display_status_key": display_status, "status_label": ORDER_STATUS_LABELS[display_status],
                    "project_name": project.project_name, "customer_id": str(project.customer_id) if project.customer_id else None, "customer_no": project.customer_no_snapshot, "customer_name": project.customer_name_snapshot,
                    "created_at": project.created_at.isoformat(), "product_count": len(children),
                    "source_product_count_snapshot": getattr(project, "source_product_count_snapshot", None),
                    "is_import_incomplete": getattr(project, "is_import_incomplete", False),
                    "configured_count": len(configured), "released_count": sum(row.status_code != "draft" and row.status_code != "cancelled" for row in children),
                    "completed_count": sum(row.status_code == "completed" for row in children),
                    "orders": [self._work_order_item(row, sum(op.work_order_id == row.id for op in operations), sum(op.work_order_id == row.id and op.status_code == "completed" for op in operations), operations=[op for op in operations if op.work_order_id == row.id], execution_summaries=executions).model_dump(mode="json") for row in children]})
            return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def update_production_order(self, project_id, body, user):
        async with get_session_context() as session:
            project = await repository.get_project(session, project_id, user, "mes:work_order:manage", for_update=True)
            if project is None: raise AppException("项目不存在或无权访问", 404)
            if getattr(project, "source_sales_order_id", None) and (body.products or body.customer_id != project.customer_id):
                raise _conflict("客户订单生成的工单不能追加非订单货品或更换客户，请从客户订单安排生产")
            if project.version_no != body.version_no: raise _conflict("项目已更新，请刷新后重试")
            if body.org_id and body.org_id != project.org_id: raise AppException("不能变更项目所属组织")
            if body.products and "mes:work_order:create" not in user.permissions: raise _forbidden("追加产品需要创建生产工单权限")
            project.production_order_no, project.project_name = body.production_order_no, body.project_name
            customer_no, customer_name = await customer_snapshot(session, body, project.org_id, project)
            project.customer_id = body.customer_id
            project.customer_no_snapshot, project.customer_name_snapshot, project.note = customer_no, customer_name, body.note
            project.version_no += 1
            project.updated_at, project.updated_by = utc_now(), user.user_id
            for product in body.products:
                if product.org_id and product.org_id != project.org_id: raise AppException("追加产品的组织与项目不一致")
                await self._create_order(session, product.model_copy(update={"org_id": project.org_id}), user, production_order_id=project.id)
            await session.commit()
            return {"id": str(project.id)}

    async def dispatch(self, task_id: UUID, body: ProductionDispatchBody, user: AuthenticatedUser) -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True, permission=MES_MANAGE_PERMISSION)
            if pair is None:
                raise AppException("生产任务不存在", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            self._check_version(task, body.version_no)
            if task.status_code not in {"pending", "dispatched"}:
                raise _conflict("当前状态不允许派工")
            if not task.process_id:
                raise AppException("该工序未关联工艺档案，请先配置正式工艺再派工")
            from .archive_repository import archive_repository
            await archive_repository.lock_organization(session, task.org_id)
            if not await repository.production_dispatch_options(session, task, person_id=body.production_person_id):
                raise AppException("请选择工单所属组织内已启用且具备该工艺有效资格的生产人员")
            previous = task.status_code
            task.assigned_production_person_id = body.production_person_id
            task.assigned_user_id = None
            task.status_code = "dispatched"
            self._touch(task, work_order, user)
            self._event(session, task, user, "dispatched", note=body.note, from_status=previous, to_status=task.status_code)
            await session.commit()
            return await self._detail(session, task, work_order, user)

    async def track_in(self, task_id: UUID, body: ProductionActionBody, user: AuthenticatedUser) -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权执行", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            await self._ensure_task_access(session, task, user)
            self._check_version(task, body.version_no)
            if task.status_code not in {"pending", "dispatched"}:
                raise _conflict("当前状态不允许开工")
            operations = await repository.work_order_operations(session, work_order.id)
            from . import schedule_execution
            scheduled = await schedule_execution.before_start(session,task,work_order,body,user)
            if scheduled is None and (not task.is_predecessor_ready or any(
                row.sequence_no < task.sequence_no and row.status_code != "completed"
                for row in operations
            )):
                raise _conflict("前置工序尚未满足，不能开工")
            current = await repository.current_execution(session, task.id, for_update=True)
            if current is not None:
                raise _conflict("该任务已有未结束的执行区间")
            assignment = scheduled if scheduled is not None else await schedule_execution.manual_assignment(
                session, task, body,
            )
            execution = MesOperationExecution(
                **assignment,
                org_id=task.org_id,
                operation_id=task.id,
                worker_user_id=user.user_id,
                worker_name_snapshot=(user.display_name or "当前用户").strip(),
                workstation_name_snapshot=task.workstation_name_snapshot,
                status_code="in_progress",
                tracked_in_at=utc_now(),
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            repository.add(session, execution)
            # 仅填外键 ID，没有 ORM relationship；先写入执行区间，避免事件先插入触发外键失败。
            # flush 不提交，后续事件或状态更新失败时仍由整个事务回滚。
            await session.flush()
            previous = task.status_code
            task.status_code = "in_progress"
            if work_order.status_code == "released":
                work_order.status_code = "in_progress"
            self._touch(task, work_order, user)
            self._event(session, task, user, "tracked_in", execution_id=execution.id, note=body.note, from_status=previous, to_status=task.status_code)
            await session.commit()
            return await self._detail(session, task, work_order, user)

    async def hold(self, task_id: UUID, body: ProductionActionBody, user: AuthenticatedUser) -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权执行", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            await self._ensure_task_access(session, task, user)
            self._check_version(task, body.version_no)
            if task.status_code not in {"in_progress", "dispatched"}:
                raise _conflict("当前状态不允许暂停")
            current = await repository.current_execution(session, task.id, for_update=True)
            previous = task.status_code
            task.status_code = "paused"
            if current is not None:
                if body.execution_id and body.execution_id != current.id:
                    raise _conflict("执行区间已变化，请刷新任务")
                current.status_code = "paused"
                current.held_at = utc_now()
                current.updated_at = utc_now()
                current.updated_by = user.user_id
                from . import schedule_execution
                await schedule_execution.set_phase_status(session,current,"paused",user)
            self._touch(task, work_order, user)
            self._event(session, task, user, "held", execution_id=current.id if current else None, note=body.note, from_status=previous, to_status=task.status_code)
            await session.commit()
            return await self._detail(session, task, work_order, user)

    async def release(self, task_id: UUID, body: ProductionActionBody, user: AuthenticatedUser) -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权执行", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            await self._ensure_task_access(session, task, user)
            self._check_version(task, body.version_no)
            if task.status_code != "paused":
                raise _conflict("当前状态不允许恢复")
            current = await repository.current_execution(session, task.id, for_update=True)
            if current is None or current.status_code != "paused":
                raise _conflict("没有可恢复的执行区间")
            if body.execution_id and body.execution_id != current.id:
                raise _conflict("执行区间已变化，请刷新任务")
            from . import schedule_execution
            await schedule_execution.before_resume(session,task,work_order,current,user)
            previous = task.status_code
            task.status_code = "in_progress"
            current.status_code = "in_progress"
            current.updated_at = utc_now()
            current.updated_by = user.user_id
            self._touch(task, work_order, user)
            self._event(session, task, user, "released", execution_id=current.id, note=body.note, from_status=previous, to_status=task.status_code)
            await session.commit()
            return await self._detail(session, task, work_order, user)

    async def report(self, task_id: UUID, body: ProductionReportBody, user: AuthenticatedUser, *, source_code="mini_program") -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权执行", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            await self._ensure_task_access(session, task, user)
            existing = await repository.find_report_by_idempotency(session, user.user_id, body.idempotency_key)
            if existing is not None:
                if existing.operation_id != task.id:
                    raise _conflict("该幂等键已用于其他生产任务，请重新提交")
                if any(getattr(existing, field) != getattr(body, field) for field in ("good_quantity", "scrap_quantity", "rework_quantity", "labor_minutes", "machine_minutes")):
                    raise _conflict("该幂等键对应的报工内容不同，请刷新后重试")
                return await self._detail(session, task, work_order, user)
            self._check_version(task, body.version_no)
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            if task.status_code != "in_progress":
                raise _conflict("当前状态不允许现场报工")
            current = await repository.current_execution(session, task.id, for_update=True)
            if current is None:
                raise _conflict("请先开工后再报工")
            if body.execution_id and body.execution_id != current.id:
                raise _conflict("执行区间已变化，请刷新任务")
            if body.good_quantity + body.scrap_quantity + body.rework_quantity <= 0:
                if not current.production_phase_id or not ((body.labor_minutes or 0)>0 or (body.machine_minutes or 0)>0):
                    raise AppException("至少填写一项产出数量；返工复作可仅登记实际工时")
            from . import schedule_execution
            await schedule_execution.validate_report(session,current,body,user)
            already_reported = task.good_quantity + task.scrap_quantity + task.rework_quantity
            if already_reported + body.good_quantity + body.scrap_quantity + body.rework_quantity > task.planned_quantity:
                raise _conflict("本次报工数量超过工序剩余数量")
            report = MesProductionReport(
                org_id=task.org_id,
                report_no=f"MES-RP-{uuid7().hex[:20].upper()}",
                operation_id=task.id,
                execution_id=current.id,
                good_quantity=body.good_quantity,
                scrap_quantity=body.scrap_quantity,
                rework_quantity=body.rework_quantity,
                labor_minutes=body.labor_minutes,
                machine_minutes=body.machine_minutes,
                exception_type_code=body.exception_type_code,
                note=body.note,
                idempotency_key=body.idempotency_key,
                source_code=source_code,
                status_code="posted",
                reported_at=utc_now(),
                created_by=user.user_id,
            )
            repository.add(session, report)
            task.good_quantity += body.good_quantity
            task.scrap_quantity += body.scrap_quantity
            task.rework_quantity += body.rework_quantity
            if body.labor_minutes is not None:
                current.labor_minutes = (current.labor_minutes or Decimal("0")) + body.labor_minutes
            if body.machine_minutes is not None:
                current.machine_minutes = (current.machine_minutes or Decimal("0")) + body.machine_minutes
            self._touch(task, work_order, user)
            self._event(session, task, user, "production_reported", execution_id=current.id, note=body.note or f"报工合格 {body.good_quantity}，报废 {body.scrap_quantity}，返工 {body.rework_quantity}", from_status=task.status_code, to_status=task.status_code)
            await session.flush()
            if body.attachment_ids:
                await file_service.bind(
                    session,
                    body.attachment_ids,
                    user=user,
                    org_id=task.org_id,
                    business_type_code=BUSINESS_TYPE,
                    business_id=report.id,
                    scene_code=SCENE_REPORT,
                )
            await session.commit()
            return await self._detail(session, task, work_order, user)

    async def track_out(self, task_id: UUID, body: ProductionActionBody, user: AuthenticatedUser) -> ProductionTaskDetail:
        async with get_session_context() as session:
            pair = await repository.get_task(session, task_id, user, for_update=True)
            if pair is None:
                raise AppException("生产任务不存在或当前账号无权执行", status_code=HTTPStatus.NOT_FOUND)
            task, work_order = pair
            self._ensure_order_executable(work_order)
            await self._ensure_no_pending_change(session, work_order.id)
            await self._ensure_task_access(session, task, user)
            self._check_version(task, body.version_no)
            if task.status_code not in {"in_progress", "paused"}:
                raise _conflict("当前状态不允许完工")
            current = await repository.current_execution(session, task.id, for_update=True)
            if current is None:
                raise _conflict("没有未结束的执行区间")
            if body.execution_id and body.execution_id != current.id:
                raise _conflict("执行区间已变化，请刷新任务")
            previous = task.status_code
            current.status_code = "completed"
            from .schedule_execution import validate_finish
            await validate_finish(session,current)
            current.tracked_out_at = utc_now()
            current.updated_at = utc_now()
            current.updated_by = user.user_id
            total = task.good_quantity + task.scrap_quantity + task.rework_quantity
            from . import schedule_execution
            scheduled = await schedule_execution.after_track_out(session,task,work_order,current,user)
            if scheduled:
                pass
            elif task.is_quality_required:
                task.status_code = "waiting_quality"
            elif total >= task.planned_quantity:
                task.status_code = "completed"
                operations = await repository.work_order_operations(session, work_order.id)
                if operations and all(row.status_code == "completed" for row in operations):
                    final_operation = max(operations, key=lambda row: row.sequence_no)
                    work_order.status_code = "completed"
                    work_order.closed_at, work_order.closed_by = utc_now(), user.user_id
                    work_order.good_quantity = final_operation.good_quantity
                    work_order.scrap_quantity = final_operation.scrap_quantity
                    work_order.rework_quantity = final_operation.rework_quantity
            else:
                task.status_code = "pending"
            self._touch(task, work_order, user)
            self._event(session, task, user, "tracked_out", execution_id=current.id, note=body.note, from_status=previous, to_status=task.status_code)
            if work_order.status_code == "completed":
                repository.add(session, MesWorkOrderEvent(org_id=task.org_id, work_order_id=work_order.id, event_type_code="completed",
                    to_status_code="completed", version_no=work_order.version_no, note="全部工序完成，自动完结", created_by=user.user_id))
            await session.commit()
            return await self._detail(session, task, work_order, user)


    async def change_execution_stage(self,task_id,body,user):
        async with get_session_context() as session:
            pair=await repository.get_task(session,task_id,user,for_update=True)
            if pair is None:raise AppException("任务不存在或无权执行",404)
            task,order=pair
            self._ensure_order_executable(order);await self._ensure_task_access(session,task,user);self._check_version(task,body.version_no)
            await self._ensure_no_pending_change(session,order.id)
            execution=await repository.current_execution(session,task.id,for_update=True)
            if execution is None or task.status_code!="in_progress" or execution.status_code!="in_progress":raise AppException("请先开始或恢复执行",409)
            if body.execution_id!=execution.id or not body.segment_type_code:raise AppException("请携带当前执行及目标阶段",409)
            from .schedule_execution import change_stage
            await change_stage(session,task,order,execution,body.segment_type_code,user)
            self._touch(task,order,user)
            label={"load":"装料","run":"自动加工","unload":"卸料","external_return":"确认委外回厂"}.get(body.segment_type_code,body.segment_type_code)
            self._event(session,task,user,"phase_changed",execution_id=execution.id,note=f"实际阶段：{label}")
            await session.commit()
            return await self._detail(session,task,order,user)


service = MesService()
