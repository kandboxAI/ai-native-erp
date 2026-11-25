"""生产管理编排；人工排程、独立模板、图纸及返工处理均沿用现有权限和事务。"""
from .archive_binding import prepare_operations
from types import SimpleNamespace
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.file.service import register_file_access, service as files
from app.modules.inventory.public import get_active_item
from app.modules.organization.public import list_writable_org_options

from .models import MesProcessTemplate, MesProcessTemplateOperation
from .order_service import touch
from .production_repository import production_repository as repo
from .repository import repository
from .service import service, _conflict
from .archive_service import archive_service
from .archive_models import MesEquipment
from .archive_repository import archive_repository
from .scheduling_repository import scheduling_repository

from .drawing_files import DRAWING_TYPE, DRAWING_SCENE
from .drawing_service import drawing_service


def station_key(task):
    if getattr(task, "equipment_id", None):
        return f"mes.equipment:{task.org_id}:{task.equipment_id}"
    if not (task.workstation_name_snapshot or "").strip():
        return None
    return f"mes.station:{task.org_id}:{task.work_center_name_snapshot or ''}:{task.workstation_name_snapshot}"


def station_keys(task):
    keys = {station_key(task)} - {None}
    if (task.workstation_name_snapshot or "").strip():
        keys.add(f"mes.station:{task.org_id}:{(task.work_center_name_snapshot or '').strip()}:{task.workstation_name_snapshot.strip()}")
    return keys


async def equipment_assignment(session, task, change):
    current_id = getattr(task, "equipment_id", None)
    requested = change.equipment_id if "equipment_id" in change.model_fields_set else current_id
    if requested is None:
        return dict(equipment_id=None, work_center_name_snapshot=None, workstation_name_snapshot=None) if "equipment_id" in change.model_fields_set else {}
    # 清空已有计划不要求重新启用设备；新增安排/换设备须校验当前设备状态和工艺。
    if change.planned_start_at is None and requested == current_id:
        return {}
    equipment = await archive_service.reference(session, MesEquipment, requested, task.org_id)
    if not await archive_repository.equipment_accepts(session, equipment, getattr(task, "process_id", None)):
        raise AppException("计划加工设备所属工艺与该工序不一致，请选择适用设备", 409)
    if requested == current_id: return {}
    return dict(equipment_id=equipment.id, work_center_name_snapshot=equipment.work_center_name, workstation_name_snapshot=equipment.equipment_no)


def validate_schedule(operations, periods):
    """工序顺序是执行约束；人工计划不可在同一工单内倒置或重叠。"""
    previous_end = None
    for task in sorted(operations, key=lambda row: row.sequence_no):
        start, end = periods.get(task.id, (task.planned_start_at, task.planned_end_at))
        if start is not None:
            if previous_end and start < previous_end:
                raise AppException("计划时间与前置工序重叠或顺序倒置，请一起调整相关工序")
            previous_end = end


