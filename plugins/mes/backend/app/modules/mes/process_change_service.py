"""工单工艺变更及已加工件处置。所有过账、审批回调和生效共用工单锁。"""
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.workflow.integration.registry import (
    WorkflowBusinessAdapter, register_business_adapter, register_business_hooks,
)
from app.modules.workflow.runtime.service import workflow_runtime_service

from .archive_binding import prepare_operations
from .archive_models import MesEquipment, MesProcess
from .archive_repository import archive_repository
from .archive_service import archive_service
from .delivery_repository import delivery_repository
from .inventory_service import inventory_service
from .order_service import touch
from .process_change_models import MesWorkOrderProcessChange as Change
from .process_change_repository import process_change_repository as changes
from .report_repository import report_repository
from .repository import repository
from .schedule_execution_repository import repository as phases
from .schemas import WorkOrderCreate, WorkOrderOperationCreate
from .service import service

BUSINESS_TYPE = "mes_process_change"
MANAGE = "mes:work_order:manage"
APPROVE = "mes:process_change:approve"


def remaining_quantity(task):
    return task.planned_quantity - task.good_quantity - task.scrap_quantity - task.rework_quantity


def item(row):
    return row.model_dump(mode="json", exclude={"flex_form"})


class ProcessChangeService:
    async def order(self, session, identifier, user, permission="mes:work_order:list", *, lock=False):
        if permission not in user.permissions:
            raise AppException("缺少工艺变更操作权限", 403)
        # 质检按受影响的工序范围授权，读取原工单沿用工单查询范围。
        scope = "mes:work_order:list" if permission == "mes:quality:inspect" else permission
        order = await repository.get_work_order(session, identifier, user, permission=scope, for_update=lock)
        if order is None:
            raise AppException("生产工单不存在或无权访问", 404)
        if permission == MANAGE and await repository.get_work_order(session, identifier, user) is None:
            raise AppException("生产工单超出查询范围", 404)
        return order

    async def overview(self, identifier, user):
        async with get_session_context() as session:
            order = await self.order(session, identifier, user)
            operations = await repository.work_order_operations(session, order.id)
            return dict(org_id=str(order.org_id), version_no=order.version_no,
                status_code=order.status_code, is_pending=order.is_process_change_pending,
                changes=[item(row) for row in await changes.list(session, order)],
                operations=[dict(id=str(task.id), name=task.operation_name_snapshot,
                    operation_no=task.operation_no, remaining=str(remaining_quantity(task)),
                    good=str(task.good_quantity)) for task in operations])

    async def validate(self, session, order, tasks, task):
        if order.status_code not in {"released", "in_progress", "paused"}:
            raise AppException("仅已下单且尚未结束的工单可申请工艺变更", 409)
        await service._ensure_no_pending_change(session, order.id)
        if await repository.open_executions_exist(session, order.id):
            raise AppException("请先结清现场报工并结束当前执行，再发起或生效工艺变更", 409)
        if task.status_code in {"waiting_quality", "cancelled"}:
            raise AppException("请先完成当前工序检验；已取消工序不可变更", 409)
        if await report_repository.downstream_history(session, task):
            raise AppException("后续工序已有生产记录，请先核对涉及的实物批次及后续处置", 409)
        if await phases.order_phases(session, order.id):
            raise AppException("已有正式排程批次，请先处理既有首件和剩余批量方案", 409)
        if any(row.planned_start_at for row in tasks if row.sequence_no >= task.sequence_no):
            raise AppException("请先在生产排程清空目标及后续工序的计划时间", 409)
        if await inventory_service.has_active(session, order.id, output_only=True) or await delivery_repository.has_shipments(session, order.id):
            raise AppException("工单产出已有入库或出货业务，请先处理对应单据", 409)
        if remaining_quantity(task) < 0:
            raise AppException("工序报工量超过计划，请先核对报工", 409)

    async def target(self, session, order, task, tasks, process_id, equipment_id, remaining):
        await archive_repository.lock_organization(session, order.org_id)
        process = await archive_service.reference(session, MesProcess, process_id, order.org_id)
        if task.process_id == process.id:
            raise AppException("请选择不同的工艺", 422)
        if remaining and process.is_equipment_required and not equipment_id:
            raise AppException("新工艺需要设备，请选择适用的生产设备", 422)
        equipment = await archive_service.reference(session, MesEquipment, equipment_id, order.org_id)
        if equipment and not await archive_repository.equipment_accepts(session, equipment, process.id):
            raise AppException("所选设备不适用新工艺", 422)
        route = [process.id if entry.id == task.id else entry.process_id for entry in tasks]
        dependencies = await archive_repository.dependencies(session, order.org_id)
        visited = set()
        for identifier in route:
            if identifier is None:
                continue
            if any(edge.process_id == identifier and edge.previous_process_id not in visited for edge in dependencies):
                raise AppException("新工艺与本工单的前置或后续工艺不兼容，请核对整条路线", 409)
            visited.add(identifier)
        return process

    async def submit(self, identifier, body, user):
        async with get_session_context() as session:
            order = await self.order(session, identifier, user, MANAGE, lock=True)
            if order.is_process_change_pending or order.version_no != body.version_no:
                raise AppException("工单已有工艺变更或版本已更新，请刷新后重试", 409)
            tasks = await repository.work_order_operations(session, order.id)
            task = next((row for row in tasks if row.id == body.operation_id), None)
            if task is None:
                raise AppException("目标工序不属于这张工单", 404)
            await self.validate(session, order, tasks, task)
            remaining = remaining_quantity(task)
            if body.disposition_code != "keep" and task.good_quantity <= 0:
                raise AppException("目标工序没有已报合格件，不能选择复检或返工", 422)
            process = await self.target(session, order, task, tasks, body.new_process_id, body.new_equipment_id, remaining)
            previous = task.model_dump(mode="json", include={
                "equipment_id", "requirement_id", "operation_description", "work_center_name_snapshot",
                "workstation_name_snapshot", "assigned_user_id", "assigned_production_person_id", "standard_minutes_per_unit",
                "is_quality_required", "is_equipment_required_snapshot", "project_stage_id", "stage_name_snapshot",
            })
            row = Change(org_id=order.org_id, work_order_id=order.id, operation_id=task.id,
                previous_process_id=task.process_id, new_process_id=process.id, new_equipment_id=body.new_equipment_id,
                previous_name_snapshot=task.operation_name_snapshot, new_name_snapshot=process.process_name,
                new_process_version_snapshot=process.version_no, previous_configuration_snapshot=previous,
                remaining_quantity_snapshot=remaining, disposition_quantity_snapshot=task.good_quantity,
                disposition_code=body.disposition_code, previous_order_status_code=order.status_code,
                reason=body.reason, created_by=user.user_id, updated_by=user.user_id)
            session.add(row)
            await session.flush()
            await workflow_runtime_service.start(business_type_code=BUSINESS_TYPE, business_id=row.id, org_id=row.org_id,
                variables={}, starter_choices=body.starter_choices, current_user=user, session=session, start_comment=row.reason)
            await session.commit()
            return item(row)

    async def load(self, session, order, change_id):
        row = await changes.get(session, change_id, lock=True)
        if row is None or row.work_order_id != order.id or row.org_id != order.org_id:
            raise AppException("工艺变更单不存在或无权访问", 404)
        if row.status_code != "approved" or not order.is_process_change_pending:
            raise AppException("请先完成工艺变更审批，或刷新变更单状态", 409)
        return row

    async def dispose(self, identifier, change_id, action, body, user):
        permission = "mes:quality:inspect" if action in {"pass", "rework"} else MANAGE
        async with get_session_context() as session:
            order = await self.order(session, identifier, user, permission, lock=True)
            row = await self.load(session, order, change_id)
            if action == "arrange":
                return await self.arrange(session, order, row, user)
            if action == "cancel":
                if row.repair_order_id:
                    repair = await changes.repair(session, row)
                    if repair is not None and repair.status_code != "cancelled":
                        raise AppException("工艺变更有关联返修工单，请先处理返修工单", 409)
                if not body.note:
                    raise AppException("请填写取消原因", 422)
                row.status_code, row.disposition_note = "cancelled", body.note
                row.updated_at, row.updated_by = utc_now(), user.user_id
                self.restore(session, order, row, user, "process_change_closed")
                await session.commit()
                return item(row)
            tasks = await repository.work_order_operations(session, order.id)
            task = next((entry for entry in tasks if entry.id == row.operation_id), None)
            if task is None:
                raise AppException("原工序已不可用，请核对工单", 409)
            if action in {"pass", "rework"}:
                scoped_task = await repository.get_task(session, task.id, user, permission=permission)
                if scoped_task is None:
                    raise AppException("无权处置该工序的已加工件", 403)
                if row.disposition_code != "reinspect" or not body.note:
                    raise AppException("仅待复检的变更可录入复检结果，请填写依据", 422)
                if action == "rework":
                    row.disposition_code = "rework"
                    row.disposition_note, row.disposition_by = body.note, user.user_id
                    row.updated_at, row.updated_by = utc_now(), user.user_id
                    await session.commit()
                    return item(row)
            elif row.disposition_code == "reinspect":
                raise AppException("请由质检人员确认复检结果", 409)
            if row.disposition_code == "rework":
                repair = await changes.repair(session, row) if row.repair_order_id else None
                if repair is None or repair.status_code != "completed" or repair.good_quantity != row.disposition_quantity_snapshot:
                    raise AppException("请先完成已加工件返工，并确认返工合格数量与待处置数量一致", 409)
                await service._ensure_no_pending_change(session, repair.id)
                repair_operations = await repository.work_order_operations(session, repair.id)
                if not any(entry.process_id == row.new_process_id and entry.status_code == "completed" and
                           entry.good_quantity == row.disposition_quantity_snapshot for entry in repair_operations):
                    raise AppException("返修工单必须使用本次批准的新工艺，并完成全部待返工数量", 409)
            await self.apply(session, order, row, task, tasks, body.note, user)
            await session.commit()
            return item(row)

    async def arrange(self, session, order, row, user):
        if row.disposition_code != "rework":
            raise AppException("仅返工处置可生成返修工单", 409)
        if row.repair_order_id:
            repair = await changes.repair(session, row)
            if repair is not None and repair.status_code != "cancelled":
                return item(row)
        if "mes:work_order:create" not in user.permissions:
            raise AppException("缺少返修工单创建权限", 403)
        repair, _ = await service._create_order(session, WorkOrderCreate(
            org_id=order.org_id, work_order_no=f"GX-FX-{uuid7().hex[-20:]}", product_item_id=order.product_item_id,
            source_work_order_id=order.id, planned_quantity=row.disposition_quantity_snapshot,
            publish=False, priority_code=order.priority_code, due_at=order.due_at,
            note=f"工艺变更返工，原工单 {order.work_order_no}；按 {row.new_name_snapshot} 配置工艺并验收。",
        ), user)
        repair.is_process_change_repair = True
        row.repair_order_id = repair.id
        row.updated_at, row.updated_by = utc_now(), user.user_id
        await session.commit()
        return item(row)

    async def apply(self, session, order, row, task, tasks, note, user):
        await self.validate(session, order, tasks, task)
        if (task.process_id != row.previous_process_id or task.good_quantity != row.disposition_quantity_snapshot
                or remaining_quantity(task) != row.remaining_quantity_snapshot):
            raise AppException("工序工艺或报工数量发生变化，请核对变更单", 409)
        process = await self.target(session, order, task, tasks, row.new_process_id, row.new_equipment_id, row.remaining_quantity_snapshot)
        if process.version_no != row.new_process_version_snapshot:
            raise AppException("新工艺档案在审批后已更新，请核对变更内容", 409)
        await changes.preserve_report_names(session, task)
        if row.remaining_quantity_snapshot:
            configs = [WorkOrderOperationCreate(operation_no=entry.operation_no,
                operation_name=entry.operation_name_snapshot, process_id=entry.process_id,
                equipment_id=entry.equipment_id, requirement_id=entry.requirement_id,
                operation_description=entry.operation_description, work_center_name=entry.work_center_name_snapshot,
                workstation_name=entry.workstation_name_snapshot, is_quality_required=entry.is_quality_required)
                for entry in tasks]
            index = next(i for i, entry in enumerate(tasks) if entry.id == task.id)
            config = configs[index] = WorkOrderOperationCreate(operation_no=task.operation_no,
                operation_name=process.process_name, process_id=process.id, equipment_id=row.new_equipment_id,
                standard_minutes_per_unit=await changes.previous_standard_minutes(session, row),
                is_quality_required=True)
            binding = (await prepare_operations(session, configs, order.org_id, tasks))[index]
            for field, value in binding.items():
                setattr(task, field, value)
            task.operation_name_snapshot = config.operation_name
            task.operation_description = config.operation_description
            task.work_center_name_snapshot, task.workstation_name_snapshot = config.work_center_name, config.workstation_name
            task.standard_minutes_per_unit = config.standard_minutes_per_unit
            task.assigned_user_id = None
            task.assigned_production_person_id = None
            task.is_quality_required = config.is_quality_required
            task.status_code = "pending"
            task.version_no += 1
            task.updated_at, task.updated_by = utc_now(), user.user_id
        row.status_code, row.applied_at = "applied", utc_now()
        row.disposition_note = "\n".join(filter(None, (row.disposition_note, note)))
        row.disposition_by = row.disposition_by or user.user_id
        row.updated_at, row.updated_by = utc_now(), user.user_id
        self.restore(session, order, row, user, "process_changed")

    def restore(self, session, order, row, user, event):
        order.status_code, order.is_process_change_pending = row.previous_order_status_code, False
        session.add(touch(order, user, event, note=row.reason, previous="paused"))

    async def hook(self, event, ctx):
        seed = await changes.get(ctx.session, ctx.business_id)
        if seed is None or seed.org_id != ctx.org_id or ctx.current_user is None:
            raise AppException("工艺变更审批记录无效", 403)
        user = ctx.current_user
        permission = MANAGE if event in {"started", "cancelled"} else APPROVE
        order = await self.order(ctx.session, seed.work_order_id, user, permission, lock=True)
        row = await changes.get(ctx.session, seed.id, lock=True)
        if event == "started":
            if row.status_code != "draft" or row.created_by != user.user_id or order.is_process_change_pending:
                raise AppException("只有申请人可以提交新的工艺变更", 409)
            row.wf_instance_id, row.status_code = ctx.instance_id, "submitted"
            order.is_process_change_pending, order.status_code = True, "paused"
            ctx.session.add(touch(order, user, "process_change_requested", note=row.reason,
                                  previous=row.previous_order_status_code))
        else:
            if row.wf_instance_id != ctx.instance_id or row.status_code != "submitted":
                raise AppException("工艺变更审批状态已更新", 409)
            if event == "completed":
                row.status_code = "approved"
            elif event in {"rejected", "cancelled"}:
                if event == "cancelled" and row.created_by != user.user_id:
                    raise AppException("只有申请人可以撤回工艺变更", 403)
                row.status_code = event
                self.restore(ctx.session, order, row, user, "process_change_closed")
        row.updated_at, row.updated_by = utc_now(), user.user_id


process_change_service = ProcessChangeService()


def hook(event):
    async def handle(ctx):
        await process_change_service.hook(event, ctx)
    return handle


async def detail(session, identifier):
    row = await changes.get(session, identifier)
    if row is None:
        raise AppException("变更记录不存在", 404)
    return {"fields": [{"label": label, "value": value} for label, value in (
        ("原工艺", row.previous_name_snapshot), ("新工艺", row.new_name_snapshot),
        ("剩余数量", str(row.remaining_quantity_snapshot)), ("已加工合格数量", str(row.disposition_quantity_snapshot)),
        ("处置方式", {"keep": "沿用", "reinspect": "复检", "rework": "返工"}[row.disposition_code]),
        ("变更原因", row.reason),
    )], "tables": []}


register_business_hooks(BUSINESS_TYPE, {event: hook(event) for event in (
    "started", "task_completed", "completed", "rejected", "cancelled",
)})
register_business_adapter(WorkflowBusinessAdapter(business_type_code=BUSINESS_TYPE, label="MES 工艺变更",
    start_permission=MANAGE, record_model=Change, detail=detail))
