"""报工更正审批：通过底座工作流编排，同事务追加事实、回算累计并保留原记录。"""
from decimal import Decimal

from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.file.service import register_file_access, service as files
from app.modules.workflow.integration.registry import WorkflowBusinessAdapter, register_business_adapter, register_business_hooks
from app.modules.workflow.runtime.service import workflow_runtime_service

from .models import MesProductionReport, MesProductionReportChange, MesWorkOrderEvent
from .production_repository import production_repository
from .report_repository import report_repository as repo
from .repository import repository
from .service import BUSINESS_TYPE as REPORT_FILES, SCENE_REPORT, service, _conflict

BUSINESS_TYPE = "mes_report_change"
QUANTITIES = ("good_quantity", "scrap_quantity", "rework_quantity")
MINUTES = ("labor_minutes", "machine_minutes")


def totals_after_change(task, report, change):
    values = {field: getattr(task, field) - getattr(report, field) + getattr(change, field) for field in QUANTITIES}
    if min(values.values()) < 0 or sum(values.values()) > task.planned_quantity:
        raise _conflict("更正后工序累计数量超出允许范围，请核对原报工及当前累计")
    return values


class ReportService:
    async def file_access(self, session, user, report_id):
        if "mes:production_report:list" in user.permissions:
            return await repo.report(session, report_id, user) is not None
        if "mes:production_report:create" in user.permissions:
            row = await repo.report(session, report_id, user, "mes:production_report:create")
            return row is not None and row[0].created_by == user.user_id
        return False

    @staticmethod
    def change_item(row, report_no=None):
        return dict(id=str(row.id), report_id=str(row.report_id), report_no=report_no,
            org_id=str(row.org_id), change_type_code=row.change_type_code, status_code=row.status_code,
            replacement_report_id=str(row.replacement_report_id) if row.replacement_report_id else None,
            wf_instance_id=str(row.wf_instance_id) if row.wf_instance_id else None,
            reason=row.reason, created_by=str(row.created_by), created_at=row.created_at.isoformat(),
            **{field: float(getattr(row, field)) if getattr(row, field) is not None else None for field in (*QUANTITIES, *MINUTES)})

    async def detail(self, report_id, user):
        async with get_session_context() as session:
            pair = await repo.report(session, report_id, user)
            if pair is None: raise AppException("报工不存在或无权查看", 404)
            report, task, order = pair
            attachments = await files.items_for_business(session, REPORT_FILES, [report.id], scene_code=SCENE_REPORT)
            return dict(id=str(report.id), report_no=report.report_no, org_id=str(report.org_id), status_code=report.status_code,
                work_order_id=str(order.id), work_order_no=order.work_order_no, operation_id=str(task.id),
                operation_name=getattr(report, "operation_name_snapshot", None) or task.operation_name_snapshot,
                unit_name=order.unit_code, note=report.note, attachments=attachments.get(report.id, []),
                **{field: float(getattr(report, field)) if getattr(report, field) is not None else None for field in (*QUANTITIES, *MINUTES)})

    async def validate_change(self, session, report, task, order, body):
        if getattr(report, "operation_name_snapshot", None):
            raise _conflict("此报工已纳入工艺变更的数量依据，请先由工程核对变更及处置记录")
        if getattr(order, "is_process_change_repair", False):
            from .process_change_repository import process_change_repository
            if await process_change_repository.repair_has_returned(session, order.id):
                raise _conflict("返工合格件已回到原工单，请先核对关联工艺变更及后续生产")
        from .schedule_execution import before_report_change
        await before_report_change(session,report,task,order)
        from .inventory_service import inventory_service
        if await inventory_service.has_active(session, order.id, output_only=True):
            raise _conflict("工单已有成品入库或仓储出货申请，请先取消对应库存业务，再更正报工")
        from .delivery_repository import delivery_repository
        if await delivery_repository.has_shipments(session, order.id):
            raise _conflict("工单已有有效出货，请先取消相关对账及出货，再更正生产报工")
        if report.status_code != "posted": raise _conflict("只允许更正已入账且未冲销的报工")
        if order.status_code not in {"released", "in_progress", "completed"}:
            raise _conflict("工单未发布、已暂停或已取消，不能更正报工")
        operations = await repository.work_order_operations(session, order.id)
        if any(row.status_code == "cancelled" for row in operations):
            raise _conflict("工单含已取消工序，须先处理完结状态，不能直接更正报工")
        if await repo.downstream_history(session, task):
            raise _conflict("后续工序已有执行或报工记录，不能直接回退前序产量")
        if await production_repository.allocated_quantity(session, report.id):
            raise _conflict("该报工已有返修安排，请先处理关联返修，不能直接冲销来源")
        totals_after_change(task, report, body)

    async def create_change(self, report_id, body, user):
        async with get_session_context() as session:
            pair = await repo.report(session, report_id, user, "mes:production_report:change", lock=True)
            if pair is None: raise AppException("报工不存在或无权变更", 404)
            report, task, order = pair
            existing = await repo.by_idempotency(session, user.user_id, body.idempotency_key)
            if existing is not None:
                if existing.report_id != report_id or any(getattr(existing, field) != getattr(body, field) for field in (*QUANTITIES, *MINUTES, "reason", "change_type_code")):
                    raise _conflict("该幂等键已用于不同报工或不同变更内容")
                return self.change_item(existing, report.report_no)
            await service._ensure_no_pending_change(session, order.id)
            await self.validate_change(session, report, task, order, body)
            row = MesProductionReportChange(org_id=report.org_id, report_id=report.id, change_type_code=body.change_type_code,
                reason=body.reason, idempotency_key=body.idempotency_key, created_by=user.user_id, updated_by=user.user_id,
                **{field: getattr(body, field) for field in (*QUANTITIES, *MINUTES)})
            repository.add(session, row)
            await session.flush()
            await workflow_runtime_service.start(business_type_code=BUSINESS_TYPE, business_id=row.id, org_id=row.org_id,
                variables={}, starter_choices=body.starter_choices, current_user=user, session=session, start_comment=body.reason)
            await session.commit()
            return self.change_item(row, report.report_no)

    async def changes(self, query, user):
        async with get_session_context() as session:
            rows, total = await repo.changes(session, query, user)
            return dict(items=[self.change_item(row, number) for row, number in rows], total=total, page=query.page, page_size=query.page_size)

    async def withdraw(self, change_id, user):
        async with get_session_context() as session:
            row = await repo.change(session, change_id, user)
            if row is None or row.created_by != user.user_id: raise AppException("只能撤回本人提交的变更申请", 403)
            if row.status_code != "submitted": raise _conflict("该申请已结束，不能撤回")
            # Let workflow lock the instance before the hook locks the production parent, matching approval order.
            if not await workflow_runtime_service.cancel_by_business(business_type_code=BUSINESS_TYPE, business_id=row.id, current_user=user, session=session):
                raise _conflict("审批状态已变化，请刷新")
            await session.commit()
            return {"id": str(row.id), "status_code": row.status_code}

    async def hook(self, event, ctx):
        seed = await repo.change(ctx.session, ctx.business_id)
        if seed is None: raise AppException("报工变更申请不存在", 404)
        pair = await repo.report(ctx.session, seed.report_id, lock=True)
        if pair is None: raise AppException("原报工或工单已不可用", 409)
        row = await repo.change(ctx.session, seed.id, lock=True)
        report, task, order = pair
        if ctx.org_id != row.org_id or row.org_id != order.org_id: raise AppException("审批与报工所属组织不一致", 403)
        if event == "started":
            if not ctx.current_user or row.created_by != ctx.current_user.user_id or row.status_code != "draft":
                raise AppException("只能从本人新提交的变更申请发起审批", 403)
            scoped = await repo.report(ctx.session, report.id, ctx.current_user, "mes:production_report:change") if "mes:production_report:change" in ctx.current_user.permissions else None
            if scoped is None: raise AppException("无权发起此报工的更正审批", 403)
            row.wf_instance_id, row.status_code = ctx.instance_id, "submitted"
        else:
            if row.wf_instance_id != ctx.instance_id: raise _conflict("审批实例与变更申请不匹配")
            if row.status_code in {"approved", "rejected", "cancelled"}: return
            if row.status_code != "submitted": raise _conflict("变更申请状态已变化")
            if event in {"completed", "task_completed", "rejected"}:
                scoped = await repo.report(ctx.session, report.id, ctx.current_user, "mes:production_report:approve") if ctx.current_user and "mes:production_report:approve" in ctx.current_user.permissions else None
                if scoped is None: raise AppException("没有此报工的审批权限或超出数据范围", 403)
            if event == "completed":
                await self.validate_change(ctx.session, report, task, order, row)
                await self.apply_change(ctx.session, report, task, order, row, ctx.current_user)
                row.status_code = "approved"
            elif event == "rejected": row.status_code = "rejected"
            elif event == "cancelled":
                if not ctx.current_user or ctx.current_user.user_id != row.created_by: raise AppException("只能撤回本人申请", 403)
                row.status_code = "cancelled"
        row.updated_at, row.updated_by = utc_now(), ctx.current_user.user_id if ctx.current_user else None

    async def apply_change(self, session, report, task, order, change, user):
        values = totals_after_change(task, report, change)
        execution = await repo.execution(session, report.execution_id)
        minute_totals = {field: (getattr(execution, field) or Decimal(0)) - (getattr(report, field) or Decimal(0)) + (getattr(change, field) or Decimal(0)) for field in MINUTES} if execution else {}
        if any(value < 0 for value in minute_totals.values()): raise _conflict("执行累计工时不足以冲销原报工，请核对数据")
        for field, value in values.items(): setattr(task, field, value)
        if execution:
            for field, value in minute_totals.items(): setattr(execution, field, value)
            execution.updated_at, execution.updated_by = utc_now(), user.user_id
        report.status_code = "reversed"
        if change.change_type_code == "replace":
            replacement = MesProductionReport(org_id=report.org_id, report_no=f"MES-RP-{uuid7().hex[:20].upper()}", operation_id=report.operation_id,
                execution_id=report.execution_id, exception_type_code=report.exception_type_code, note=change.reason,
                idempotency_key=f"change:{change.id}", source_code="web", status_code="posted", reported_at=report.reported_at,
                created_by=change.created_by, **{field: getattr(change, field) for field in (*QUANTITIES, *MINUTES)})
            repository.add(session, replacement)
            await session.flush()
            change.replacement_report_id = replacement.id
        current = await repository.current_execution(session, task.id)
        if current:
            task.status_code = "paused" if current.status_code == "paused" else "in_progress"
        elif sum(values.values()) < task.planned_quantity:
            task.status_code = "pending"
        else:
            task.status_code = "waiting_quality" if task.is_quality_required else "completed"
        operations = await repository.work_order_operations(session, order.id)
        complete = bool(operations) and all(op.status_code == "completed" for op in operations)
        order.status_code = "completed" if complete else "in_progress"
        order.closed_at, order.closed_by = (utc_now(), user.user_id) if complete else (None, None)
        last = max(operations, key=lambda op: op.sequence_no) if operations else None
        for field in QUANTITIES: setattr(order, field, getattr(last, field) if complete and last else Decimal(0))
        from .schedule_execution import after_report_change
        await after_report_change(session,report,task,order,user)
        service._touch(task, order, user)
        service._event(session, task, user, "report_corrected", execution_id=report.execution_id, note=f"审批通过：{change.reason}；原报工 {report.report_no}", to_status=task.status_code)
        repository.add(session, MesWorkOrderEvent(org_id=order.org_id, work_order_id=order.id, event_type_code="report_corrected",
            to_status_code=order.status_code, version_no=order.version_no, note=f"报工更正申请 {change.id} 审批通过", created_by=user.user_id))