class ProductionService:
    async def template_organizations(self, query, user):
        async with get_session_context() as session:
            return await list_writable_org_options(session, user, "mes:process_template:manage", query.keyword, query.limit)

    async def schedules(self, query, user):
        if "mes:schedule:list" not in user.permissions: raise AppException("没有生产排程查看权限", 403)
        if query.start_date and query.end_date and query.start_date > query.end_date:
            raise AppException("开始日期不能晚于结束日期", 422)
        async with get_session_context() as session:
            pairs, total = await repo.schedules(session, query, user)
            items = await service._task_items(session, pairs)
            projects = await scheduling_repository.projects(session, list({order.id for _, order in pairs}))
            return dict(items=[dict(**row.model_dump(mode="json"), project_name=projects.get(row.work_order_id)) for row in items], total=total, page=query.page, page_size=query.page_size)

    async def schedule_resources(self, query, user):
        if "mes:schedule:list" not in user.permissions: raise AppException("没有生产排程查看权限", 403)
        async with get_session_context() as session:
            return await scheduling_repository.resources(session, query, user)

    async def schedule_organizations(self, query, user):
        if "mes:schedule:list" not in user.permissions: raise AppException("没有生产排程查看权限", 403)
        async with get_session_context() as session:
            return await list_writable_org_options(session, user, "mes:schedule:list", query.keyword, query.limit)

    async def schedule(self, body, user):
        if "mes:schedule:manage" not in user.permissions: raise AppException("没有生产排程调整权限", 403)
        async with get_session_context() as session:
            mapping = await repo.schedule_parents(session, [row.operation_id for row in body.operations], user)
            if len(mapping) != len(body.operations):
                raise AppException("部分工序不存在或无权排程", 404)
            by_id = {row.operation_id: row for row in body.operations}
            pairs = []
            # Stable parent order prevents competing multi-order updates from locking in reverse order.
            for task_id in sorted(mapping, key=lambda key: (str(mapping[key]), str(key))):
                pair = await repository.get_task(session, task_id, user, permission="mes:schedule:manage", for_update=True)
                if pair is None:
                    raise AppException("工序已变化或无权排程，请刷新", 409)
                task, order = pair
                await service._ensure_no_pending_change(session, order.id)
                service._check_version(task, by_id[task.id].version_no)
                if order.status_code not in {"draft", "released", "in_progress"} or task.status_code not in {"draft", "pending", "dispatched"}:
                    raise _conflict("只允许调整未开始的工序；已暂停或已结束工单不能排程")
                pairs.append(pair)
            from .schedule_execution import guard_manual_schedule
            await guard_manual_schedule(session,pairs,by_id)
            periods = {row.operation_id: (row.planned_start_at, row.planned_end_at) for row in body.operations}
            orders = {order.id: order for _, order in pairs}
            for order in orders.values():
                validate_schedule(await repository.work_order_operations(session, order.id), periods)
            assignments, probes = {}, []
            keys = set()
            await repo.lock_schedule_equipment(session, [(task.org_id, by_id[task.id].equipment_id if "equipment_id" in by_id[task.id].model_fields_set else getattr(task, "equipment_id", None)) for task, _ in pairs])
            for task, _ in pairs:
                assignments[task.id] = await equipment_assignment(session, task, by_id[task.id])
                probe = SimpleNamespace(id=task.id, org_id=task.org_id, equipment_id=getattr(task, "equipment_id", None),
                    work_center_name_snapshot=task.work_center_name_snapshot, workstation_name_snapshot=task.workstation_name_snapshot)
                for name, value in assignments[task.id].items(): setattr(probe, name, value)
                probes.append(probe)
                keys.update(station_keys(task) | station_keys(probe))
            await repo.lock_workstations(session, list(keys))
            for index, task in enumerate(probes):
                start, end = periods[task.id]
                if start and station_key(task):
                    if await repo.station_conflict(session, task, start, end, list(by_id)):
                        raise _conflict("该工作站在所选时段已有生产安排，请调整时间")
                    for other in probes[:index]:
                        other_start, other_end = periods[other.id]
                        if station_keys(other) & station_keys(task) and other_start and start < other_end and end > other_start:
                            raise _conflict("本次排程中同一工作站的工序时间重叠")
            for task, _ in pairs:
                old_station = task.workstation_name_snapshot
                old_start, old_end = task.planned_start_at, task.planned_end_at
                for name, value in assignments[task.id].items(): setattr(task, name, value)
                task.planned_start_at, task.planned_end_at = periods[task.id]
                task.version_no += 1
                task.updated_at, task.updated_by = utc_now(), user.user_id
                start, end = periods[task.id]
                equipment_note = f"；设备：{old_station or '未分配'} → {task.workstation_name_snapshot or '未分配'}" if assignments[task.id] else ""
                service._event(session, task, user, "scheduled", note=f"{body.note.strip()}；原计划：{old_start.isoformat() if old_start else '未安排'} → {old_end.isoformat() if old_end else '未安排'}；现计划：{start.isoformat() if start else '未安排'} → {end.isoformat() if end else '未安排'}{equipment_note}")
            for order in orders.values():
                repository.add(session, touch(order, user, "scheduled", note=body.note.strip(), previous=order.status_code))
            await session.commit()
            return {"updated": len(pairs)}

    @staticmethod
    async def template_item(session, row):
        operations = await repo.template_operations(session, row.id)
        return dict(id=str(row.id), org_id=str(row.org_id), template_no=row.template_no, template_name=row.template_name,
                    product_item_id=str(row.product_item_id) if row.product_item_id else None, version_no=row.version_no,
                    is_active=row.is_active, operations=[dict(process_id=str(op.process_id) if op.process_id else None, equipment_id=str(op.equipment_id) if op.equipment_id else None,
                    requirement_id=str(op.requirement_id) if op.requirement_id else None, operation_no=op.operation_no, operation_name=op.operation_name,
                    standard_minutes_per_unit=float(op.standard_minutes_per_unit) if op.standard_minutes_per_unit is not None else None,
                    operation_description=op.operation_description, work_center_name=op.work_center_name,
                    workstation_name=op.workstation_name, is_quality_required=op.is_quality_required,is_equipment_required_snapshot=op.is_equipment_required_snapshot) for op in operations])

    async def templates(self, query, user):
        async with get_session_context() as session:
            rows, total = await repo.templates(session, query, user)
            return dict(items=[await self.template_item(session, row) for row in rows], total=total, page=query.page, page_size=query.page_size)

    async def template_options(self, query, user, action="create"):
        permission = {"create": "mes:work_order:create", "manage": "mes:work_order:manage"}.get(action)
        if permission is None or permission not in user.permissions:
            raise AppException("没有当前工单操作的工艺路线选用权限", 403)
        if query.org_id is None:
            raise AppException("请先选择组织", 422)
        resolve_write_org_id(user, query.org_id, permission)
        query = query.model_copy(update={"is_active": True})
        async with get_session_context() as session:
            rows, total = await repo.templates(session, query, user, permission=permission)
            items, products = [], {}
            for row in rows:
                item = await self.template_item(session, row)
                product_id = getattr(row, "product_item_id", None)
                if product_id:
                    if product_id not in products:
                        products[product_id] = await get_active_item(session, product_id)
                    product = products[product_id]
                    item["is_product_active"] = product is not None
                    if product is not None:
                        item["product_option"] = dict(value=str(product.id), label=f"{product.item_no} · {product.item_name}", unit=product.unit_code)
                items.append(item)
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)

    async def save_template(self, body, user, template_id=None):
        async with get_session_context() as session:
            org_id = resolve_write_org_id(user, body.org_id, "mes:process_template:manage")
            if body.product_item_id and await get_active_item(session, body.product_item_id) is None:
                raise AppException("模板产品不存在或已停用")
            if await repo.template_no_exists(session, org_id, body.template_no, template_id):
                raise _conflict("该组织已有相同模板编号")
            if template_id:
                row = await repo.template(session, template_id, user, "mes:process_template:manage", lock=True)
                if row is None: raise AppException("模板不存在或无权修改", 404)
                if row.org_id != org_id: raise AppException("不能变更模板所属组织")
                if row.version_no != body.version_no: raise _conflict("模板已更新，请刷新后重试")
                for op in await repo.template_operations(session, row.id):
                    op.deleted_at, op.deleted_by = utc_now(), user.user_id
                    op.updated_at, op.updated_by = utc_now(), user.user_id
                await session.flush()
                row.version_no += 1
            else:
                row = MesProcessTemplate(org_id=org_id, template_no=body.template_no, template_name=body.template_name,
                    created_by=user.user_id, updated_by=user.user_id)
                repository.add(session, row)
                await session.flush()
            row.template_no, row.template_name, row.product_item_id = body.template_no, body.template_name, body.product_item_id
            row.is_active, row.updated_at, row.updated_by = body.is_active, utc_now(), user.user_id
            bindings = await prepare_operations(session, body.operations, org_id)
            for index, op in enumerate(body.operations, 1):
                repository.add(session, MesProcessTemplateOperation(org_id=org_id, template_id=row.id, sequence_no=index, **bindings[index-1],
                    operation_no=op.operation_no, operation_name=op.operation_name, operation_description=op.operation_description,
                    standard_minutes_per_unit=op.standard_minutes_per_unit,
                    work_center_name=op.work_center_name, workstation_name=op.workstation_name, is_quality_required=op.is_quality_required,
                    created_by=user.user_id, updated_by=user.user_id))
            await session.commit()
            return {"id": str(row.id), "version_no": row.version_no}

    async def drawing_access(self, session, user, order_id):
        if "mes:work_order:list" in user.permissions:
            return await repository.get_work_order(session, order_id, user) is not None
        return False

    async def drawings(self, order_id, user):
        return await drawing_service.drawings(order_id, user)

    async def save_drawings(self, order_id, body, user):
        return await drawing_service.save(order_id, body, user)

    async def reworks(self, query, user):
        async with get_session_context() as session:
            rows, links, visible, total = await repo.reworks(session, query, user)
            repair_operations = await repository.operations_for_orders(session, list(visible))
            repair_counts = {}
            for operation in repair_operations:
                repair_counts[operation.work_order_id] = repair_counts.get(operation.work_order_id, 0) + 1
            items = []
            for report, task, order in rows:
                assigned = [repair for report_id, repair in links if report_id == report.id]
                allocated = sum((repair.planned_quantity for repair in assigned), 0)
                items.append(dict(id=str(report.id), report_no=report.report_no, work_order_id=str(order.id),
                    work_order_no=order.work_order_no, operation_name=task.operation_name_snapshot, product_item_name=order.product_item_name_snapshot,
                    rework_quantity=float(report.rework_quantity), allocated_quantity=float(allocated),
                    pending_quantity=float(max(0, report.rework_quantity - allocated)), unit_name=order.unit_code,
                    reported_at=report.reported_at.isoformat(),
                    repairs=[dict(id=str(row.id), work_order_no=row.work_order_no, planned_quantity=float(row.planned_quantity),
                        good_quantity=float(row.good_quantity), status_code=row.status_code,
                        operation_count=repair_counts.get(row.id, 0)) for row in assigned if row.id in visible]))
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)


production_service = ProductionService()
register_file_access(DRAWING_TYPE, production_service.drawing_access)
