"""整工序检验：冻结待检产出，失败退回本工序复作，复检前不能流转或入库。"""
from decimal import Decimal
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .models import MesWorkOrderEvent
from .repository import repository
from .quality_repository import quality_repository as repo
from .quality_models import MesQualityInspection
from .service import service, STATUS_LABELS


def require(user, key):
    if key not in user.permissions:
        raise AppException("缺少工序检验权限", 403)


def task_item(task, order):
    return dict(id=str(task.id), work_order_id=str(order.id), org_id=str(task.org_id), work_order_no=order.work_order_no,
        work_order_status_code=order.status_code, product_item_no=order.product_item_no_snapshot, product_item_name=order.product_item_name_snapshot,
        operation_no=task.operation_no, operation_name=task.operation_name_snapshot, status_code=task.status_code,
        status_label=STATUS_LABELS.get(task.status_code, task.status_code), version_no=task.version_no, unit_name=order.unit_code,
        planned_quantity=float(task.planned_quantity), good_quantity=float(task.good_quantity), scrap_quantity=float(task.scrap_quantity), rework_quantity=float(task.rework_quantity))


def inspection_item(row):
    return dict(id=str(row.id), operation_id=str(row.operation_id), execution_id=str(row.execution_id), result_code=row.result_code,
        production_phase_id=str(row.production_phase_id) if row.production_phase_id else None,inspection_type_code=row.inspection_type_code,
        to_status_code=row.to_status_code, operation_version_snapshot=row.operation_version_snapshot,
        good_quantity=float(row.reported_good_quantity_snapshot), scrap_quantity=float(row.reported_scrap_quantity_snapshot),
        rework_quantity=float(row.reported_rework_quantity_snapshot), unit_name=row.unit_code_snapshot,
        note=row.note, created_at=row.created_at, created_by=str(row.created_by) if row.created_by else None)


