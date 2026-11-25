"""生产工单配置和生命周期；所有查询经 Repository，写入围绕完整动作提交。"""
from .archive_binding import prepare_operations
from http import HTTPStatus

from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.inventory.public import get_active_item
from app.modules.user_profile.public import user_display_names

from .models import MesWorkOrderEvent, MesWorkOrderOperation
from .repository import repository
from .service import service, _conflict
from .schemas import WorkOrderCommand

MANAGE = "mes:work_order:manage"
ACTION_STATES = {
    "publish": {"draft"}, "withdraw": {"released"}, "pause": {"released", "in_progress"},
    "resume": {"paused"}, "complete": {"released", "in_progress"},
    "cancel": {"draft", "released"}, "delete": {"draft", "cancelled"},
}
EVENTS = {"publish": "published", "withdraw": "withdrawn", "pause": "paused", "resume": "resumed", "complete": "completed", "cancel": "cancelled", "delete": "deleted"}


def ensure_action(order, action, version_no, *, history=False, open_execution=False, waiting_quality=False, operation_count=0):
    """可离线验证的状态规则；暂停不覆盖工序自身的暂停状态。"""
    if order.version_no != version_no:
        raise _conflict("工单已被其他人更新，请刷新后重试")
    if action not in ACTION_STATES or order.status_code not in ACTION_STATES[action]:
        raise _conflict("当前工单状态不允许此操作")
    if action == "publish" and not operation_count:
        raise _conflict("下单前请至少配置一道工序")
    if action in {"withdraw", "cancel", "delete"} and history:
        raise _conflict("工单已有执行或报工记录，不能撤回、取消或删除")
    if action == "complete" and (open_execution or waiting_quality):
        raise _conflict("存在未结束的执行区间或待检验工序，不能完结")


def touch(order, user, event, *, note=None, previous=None):
    order.version_no += 1
    order.updated_at, order.updated_by = utc_now(), user.user_id
    return MesWorkOrderEvent(org_id=order.org_id, work_order_id=order.id,
        event_type_code=event, from_status_code=previous, to_status_code=order.status_code,
        version_no=order.version_no, note=note, created_by=user.user_id)


