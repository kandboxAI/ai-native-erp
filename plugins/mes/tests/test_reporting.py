"""报工与工作流回归；模拟事务和审批上下文，不访问真实业务库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.mes import report_service as module, service as service_module
from app.modules.mes.models import MesProductionReport, MesProductionReportChange, MesWorkOrder, MesWorkOrderOperation, MesOperationExecution
from app.modules.mes.report_repository import report_repository as repo
from app.modules.mes.report_service import report_service, totals_after_change, BUSINESS_TYPE
from app.modules.mes.repository import repository
from app.modules.mes.production_repository import production_repository
from app.modules.mes.schemas import ReportChangeBody, ProductionReportBody
from app.modules.mes.service import service
from app.modules.mes.workflow_defaults import report_change_design
from app.modules.workflow.integration.registry import WorkflowHookContext
from test_production_management import actor


def user():
    value = actor()
    for key in ["mes:production_report:create", "mes:production_report:change", "mes:production_report:approve", "mes:production_report:change:list"]:
        value.permissions.append(key); value.permission_scopes[key] = "organization"
    return value


def fixture(monkeypatch, change_type="replace"):
    current_user = user()
    order = MesWorkOrder(org_id=current_user.org_id, work_order_no="O1", product_item_id=uuid4(), product_item_no_snapshot="P1",
        product_item_name_snapshot="产品", unit_code="pcs", planned_quantity=10, good_quantity=10, priority_code="normal", status_code="completed")
    task = MesWorkOrderOperation(org_id=order.org_id, work_order_id=order.id, sequence_no=1, operation_no="10", operation_name_snapshot="下料",
        planned_quantity=10, good_quantity=10, scrap_quantity=0, rework_quantity=0, status_code="completed", priority_code="normal")
    execution = MesOperationExecution(org_id=order.org_id, operation_id=task.id, worker_user_id=current_user.user_id,
        status_code="completed", tracked_in_at=datetime(2026, 10, 24, tzinfo=UTC), labor_minutes=20, machine_minutes=10)
    report = MesProductionReport(org_id=order.org_id, operation_id=task.id, execution_id=execution.id, report_no="RP1", good_quantity=4,
        scrap_quantity=0, rework_quantity=0, labor_minutes=8, machine_minutes=4, idempotency_key="original-report", source_code="web",
        status_code="posted", reported_at=datetime(2026, 10, 24, tzinfo=UTC), created_by=current_user.user_id)
    change = MesProductionReportChange(org_id=order.org_id, report_id=report.id, change_type_code=change_type, reason="纠正录入",
        idempotency_key="change-key-1", good_quantity=2 if change_type == "replace" else 0, scrap_quantity=0, rework_quantity=0,
        labor_minutes=3 if change_type == "replace" else None, machine_minutes=1 if change_type == "replace" else None,
        status_code="submitted", wf_instance_id=uuid4(), created_by=current_user.user_id)
    records, commits = [], []
    async def flush(): pass
    async def commit(): commits.append(True)
    session = SimpleNamespace(add=records.append, flush=flush, commit=commit)
    @asynccontextmanager
    async def sessions(): yield session
    async def scoped(*args, **kwargs): return report, task, order
    async def request(*args, **kwargs): return change
    async def operations(*args): return [task]
    async def exec_row(*args): return execution
    async def no(*args, **kwargs): return False
    async def zero(*args): return Decimal(0)
    async def none(*args): return None
    from app.modules.mes import schedule_execution
    # 本组为旧整批报工的审批编排替身；正式首件/批次报工使用test_schedule_execution真实内存事务。
    monkeypatch.setattr(schedule_execution,"before_report_change",none)
    monkeypatch.setattr(schedule_execution,"after_report_change",none)
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repo, "report", scoped)
    monkeypatch.setattr(repo, "change", request)
    monkeypatch.setattr(repo, "execution", exec_row)
    monkeypatch.setattr(repo, "pending_for_order", no)
    from app.modules.mes.inventory_service import inventory_service
    monkeypatch.setattr(inventory_service, "has_active", no)
    monkeypatch.setattr(inventory_service, "receipt_reserved", zero)
    from app.modules.mes.delivery_repository import delivery_repository
    monkeypatch.setattr(delivery_repository, "has_shipments", no)
    monkeypatch.setattr(repo, "by_idempotency", none)
    monkeypatch.setattr(repo, "downstream_history", no)
    monkeypatch.setattr(production_repository, "allocated_quantity", zero)
    monkeypatch.setattr(repository, "work_order_operations", operations)
    monkeypatch.setattr(repository, "current_execution", none)
    return current_user, order, task, report, change, execution, session, records, commits


@pytest.mark.parametrize("kind", ["replace", "reverse"])
def test_approval_appends_fact_and_recalculates_quantity_time_and_closed_state(monkeypatch, kind):
    actor, order, task, report, change, execution, session, records, _ = fixture(monkeypatch, kind)
    ctx = WorkflowHookContext(session=session, instance_id=change.wf_instance_id, business_type_code=BUSINESS_TYPE,
        business_id=change.id, org_id=order.org_id, status_code="completed", current_user=actor)
    asyncio.run(report_service.hook("completed", ctx))
    assert change.status_code == "approved" and report.status_code == "reversed"
    assert report.good_quantity == 4 and report.labor_minutes == 8
    assert task.good_quantity == (8 if kind == "replace" else 6)
    assert execution.labor_minutes == (15 if kind == "replace" else 12)
    assert execution.machine_minutes == (7 if kind == "replace" else 6)
    assert task.status_code == "pending" and order.status_code == "in_progress"
    assert order.closed_at is None and order.good_quantity == 0
    replacements = [row for row in records if isinstance(row, MesProductionReport)]
    assert len(replacements) == (1 if kind == "replace" else 0)
    if replacements: assert replacements[0].id == change.replacement_report_id and replacements[0].source_code == "web"
    before = len(records)
    asyncio.run(report_service.hook("completed", ctx))
    assert len(records) == before and task.good_quantity == (8 if kind == "replace" else 6)


@pytest.mark.parametrize("event", ["rejected", "cancelled"])
def test_rejection_or_withdrawal_keeps_original_facts(monkeypatch, event):
    actor, order, task, report, change, execution, session, records, _ = fixture(monkeypatch)
    ctx = WorkflowHookContext(session=session, instance_id=change.wf_instance_id, business_type_code=BUSINESS_TYPE,
        business_id=change.id, org_id=order.org_id, status_code=event, current_user=actor)
    asyncio.run(report_service.hook(event, ctx))
    assert change.status_code == event and report.status_code == "posted"
    assert task.good_quantity == 10 and execution.labor_minutes == 20 and not records


@pytest.mark.parametrize("failure", ["permission", "scope", "instance", "org"])
def test_workflow_cannot_bypass_business_approval_checks(monkeypatch, failure):
    actor, order, task, report, change, execution, session, records, _ = fixture(monkeypatch)
    instance, org_id = change.wf_instance_id, order.org_id
    if failure == "permission": actor.permissions.remove("mes:production_report:approve")
    if failure == "scope":
        async def scoped(session, report_id, user=None, *args, **kwargs): return None if user else (report, task, order)
        monkeypatch.setattr(repo, "report", scoped)
    if failure == "instance": instance = uuid4()
    if failure == "org": org_id = uuid4()
    ctx = WorkflowHookContext(session=session, instance_id=instance, business_type_code=BUSINESS_TYPE, business_id=change.id,
        org_id=org_id, status_code="completed", current_user=actor)
    with pytest.raises(AppException): asyncio.run(report_service.hook("completed", ctx))
    assert report.status_code == "posted" and not records


@pytest.mark.parametrize("failure", ["downstream", "repair", "overrun", "reversed", "paused"])
def test_invalid_changes_fail_before_workflow_or_fact_mutation(monkeypatch, failure):
    actor, order, task, report, change, execution, session, records, _ = fixture(monkeypatch)
    if failure == "downstream":
        async def yes(*args): return True
        monkeypatch.setattr(repo, "downstream_history", yes)
    if failure == "repair":
        async def allocated(*args): return Decimal(1)
        monkeypatch.setattr(production_repository, "allocated_quantity", allocated)
    if failure == "overrun": change.good_quantity = 20
    if failure == "reversed": report.status_code = "reversed"
    if failure == "paused": order.status_code = "paused"
    with pytest.raises(AppException): asyncio.run(report_service.validate_change(session, report, task, order, change))
    assert not records and task.good_quantity == 10


def test_failed_workflow_start_never_commits_change(monkeypatch):
    actor, order, task, report, change, execution, session, records, commits = fixture(monkeypatch)
    async def missing(**kwargs):
        assert kwargs["session"] is session
        raise AppException("未配置已启用的审批流程")
    monkeypatch.setattr(module.workflow_runtime_service, "start", missing)
    body = ReportChangeBody(change_type_code="replace", good_quantity=2, reason="录入有误", idempotency_key="new-change-key")
    with pytest.raises(AppException, match="流程"): asyncio.run(report_service.create_change(report.id, body, actor))
    assert not commits and report.status_code == "posted" and task.good_quantity == 10


def test_pending_change_freezes_production(monkeypatch):
    async def yes(*args): return True
    monkeypatch.setattr(repo, "pending_for_order", yes)
    with pytest.raises(AppException, match="审批"):
        asyncio.run(service._ensure_no_pending_change(object(), uuid4()))


def test_report_sql_uses_report_owner_scope_and_preserves_tenant_boundary():
    actor = user(); actor.permission_scopes["mes:production_report:list"] = "self"
    sql = str(repo.report_query(uuid4(), actor).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "mes_production_report.created_by" in sql and "deleted_at IS NULL" in sql
    assert "t_test." not in sql and "tenant_id" not in sql


def test_report_change_schema_and_workflow_template_contract():
    with pytest.raises(ValidationError): ReportChangeBody(change_type_code="reverse", good_quantity=1, reason="更正", idempotency_key="test-key-1")
    with pytest.raises(ValidationError): ReportChangeBody(change_type_code="replace", good_quantity=1, reason=" ", idempotency_key="test-key-1")
    with pytest.raises(ValidationError): ProductionReportBody(version_no=1, good_quantity="0.0001", idempotency_key="test-key-1")
    design = report_change_design()
    assert design.nodes[0].assignee.value == "mes:production_report:approve"


def test_web_report_sets_source_on_server_and_retries_do_not_count_twice(monkeypatch):
    actor, order, task, report, change, execution, session, records, commits = fixture(monkeypatch)
    order.status_code, task.status_code, execution.status_code = "in_progress", "in_progress", "in_progress"
    task.good_quantity, execution.labor_minutes = Decimal(0), Decimal(0)
    body = ProductionReportBody(version_no=1, good_quantity=2, labor_minutes=3, idempotency_key="web-report-1")
    async def pair(*args, **kwargs): return task, order
    async def current(*args, **kwargs): return execution
    async def detail(*args): return task
    async def existing(*args): return next((row for row in records if isinstance(row, MesProductionReport)), None)
    @asynccontextmanager
    async def sessions(): yield session
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_task", pair)
    monkeypatch.setattr(repository, "current_execution", current)
    monkeypatch.setattr(repository, "find_report_by_idempotency", existing)
    monkeypatch.setattr(service, "_detail", detail)
    asyncio.run(service.report(task.id, body, actor, source_code="web"))
    asyncio.run(service.report(task.id, body, actor, source_code="web"))
    row = next(row for row in records if isinstance(row, MesProductionReport))
    assert row.source_code == "web" and task.good_quantity == 2 and execution.labor_minutes == 3
    assert len(commits) == 1
    body.good_quantity = Decimal(3)
    with pytest.raises(AppException, match="内容不同"): asyncio.run(service.report(task.id, body, actor, source_code="web"))


def test_http_web_source_cannot_be_spoofed_and_permissions_are_required(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.dependencies import get_current_user
    from app.modules.mes.api import router
    current = user(); calls = []
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current
    async def report(task_id, body, actor, *, source_code):
        calls.append(source_code)
        return SimpleNamespace(model_dump=lambda **kwargs: {"id": str(task_id)})
    monkeypatch.setattr(service, "report", report)
    path = f"/api/mes/reporting/tasks/{uuid4()}/reports/submit"
    body = dict(version_no=1, good_quantity=1, idempotency_key="http-report-1", source_code="device")
    with TestClient(app) as client:
        assert client.post(path, json=body).status_code == 200
        assert calls == ["web"]
        assert client.post(path, json=dict(body, good_quantity=-1)).status_code == 422
        current.permissions = []
        assert client.post(path, json=body).status_code == 403
    assert calls == ["web"]