class QualityService:
    async def tasks(self, query, user):
        require(user, "mes:quality:list")
        async with get_session_context() as session:
            rows, total = await repo.tasks(session, query, user)
            return dict(items=[task_item(task, order) for task, order in rows], total=total, page=query.page, page_size=query.page_size)

    async def detail(self, identifier, user):
        require(user, "mes:quality:list")
        async with get_session_context() as session:
            pair = await repository.get_task(session, identifier, user, permission="mes:quality:list")
            from .schedule_execution import context
            scheduled=await context(session,*pair) if pair else None
            if pair is None or (not pair[0].is_quality_required and not scheduled):
                raise AppException("检验任务不存在或无权查看", 404)
            from .schedule_execution_repository import repository as phase_repo
            options=await phase_repo.rework_options(session,pair[0],user) if scheduled and "mes:quality:inspect" in user.permissions else []
            return dict(**task_item(*pair),schedule_context=scheduled,rework_options=[dict(value=str(i),label=n) for i,n in options], inspections=[inspection_item(row) for row in await repo.history(session, identifier)])

    async def inspect(self, identifier, body, user):
        require(user, "mes:quality:inspect")
        async with get_session_context() as session:
            # 与报工、入库和出货共用先工单、后工序的锁；检验权限不要求本人派工。
            pair = await repository.get_task(session, identifier, user, permission="mes:quality:inspect", for_update=True)
            if pair is None:
                raise AppException("检验任务不存在或无权处置", 404)
            task, order = pair
            existing = await repo.by_key(session, user.user_id, body.idempotency_key)
            if existing:
                if (existing.operation_id, existing.operation_version_snapshot, existing.result_code, existing.note) != (identifier, body.version_no, body.result_code, body.note):
                    raise AppException("该提交标识已用于不同检验内容，请刷新后重试", 409)
                return dict(task=task_item(task, order), inspection=inspection_item(existing))
            service._check_version(task, body.version_no)
            service._ensure_order_executable(order)
            await service._ensure_no_pending_change(session, order.id)
            if task.status_code != "waiting_quality":
                raise AppException("仅待检验工序可提交检验；退回返工后须重新开工、结束执行再复检", 409)
            if await repository.current_execution(session, task.id, for_update=True):
                raise AppException("当前仍有未结束的执行，不能检验放行", 409)
            from . import schedule_execution
            scheduled=await schedule_execution.inspection_context(session,task,order,body,user)
            if scheduled:
                row=MesQualityInspection(org_id=task.org_id,operation_id=task.id,execution_id=scheduled["execution"].id,
                    production_phase_id=scheduled["phase"].id,inspection_type_code=scheduled["inspection_type"],
                    inspection_person_id=scheduled["person_id"],equipment_id=scheduled["equipment_id"],
                    operation_version_snapshot=body.version_no,result_code=body.result_code,to_status_code="pending",
                    reported_good_quantity_snapshot=scheduled["good"],reported_scrap_quantity_snapshot=scheduled["scrap"],
                    reported_rework_quantity_snapshot=scheduled["rework"],unit_code_snapshot=order.unit_code,
                    note=body.note,idempotency_key=body.idempotency_key,created_by=user.user_id)
                repo.add(session,row);await session.flush()
                await schedule_execution.apply_inspection(session,task,order,body,user,scheduled,row)
                service._touch(task,order,user)
                service._event(session,task,user,"quality_released" if body.result_code=="pass" else "quality_rework_requested",
                    execution_id=scheduled["execution"].id,from_status="waiting_quality",to_status=task.status_code,note=body.note or "实际生产批次检验放行")
                await session.flush();result=dict(task=task_item(task,order),inspection=inspection_item(row));await session.commit();return result
            if not task.is_quality_required:raise AppException("该工序没有待办检验",409)
            execution = await repo.last_execution(session, task.id)
            if execution is None:
                raise AppException("缺少已结束的生产执行，不能提交检验", 409)
            total = task.good_quantity + task.scrap_quantity + task.rework_quantity
            if body.result_code == "pass" and total <= 0:
                raise AppException("尚无报工数量，不能合格放行；请退回工序补齐生产报工", 409)
            if total > task.planned_quantity:
                raise AppException("报工累计超过计划数量，请先核对报工", 409)
            # 不合格只退回原工序复作；保留原报工，不凭检验再增加或重分类产量。
            task.status_code = "completed" if body.result_code == "pass" and total >= task.planned_quantity else "pending"
            row = MesQualityInspection(org_id=task.org_id, operation_id=task.id, execution_id=execution.id,
                operation_version_snapshot=body.version_no, result_code=body.result_code, to_status_code=task.status_code,
                reported_good_quantity_snapshot=task.good_quantity, reported_scrap_quantity_snapshot=task.scrap_quantity,
                reported_rework_quantity_snapshot=task.rework_quantity, unit_code_snapshot=order.unit_code,
                note=body.note, idempotency_key=body.idempotency_key, created_by=user.user_id)
            repo.add(session, row)
            operations = await repository.work_order_operations(session, order.id)
            if operations and all(op.status_code == "completed" for op in operations):
                last = max(operations, key=lambda op: op.sequence_no)
                order.status_code, order.closed_at, order.closed_by = "completed", utc_now(), user.user_id
                for field in ("good_quantity", "scrap_quantity", "rework_quantity"):
                    setattr(order, field, getattr(last, field))
            else:
                order.status_code, order.closed_at, order.closed_by = "in_progress", None, None
                for field in ("good_quantity", "scrap_quantity", "rework_quantity"):
                    setattr(order, field, Decimal(0))
            service._touch(task, order, user)
            service._event(session, task, user, "quality_released" if body.result_code == "pass" else "quality_rework_requested",
                execution_id=execution.id, from_status="waiting_quality", to_status=task.status_code, note=body.note or "工序检验合格放行")
            if order.status_code == "completed":
                repo.add(session, MesWorkOrderEvent(org_id=order.org_id, work_order_id=order.id, event_type_code="completed",
                    to_status_code="completed", version_no=order.version_no, note="检验放行后全部工序完成，自动完结", created_by=user.user_id))
            await session.flush()
            result = dict(task=task_item(task, order), inspection=inspection_item(row))
            await session.commit()
            return result


quality_service = QualityService()
