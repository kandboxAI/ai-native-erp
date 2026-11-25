"""正式计划→首件全路线→实际质检→剩余批量→最终放行；真实内存事务，不写业务库。"""
import asyncio
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.core.exceptions import AppException
from app.modules.mes import schedule_plan_service as plans,service as production,quality_service as quality,schedule_execution as phases
from app.modules.mes.models import MesWorkOrderOperation,MesProductionReport,MesOperationExecution
from app.modules.mes.schedule_models import MesWorkOrderFirstArticle,MesOperationProductionPhase
from app.modules.mes.quality_models import MesQualityInspection
from app.modules.mes.schemas import ProductionActionBody,ProductionReportBody
from app.modules.mes.quality_schemas import QualityInspectionBody
from app.modules.mes.schedule_plan_schemas import SchedulePlanCommand
from app.modules.mes.schedule_trial_planning import snapshot_key
from test_schedule_plans import state as plan_state,START
from test_schedule_trial_repository import store


@pytest.fixture
def state(plan_state,monkeypatch):
    s=plan_state
    s.actor.display_name="测试生产主管"
    for key in ("mes:production_report:create","mes:operation_task:detail","mes:operation_task:manage","mes:quality:list","mes:quality:inspect"):
        s.actor.permissions.append(key);s.actor.permission_scopes[key]="organization"
    async def no_change(*args):pass
    async def detail(session,task,order,user):return NS(id=task.id,version_no=task.version_no,status_code=task.status_code)
    monkeypatch.setattr(production,"get_session_context",plans.get_session_context)
    monkeypatch.setattr(quality,"get_session_context",plans.get_session_context)
    monkeypatch.setattr(production.service,"_ensure_no_pending_change",no_change)
    monkeypatch.setattr(production.service,"_detail",detail)
    clock=[START+timedelta(hours=2)]
    monkeypatch.setattr(production,"utc_now",lambda:clock[0])
    monkeypatch.setattr(quality,"utc_now",lambda:clock[0])
    monkeypatch.setattr(phases,"utc_now",lambda:clock[0])
    for r in s.body.readiness:r.is_confirmed=True
    return NS(**vars(s),clock=clock)


def apply(state):
    # 可能已增加第二道真实工序，重新取得完整资料摘要。
    snap=asyncio.run(plans.sources.snapshot(state.adapter,state.body,state.actor))
    state.body.snapshot_key=snapshot_key(snap)
    result=asyncio.run(plans.service.create(state.body,state.actor))
    return asyncio.run(plans.service.apply(UUID(result["plan_id"]),SchedulePlanCommand(version_no=result["plan_version_no"],note="正式执行测试"),state.actor))


def action(state,task,method,stage=None):
    execution=state.session.scalar(select(MesOperationExecution).where(MesOperationExecution.operation_id==task.id,MesOperationExecution.tracked_out_at.is_(None)))
    body=ProductionActionBody(version_no=task.version_no,execution_id=execution.id if execution else None,segment_type_code=stage)
    result=asyncio.run(getattr(production.service,method)(task.id,body,state.actor))
    state.clock[0]+=timedelta(seconds=30)
    return result


def report(state,task,quantity=1,labor=None):
    body=ProductionReportBody(version_no=task.version_no,good_quantity=quantity,scrap_quantity=0,rework_quantity=0,labor_minutes=labor,idempotency_key=f"test-{uuid4()}")
    return asyncio.run(production.service.report(task.id,body,state.actor))


def finish(state,task):
    action(state,task,"track_in")
    action(state,task,"change_execution_stage","run")
    report(state,task)
    action(state,task,"change_execution_stage","unload")
    action(state,task,"track_out")


def inspect(state,task,result="pass"):
    return asyncio.run(quality.quality_service.inspect(task.id,QualityInspectionBody(version_no=task.version_no,result_code=result,
        note="检验合格" if result=="pass" else "尺寸异常，返工处理",idempotency_key=f"qa-{uuid4()}"),state.actor))


def test_first_article_limits_report_quantity_and_cannot_skip_actual_inspection(state):
    apply(state)
    action(state,state.task,"track_in")
    with pytest.raises(AppException):report(state,state.task,2)
    report(state,state.task,1)
    action(state,state.task,"change_execution_stage","run")
    with pytest.raises(AppException):action(state,state.task,"track_out")
    action(state,state.task,"change_execution_stage","unload")
    action(state,state.task,"track_out")
    assert state.task.status_code=="waiting_quality"
    assert state.session.scalar(select(MesWorkOrderFirstArticle)).status_code=="waiting_quality"
    with pytest.raises(AppException):action(state,state.task,"track_in")
    inspect(state,state.task)
    assert state.session.scalar(select(MesWorkOrderFirstArticle)).status_code=="released"
    finish(state,state.task)
    inspect(state,state.task)
    assert state.work.status_code=="completed" and state.work.good_quantity==2
    assert state.session.scalar(select(func.sum(MesProductionReport.good_quantity)))==2
    assert set(state.session.scalars(select(MesQualityInspection.inspection_type_code)))=={"first_article","final"}