class OrderService:
    async def _get(self, session, order_id, user, *, permission=MANAGE, lock=True):
        order = await repository.get_work_order(session, order_id, user, permission=permission, for_update=lock)
        if order is None:
            raise AppException("生产工单不存在或当前账号无权访问", HTTPStatus.NOT_FOUND)
        return order

    async def definition(self, order_id, user):
        async with get_session_context() as session:
            order = await self._get(session, order_id, user, permission="mes:work_order:list", lock=False)
            operations = await repository.work_order_operations(session, order.id)
            names = await user_display_names(session, {row.assigned_user_id for row in operations if row.assigned_user_id})
            from .inventory_service import inventory_service
            return {"id": str(order.id), "org_id": str(order.org_id), "work_order_no": order.work_order_no,
                "product_item_id": str(order.product_item_id), "product_label": f"{order.product_item_no_snapshot} · {order.product_item_name_snapshot}",
                "unit_name": order.unit_code, "planned_quantity": float(order.planned_quantity), "priority_code": order.priority_code,
                "due_at": order.due_at.isoformat() if order.due_at else None, "note": order.note, "version_no": order.version_no,
                "status_code": order.status_code, "publish": False,
                "processing_type_code": order.processing_type_code,
                **{field: getattr(order, field, None) for field in ("material_name_snapshot", "heat_treatment_snapshot", "surface_treatment_snapshot", "process_requirement_snapshot", "outsourced_due_at")},
                "source_work_order_id": str(order.source_work_order_id) if order.source_work_order_id else None,
                "process_template_id": str(order.process_template_id) if order.process_template_id else None,
                "process_template_version_snapshot": order.process_template_version_snapshot,
                "can_edit_configuration": order.status_code in {"draft", "released"} and not await repository.history_exists(session, order.id) and not await inventory_service.has_history(session, order.id),
                "operations": [{"process_id": str(row.process_id) if row.process_id else None, "equipment_id": str(row.equipment_id) if row.equipment_id else None,
                    "requirement_id": str(row.requirement_id) if row.requirement_id else None, "operation_no": row.operation_no, "operation_name": row.operation_name_snapshot,
                    "planned_quantity": float(row.planned_quantity), "work_center_name": row.work_center_name_snapshot,
                    "standard_minutes_per_unit": float(row.standard_minutes_per_unit) if row.standard_minutes_per_unit is not None else None,
                    "workstation_name": row.workstation_name_snapshot, "assigned_user_id": str(row.assigned_user_id) if row.assigned_user_id else None,
                    "assigned_user_name": names.get(row.assigned_user_id),
                    "is_quality_required": row.is_quality_required, "operation_description": row.operation_description} for row in operations]}

    async def update(self, order_id, body, user):
        async with get_session_context() as session:
            order = await self._get(session, order_id, user)
            if getattr(order, "is_process_change_pending", False):
                raise _conflict("工单有未完成的工艺变更，请先完成变更")
            if getattr(order, "source_sales_order_line_id", None) and (body.product_item_id != order.product_item_id or body.planned_quantity != order.planned_quantity):
                raise _conflict("客户订单来源的货品数量及生产物料不能直接更换，请取消未执行工单后从订单重新安排")
            if body.drawing_attachment_ids is not None or body.drawing_revision_label is not None:
                raise _conflict("已有工单的图纸请在工单详情的“工单图纸”中维护")
            await service._ensure_no_pending_change(session, order.id)
            if order.version_no != body.version_no:
                raise _conflict("工单已被其他人更新，请刷新后重试")
            if order.status_code not in {"draft", "released", "in_progress", "paused"}:
                raise _conflict("已结束工单不能变更")
            if body.org_id and body.org_id != order.org_id or body.source_work_order_id != order.source_work_order_id:
                raise _conflict("不能变更工单组织或返修来源")
            from .inventory_service import inventory_service
            editable = order.status_code in {"draft", "released"} and not await repository.history_exists(session, order.id) and not await inventory_service.has_history(session, order.id)
            manufacturing = ("material_name_snapshot", "heat_treatment_snapshot", "surface_treatment_snapshot", "process_requirement_snapshot", "outsourced_due_at")
            if not editable and any(field in body.model_fields_set and getattr(body, field) != getattr(order, field, None) for field in manufacturing):
                raise _conflict("已有执行记录，不能更改材料、处理要求或外协交期")
            if editable:
                for field in manufacturing:
                    if field in body.model_fields_set: setattr(order, field, getattr(body, field))
            if not editable:
                if body.processing_type_code != order.processing_type_code:
                    raise _conflict("已有执行记录，不能变更货品类型（自制/委外）")
                if (body.process_template_id, body.process_template_version_snapshot) != (order.process_template_id, order.process_template_version_snapshot):
                    raise _conflict("已有执行记录，不能变更工艺模板来源")
                # Once execution starts, only delivery, priority and note may change.
                if body.product_item_id != order.product_item_id or body.planned_quantity != order.planned_quantity or body.work_order_no != order.work_order_no:
                    raise _conflict("已有执行记录，只能调整交期、优先级和说明")
                current = await repository.work_order_operations(session, order.id)
                def signature(row, existing):
                    return (row.operation_no, row.operation_name_snapshot if existing else row.operation_name,
                        row.planned_quantity or order.planned_quantity, (row.work_center_name_snapshot if existing else row.work_center_name) or None,
                        (row.workstation_name_snapshot if existing else row.workstation_name) or None, row.assigned_user_id,
                        row.is_quality_required, row.operation_description or None,
                        getattr(row, "process_id", None), getattr(row, "equipment_id", None), getattr(row, "requirement_id", None),
                        getattr(row, "standard_minutes_per_unit", None))
                if [signature(row, True) for row in current] != [signature(row, False) for row in body.operations]:
                    raise _conflict("已有执行记录，不能更换或调整生产工序")
            else:
                if (body.process_template_id, body.process_template_version_snapshot) != (order.process_template_id, order.process_template_version_snapshot):
                    await service._validate_template(session, body, user, order.org_id, permission=MANAGE)
                order.process_template_id, order.process_template_version_snapshot = body.process_template_id, body.process_template_version_snapshot
                if order.status_code == "released" and not body.operations:
                    raise _conflict("已下单工单至少保留一道工序")
                if body.work_order_no != order.work_order_no and await repository.work_order_no_exists(session, order.org_id, body.work_order_no):
                    raise _conflict("该组织已存在相同工单号")
                item = await get_active_item(session, body.product_item_id)
                if item is None:
                    raise AppException("产品不存在或未启用")
                if order.source_work_order_id and (body.product_item_id != order.product_item_id or body.planned_quantity > order.planned_quantity):
                    raise AppException("返修产品不能更换，返修数量只能减少")
                for operation in body.operations:
                    if operation.assigned_user_id and not await repository.is_active_assignee(session, operation.assigned_user_id, order.org_id):
                        raise AppException("派工人员不存在、已停用或不可访问工单组织")
                old = await repository.work_order_operations(session, order.id)
                bindings = await prepare_operations(session, body.operations, order.org_id, old)
                def configuration(row, existing):
                    return (row.operation_no, row.operation_name_snapshot if existing else row.operation_name,
                        row.planned_quantity if existing else row.planned_quantity or body.planned_quantity,
                        (row.work_center_name_snapshot if existing else row.work_center_name) or None,
                        (row.workstation_name_snapshot if existing else row.workstation_name) or None,
                        row.assigned_user_id, row.is_quality_required, row.operation_description or None,
                        getattr(row, "process_id", None), getattr(row, "equipment_id", None), getattr(row, "requirement_id", None),
                        getattr(row, "standard_minutes_per_unit", None))
                changed = body.product_item_id != order.product_item_id or body.planned_quantity != order.planned_quantity or [configuration(row, True) for row in old] != [configuration(row, False) for row in body.operations]
                if changed and any(row.planned_start_at is not None for row in old):
                    raise _conflict("工序已有排程，请先清空这些工序的计划时间，再调整产品、数量或工序配置")
                order.work_order_no, order.product_item_id = body.work_order_no, item.id
                order.product_item_no_snapshot, order.product_item_name_snapshot, order.unit_code = item.item_no, item.item_name, item.unit_code
                order.planned_quantity = body.planned_quantity
                order.processing_type_code = body.processing_type_code
                for row in old if changed else []:
                    row.deleted_at, row.deleted_by = utc_now(), user.user_id
                    row.updated_at, row.updated_by = utc_now(), user.user_id
                await session.flush()
                configured_at = utc_now()
                previous_by_number = {row.operation_no: row for row in old}
                for index, row in enumerate(body.operations if changed else [], 1):
                    binding = bindings[index-1]
                    previous_task = previous_by_number.get(row.operation_no)
                    assigned_person = (
                        previous_task.assigned_production_person_id
                        if previous_task and previous_task.process_id == binding.get("process_id") and not row.assigned_user_id
                        else None
                    )
                    task = MesWorkOrderOperation(org_id=order.org_id, work_order_id=order.id, sequence_no=index, **binding,
                        operation_no=row.operation_no, operation_name_snapshot=row.operation_name, planned_quantity=row.planned_quantity or body.planned_quantity,
                        standard_minutes_per_unit=row.standard_minutes_per_unit, created_at=configured_at,
                        work_center_name_snapshot=row.work_center_name, workstation_name_snapshot=row.workstation_name,
                        operation_description=row.operation_description, assigned_user_id=row.assigned_user_id, is_quality_required=row.is_quality_required,
                        assigned_production_person_id=assigned_person,
                        priority_code=body.priority_code,
                        status_code="draft" if order.status_code == "draft" else "dispatched" if assigned_person or row.assigned_user_id else "pending",
                        created_by=user.user_id, updated_by=user.user_id)
                    repository.add(session, task)
            order.due_at, order.priority_code, order.note = body.due_at, body.priority_code, body.note
            # Update dispatch priority for all current tasks, retaining historic configurations.
            await session.flush()
            for task in await repository.work_order_operations(session, order.id):
                task.priority_code = body.priority_code
                task.version_no += 1
                task.updated_at, task.updated_by = utc_now(), user.user_id
            repository.add(session, touch(order, user, "updated", note="变更生产配置" if editable else "变更交期、优先级或说明", previous=order.status_code))
            await session.commit()
            return {"id": str(order.id), "work_order_id": str(order.id)}

    async def _command(self, session, order_id, action, body, user):
        if action == "place":
            action = "publish"  # Keep the existing execution transition and event compatibility.
        order = await self._get(session, order_id, user)
        if getattr(order, "is_process_change_pending", False):
            raise _conflict("工单已因工艺变更暂停，请在变更单完成审批及处置")
        await service._ensure_no_pending_change(session, order.id)
        operations = await repository.work_order_operations(session, order.id)
        if action in {"withdraw", "cancel", "delete"}:
            from .inventory_service import inventory_service
            if await inventory_service.has_active(session, order.id):
                raise _conflict("工单仍有关联库存单据，请先作废或冲销库存业务")
        history = await repository.history_exists(session, order.id) if action in {"withdraw", "cancel", "delete"} else False
        opened = await repository.open_executions_exist(session, order.id) if action == "complete" else False
        ensure_action(order, action, body.version_no, history=history, open_execution=opened,
            waiting_quality=any(row.status_code == "waiting_quality" for row in operations), operation_count=len(operations))
        if action in {"complete", "cancel", "delete"} and not (body.note or "").strip():
            raise AppException("请填写操作理由")
        previous = order.status_code
        if action == "publish":
            # Recheck assignees since a draft can outlive user deactivation.
            for task in operations:
                if task.assigned_user_id and not await repository.is_active_assignee(session, task.assigned_user_id, order.org_id):
                    raise AppException("工序包含已失效的派工人员，请先变更配置")
            if await get_active_item(session, order.product_item_id) is None:
                raise AppException("产品已停用，请先变更配置")
            order.status_code, order.released_at, order.released_by = "released", utc_now(), user.user_id
        elif action == "withdraw":
            order.status_code, order.released_at, order.released_by = "draft", None, None
        elif action == "pause":
            order.resume_status_code, order.status_code = order.status_code, "paused"
        elif action == "resume":
            order.status_code = order.resume_status_code if order.resume_status_code in {"released", "in_progress"} else "released"
            order.resume_status_code = None
        elif action == "complete":
            from .schedule_execution import ensure_order_complete
            await ensure_order_complete(session,order)
            order.status_code, order.closed_at, order.closed_by = "completed", utc_now(), user.user_id
            if operations:
                last = max(operations, key=lambda row: row.sequence_no)
                order.good_quantity, order.scrap_quantity, order.rework_quantity = last.good_quantity, last.scrap_quantity, last.rework_quantity
        elif action == "cancel":
            order.status_code = "cancelled"
        elif action == "delete":
            if await repository.repair_exists(session, order.id):
                raise _conflict("存在关联返修工单，不能删除")
            order.deleted_at, order.deleted_by = utc_now(), user.user_id
        if action in {"publish", "withdraw", "complete", "cancel", "delete"}:
            for task in operations:
                if action == "publish":
                    task.status_code = "dispatched" if task.assigned_production_person_id or task.assigned_user_id else "pending"
                elif action == "withdraw": task.status_code = "draft"
                elif action in {"complete", "cancel"} and task.status_code != "completed": task.status_code = "cancelled"
                elif action == "delete": task.deleted_at, task.deleted_by = utc_now(), user.user_id
                task.version_no += 1
                task.updated_at, task.updated_by = utc_now(), user.user_id
        repository.add(session, touch(order, user, EVENTS[action], note=body.note, previous=previous))
        return {"id": str(order.id), "version_no": order.version_no, "status_code": order.status_code}

    async def command(self, order_id, action, body, user):
        async with get_session_context() as session:
            result = await self._command(session, order_id, action, body, user)
            await session.commit()
            return result

    async def place_project(self, project_id, body, user):
        async with get_session_context() as session:
            project = await repository.get_project(session, project_id, user, MANAGE, for_update=True)
            if project is None:
                raise AppException("工单不存在或无权下单", 404)
            if project.version_no != body.version_no:
                raise _conflict("工单已更新，请刷新后重试")
            orders = await repository.project_orders_for_placement(session, project.id, user)
            if orders is None:
                raise AppException("无权为该工单的全部待下单货品下单", 403)
            submitted = {row.id: row.version_no for row in body.orders}
            if not orders or {row.id: row.version_no for row in orders} != submitted:
                raise _conflict("待下单货品或版本已变化，请刷新后重试")
            # Repository locks UUID order. Every child's check and transition shares this transaction.
            for order in orders:
                await self._command(session, order.id, "place", WorkOrderCommand(version_no=submitted[order.id]), user)
            project.version_no += 1
            project.updated_at, project.updated_by = utc_now(), user.user_id
            await session.commit()
            return {"id": str(project.id), "version_no": project.version_no, "placed_count": len(orders)}


order_service = OrderService()