report_service = ReportService()


def hook(event):
    async def handler(ctx): await report_service.hook(event, ctx)
    return handler


async def business_detail(session, business_id):
    row = await repo.change(session, business_id)
    pair = await repo.report(session, row.report_id) if row else None
    if not pair: return {"fields": [{"label": "提示", "value": "变更申请不存在"}], "tables": []}
    report, task, order = pair
    name = getattr(report, "operation_name_snapshot", None) or task.operation_name_snapshot
    return {"fields": [{"label": "报工单", "value": report.report_no}, {"label": "工单 / 工序", "value": f"{order.work_order_no} / {name}"},
        {"label": "类型", "value": "冲销" if row.change_type_code == "reverse" else "更正"}, {"label": "理由", "value": row.reason}],
        "tables": [{"title": "变更前后（数量沿用工单单位，工时单位为分钟）", "columns": [{"prop": "field", "label": "项目"}, {"prop": "before", "label": "原值"}, {"prop": "after", "label": "申请值"}],
                    "rows": [{"field": label, "before": str(getattr(report, field) or 0), "after": str(getattr(row, field) or 0)} for field, label in [("good_quantity", "合格"), ("scrap_quantity", "报废"), ("rework_quantity", "返工"), ("labor_minutes", "人工工时"), ("machine_minutes", "机器工时")]]}]}


register_business_hooks(BUSINESS_TYPE, {event: hook(event) for event in ("started", "task_completed", "completed", "rejected", "cancelled")})
register_business_adapter(WorkflowBusinessAdapter(business_type_code=BUSINESS_TYPE, label="MES 报工变更", start_permission="mes:production_report:change",
    record_model=MesProductionReportChange, detail=business_detail))
register_file_access(REPORT_FILES, report_service.file_access)