def test_first_article_runs_entire_route_before_remaining_quantity(state):
    second=MesWorkOrderOperation(org_id=state.org,work_order_id=state.work.id,operation_no="20",operation_name_snapshot="第二道",
        sequence_no=2,process_id=state.task.process_id,planned_quantity=2,standard_minutes_per_unit=10,status_code="pending",priority_code="normal",created_by=state.actor.user_id)
    state.session.add(second);state.session.commit()
    rule=state.body.operation_rules[0].model_copy(update={"operation_id":second.id,"version_no":second.version_no})
    state.body.operation_rules.append(rule)
    apply(state)
    finish(state,state.task)
    assert state.task.status_code=="pending"  # 仅首件完成，不是整批完工。
    with pytest.raises(AppException):action(state,state.task,"track_in")
    finish(state,second)
    inspect(state,second)
    finish(state,state.task)
    finish(state,second)
    inspect(state,second)
    assert state.work.good_quantity==2 and state.work.status_code=="completed"
    assert state.session.scalar(select(func.count()).select_from(MesProductionReport))==4


def test_first_article_rework_keeps_original_quantity_and_requires_reinspection(state):
    apply(state);finish(state,state.task);inspect(state,state.task,"fail")
    gate=state.session.scalar(select(MesWorkOrderFirstArticle))
    assert gate.status_code=="rework"
    action(state,state.task,"track_in")
    with pytest.raises(AppException):report(state,state.task,1)
    report(state,state.task,0,labor=2)
    action(state,state.task,"change_execution_stage","run")
    action(state,state.task,"change_execution_stage","unload")
    action(state,state.task,"track_out")
    inspect(state,state.task)
    assert gate.status_code=="released" and state.task.good_quantity==1


def test_first_article_can_report_after_ending_without_output(state):
    apply(state)
    task = state.task
    phase = state.session.scalar(select(MesOperationProductionPhase).where(
        MesOperationProductionPhase.operation_id == task.id,
        MesOperationProductionPhase.production_phase_code == "first",
    ))
    action(state, task, "track_in")
    action(state, task, "change_execution_stage", "run")
    action(state, task, "change_execution_stage", "unload")
    action(state, task, "track_out")
    assert task.status_code == phase.status_code == "pending"
    assert not phase.is_rework

    # 复现旧版本留下的错误标记，且当前执行已到卸料阶段。
    phase.is_rework = True
    state.session.commit()
    action(state, task, "track_in")
    action(state, task, "change_execution_stage", "run")
    action(state, task, "change_execution_stage", "unload")
    context = asyncio.run(phases.context(state.adapter, task, state.work))
    assert not context["is_rework"] and context["remaining_quantity"] == 1
    with pytest.raises(AppException, match="超过当前首件"):
        report(state, task, 2)
    report(state, task, 1)
    assert not phase.is_rework and task.good_quantity == 1
    action(state, task, "track_out")
    assert task.status_code == "waiting_quality"


def test_expected_ready_time_does_not_grant_actual_start(state):
    for r in state.body.readiness:r.is_confirmed=False
    apply(state)
    with pytest.raises(AppException,match="实际确认就绪"):action(state,state.task,"track_in")


def test_remaining_replan_preserves_actual_first_reports_and_quality(state):
    apply(state);finish(state,state.task);inspect(state,state.task)
    first=state.session.scalar(select(MesOperationProductionPhase).where(MesOperationProductionPhase.production_phase_code=="first"))
    original_plan=first.plan_operation_id
    original_release=state.session.scalar(select(MesWorkOrderFirstArticle)).released_at.replace(tzinfo=START.tzinfo)
    snap=asyncio.run(plans.sources.snapshot(state.adapter,state.body,state.actor))
    state.body.snapshot_key=snapshot_key(snap)
    state.body.order_rules[0].version_no=state.work.version_no
    state.body.operation_rules[0].version_no=state.task.version_no
    result=asyncio.run(plans.service.create(state.body,state.actor))
    assert result["status_code"] in {"FEASIBLE","OPTIMAL"}
    assert all(s["batch_key"]=="remaining" for s in result["segments"])
    asyncio.run(plans.service.apply(UUID(result["plan_id"]),SchedulePlanCommand(version_no=result["plan_version_no"],note="仅重排剩余批量"),state.actor))
    assert first.plan_operation_id==original_plan and first.status_code=="completed"
    assert state.session.scalar(select(MesWorkOrderFirstArticle)).released_at==original_release
    finish(state,state.task);inspect(state,state.task)
    assert state.work.good_quantity==2
    assert state.session.scalar(select(func.sum(MesProductionReport.good_quantity)))==2


def test_outsource_actual_return_and_quality_cannot_be_replaced_by_forecast(state):
    from app.modules.mes.archive_models import MesProcess
    from app.modules.mes.schedule_trial_schemas import TrialOperationRule,TrialInspection
    process=state.session.get(MesProcess,state.task.process_id)
    process.execution_kind_code="external";process.processing_type_code="outsourced";process.is_equipment_required=False
    state.session.commit()
    qc=state.body.inspection.process_id
    state.body.operation_rules=[TrialOperationRule(operation_id=state.task.id,version_no=state.task.version_no,kind_key="external",setup_minutes=0,load_minutes=0,unload_minutes=0,
        is_timing_confirmed=True,external_first_return_at=START+timedelta(minutes=90),external_remaining_return_at=START+timedelta(hours=3),
        inspection=dict(process_id=qc,is_equipment_required=False,minutes_per_piece=1))]
    state.body.inspection=TrialInspection(mode_key="last_operation")
    apply(state)
    for _ in range(2):
        action(state,state.task,"track_in")
        with pytest.raises(AppException,match="尚未确认回厂"):report(state,state.task)
        with pytest.raises(AppException,match="尚未确认回厂"):action(state,state.task,"track_out")
        action(state,state.task,"change_execution_stage","external_return")
        report(state,state.task);action(state,state.task,"track_out")
        inspect(state,state.task)
    assert state.work.status_code=="completed" and state.work.good_quantity==2
