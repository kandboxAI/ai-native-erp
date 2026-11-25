"""生产管理离线回归：模拟会话、编译 SQL、真实 HTTP 参数校验；不连接数据库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.auth.schemas import AuthenticatedUser
from app.auth.dependencies import get_current_user
from app.core.exceptions import AppException
from app.modules.mes import production_service as module, service as service_module
from app.modules.mes.api import router
from app.modules.mes.models import MesProcessTemplate, MesWorkOrder, MesWorkOrderOperation, MesReworkAssignment
from app.modules.mes.production_repository import production_repository as repo
from app.modules.mes.production_service import production_service, validate_schedule
from app.modules.mes.repository import repository
from app.modules.mes.schemas import ScheduleOperation, ScheduleUpdate, ScheduleQuery, ProcessTemplateBody, ProcessTemplateQuery, WorkOrderDrawingUpdate, WorkOrderCreate
from app.modules.mes.service import service


@pytest.fixture(autouse=True)
def no_pending_report_changes(monkeypatch):
    from app.modules.mes.report_repository import report_repository
    async def empty(*args): return False
    monkeypatch.setattr(report_repository, "pending_for_order", empty)


def actor():
    permissions = ["mes:schedule:list", "mes:schedule:manage", "mes:work_order:list", "mes:work_order:create",
                   "mes:work_order:manage", "mes:production_report:list", "mes:process_template:list", "mes:process_template:manage"]
    return AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test",
        user_id=uuid4(), org_id=uuid4(), permissions=permissions, permission_scopes={key: "organization" for key in permissions})


def period(hour):
    return datetime(2026, 10, 23, hour, tzinfo=UTC)


@pytest.mark.parametrize("start,end", [(period(9), None), (None, period(9)), (period(10), period(9)),
                                      (period(9), period(9)), (period(9).replace(tzinfo=None), period(10))])
def test_schedule_rejects_partial_reversed_and_naive_dates(start, end):
    with pytest.raises(ValidationError):
        ScheduleOperation(operation_id=uuid4(), version_no=1, planned_start_at=start, planned_end_at=end)


def test_schedule_rejects_duplicate_tasks_and_blank_reason():
    row = ScheduleOperation(operation_id=uuid4(), version_no=1)
    with pytest.raises(ValidationError): ScheduleUpdate(operations=[row, row], note="排程")
    with pytest.raises(ValidationError): ScheduleUpdate(operations=[row], note=" ")


def test_schedule_checks_existing_predecessors_and_allows_adjacent_boundaries():
    first = SimpleNamespace(id=uuid4(), sequence_no=1, planned_start_at=period(8), planned_end_at=period(10))
    second = SimpleNamespace(id=uuid4(), sequence_no=2, planned_start_at=None, planned_end_at=None)
    with pytest.raises(AppException, match="前置"):
        validate_schedule([second, first], {second.id: (period(9), period(11))})
    validate_schedule([second, first], {second.id: (period(10), period(11))})
    validate_schedule([second, first], {first.id: (None, None), second.id: (period(9), period(11))})


def fixture(monkeypatch):
    user = actor()
    order = MesWorkOrder(org_id=user.org_id, work_order_no="O1", product_item_id=uuid4(), product_item_no_snapshot="P1",
        product_item_name_snapshot="产品", unit_code="pcs", planned_quantity=10, priority_code="normal", status_code="released")
    tasks = [MesWorkOrderOperation(org_id=user.org_id, work_order_id=order.id, operation_no=str(index * 10),
        operation_name_snapshot="工序", sequence_no=index, planned_quantity=10, status_code="pending", priority_code="normal",
        work_center_name_snapshot="车间", workstation_name_snapshot=f"S{index}") for index in [1, 2]]
    commits, records, locks = [], [], []
    @asynccontextmanager
    async def sessions():
        async def commit(): commits.append(True)
        async def flush(): pass
        yield SimpleNamespace(add=records.append, commit=commit, flush=flush)
    async def parents(session, ids, user): return {task.id: order.id for task in tasks if task.id in ids}
    async def pair(session, task_id, user, **kwargs):
        assert kwargs == {"permission": "mes:schedule:manage", "for_update": True}
        locks.append(task_id)
        return next((task, order) for task in tasks if task.id == task_id)
    async def operations(*args): return tasks
    async def stations(*args): pass
    async def no(*args): return False
    from app.modules.mes import schedule_execution
    # 本夹具无数据库，仅测试旧人工计划编排；正式占用冲突在test_schedule_plans的真实事务中验证。
    monkeypatch.setattr(schedule_execution,"guard_manual_schedule",no)
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repo, "schedule_parents", parents)
    monkeypatch.setattr(repo, "lock_workstations", stations)
    monkeypatch.setattr(repo, "station_conflict", no)
    monkeypatch.setattr(repository, "get_task", pair)
    monkeypatch.setattr(repository, "work_order_operations", operations)
    return user, order, tasks, commits, records, locks, sessions


def update(tasks):
    return ScheduleUpdate(note="安排生产", operations=[ScheduleOperation(operation_id=task.id, version_no=task.version_no,
        planned_start_at=period(8 + index), planned_end_at=period(9 + index)) for index, task in enumerate(tasks)])


def test_batch_schedule_has_one_commit_versions_and_append_audit(monkeypatch):
    user, order, tasks, commits, records, locks, _ = fixture(monkeypatch)
    asyncio.run(production_service.schedule(update(tasks), user))
    assert commits == [True] and all(task.version_no == 2 for task in tasks)
    assert order.version_no == 2 and len(records) == 3
    assert all(row.event_type_code == "scheduled" for row in records)
    assert locks == sorted(locks, key=str)
    assert tasks[0].planned_end_at == tasks[1].planned_start_at


@pytest.mark.parametrize("failure", ["version", "scope", "station", "started", "paused", "batch_station"])
def test_batch_schedule_rejects_conflict_before_mutation_or_commit(monkeypatch, failure):
    user, order, tasks, commits, records, locks, _ = fixture(monkeypatch)
    body = update(tasks)
    if failure == "version": tasks[1].version_no = 2
    if failure == "scope":
        async def missing(*args): return {}
        monkeypatch.setattr(repo, "schedule_parents", missing)
    if failure == "station":
        async def conflict(*args): return True
        monkeypatch.setattr(repo, "station_conflict", conflict)
    if failure == "started": tasks[1].status_code = "in_progress"
    if failure == "paused": order.status_code = "paused"
    if failure == "batch_station":
        # Different orders may use the same station; their periods still cannot overlap.
        tasks[1].workstation_name_snapshot = tasks[0].workstation_name_snapshot
        tasks[1].work_order_id = uuid4()
        body.operations[1].planned_start_at = period(8)
        # Bypass within-order check only, exercising the resource collision guard.
        monkeypatch.setattr(module, "validate_schedule", lambda *args: None)
    with pytest.raises(AppException): asyncio.run(production_service.schedule(body, user))
    assert not commits and not records and all(task.planned_start_at is None for task in tasks)


def test_schedule_clear_is_explicit_and_audited(monkeypatch):
    user, order, tasks, commits, records, _, _ = fixture(monkeypatch)
    tasks[0].planned_start_at, tasks[0].planned_end_at = period(8), period(9)
    asyncio.run(production_service.schedule(ScheduleUpdate(note="取消计划", operations=[ScheduleOperation(operation_id=tasks[0].id, version_no=1)]), user))
    assert tasks[0].planned_start_at is None and tasks[0].planned_end_at is None
    assert commits == [True] and "未安排" in records[0].note


def test_schedule_sql_enforces_scope_soft_delete_and_half_open_resource_overlap():
    statements = []
    class Session:
        async def execute(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(scalar_one=lambda: 0)
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(all=lambda: [])
    user = actor()
    asyncio.run(repo.schedules(Session(), ScheduleQuery(keyword="O1", scheduled=False), user))
    assert all("org_id" in sql and "deleted_at IS NULL" in sql for sql in statements)
    assert "planned_start_at IS NULL" in statements[0]
    task = SimpleNamespace(id=uuid4(), org_id=user.org_id, work_center_name_snapshot="车间", workstation_name_snapshot="S1")
    asyncio.run(repo.station_conflict(Session(), task, period(8), period(9), [task.id]))
    assert "planned_start_at <" in statements[-1] and "planned_end_at >" in statements[-1]


def test_template_rejects_duplicates_and_assignment_facts():
    body = dict(org_id=uuid4(), template_no="T1", template_name="通用", operations=[dict(operation_no="10", operation_name="下料")])
    with pytest.raises(ValidationError): ProcessTemplateBody(**dict(body, operations=body["operations"] * 2))
    with pytest.raises(ValidationError): ProcessTemplateBody(**dict(body, operations=[dict(operation_no="10", operation_name="下料", assigned_user_id=uuid4())]))
    assert ProcessTemplateBody(**body).is_active is True


@pytest.mark.parametrize("failure", ["stale", "org", "product", "inactive", "permission"])
def test_template_application_checks_version_product_org_and_permission(monkeypatch, failure):
    user = actor()
    row = MesProcessTemplate(org_id=user.org_id, template_no="T1", template_name="模板")
    body = WorkOrderCreate(org_id=user.org_id, work_order_no="W1", product_item_id=uuid4(), planned_quantity=1, publish=False,
        process_template_id=row.id, process_template_version_snapshot=1)
    if failure == "stale": row.version_no = 2
    if failure == "org": row.org_id = uuid4()
    if failure == "product": row.product_item_id = uuid4()
    if failure == "inactive": row.is_active = False
    if failure == "permission": user.permissions.remove("mes:work_order:create")
    async def get(*args, **kwargs): return row
    monkeypatch.setattr(repo, "template", get)
    with pytest.raises(AppException): asyncio.run(service._validate_template(object(), body, user, user.org_id))


@pytest.mark.parametrize("action,permission", [("create", "mes:work_order:create"), ("manage", "mes:work_order:manage")])
def test_route_selection_uses_current_work_order_permission_without_route_management(monkeypatch, action, permission):
    user = actor()
    user.permissions = [permission]
    user.permission_scopes = {permission: "organization"}
    row = MesProcessTemplate(org_id=user.org_id, template_no="R1", template_name="路线")
    selected_product = uuid4()
    calls = []
    @asynccontextmanager
    async def sessions(): yield object()
    async def templates(session, query, actor, **kwargs):
        calls.append((query, kwargs))
        return [row], 1
    async def item(session, value): return {"id": str(value.id)}
    async def template(session, identifier, actor, **kwargs):
        assert kwargs["permission"] == permission
        return row
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repo, "templates", templates)
    monkeypatch.setattr(repo, "template", template)
    monkeypatch.setattr(production_service, "template_item", item)
    query = ProcessTemplateQuery(org_id=user.org_id, product_item_id=selected_product, is_active=False)
    result = asyncio.run(production_service.template_options(query, user, action))
    assert result["total"] == 1 and calls[0][0].is_active is True
    assert calls[0][0].product_item_id == selected_product and calls[0][1]["permission"] == permission
    body = WorkOrderCreate(org_id=user.org_id, work_order_no="W1", product_item_id=selected_product, planned_quantity=1,
        publish=False, process_template_id=row.id, process_template_version_snapshot=1)
    asyncio.run(service._validate_template(object(), body, user, user.org_id, permission=permission))
    other_action = "manage" if action == "create" else "create"
    with pytest.raises(AppException): asyncio.run(production_service.template_options(query, user, other_action))
    with pytest.raises(AppException): asyncio.run(production_service.template_options(query.model_copy(update={"org_id": uuid4()}), user, action))


def test_route_selection_query_limits_organization_product_active_and_scope():
    user = actor()
    user.permissions = ["mes:work_order:create"]
    statements = []
    class Session:
        async def execute(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(scalar_one=lambda: 0)
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(all=lambda: [])
    product = uuid4()
    asyncio.run(repo.templates(Session(), ProcessTemplateQuery(org_id=user.org_id, product_item_id=product, is_active=True), user, permission="mes:work_order:create"))
    assert all(str(user.org_id) in sql and str(product) in sql and "product_item_id IS NULL" in sql and "is_active = true" in sql and "deleted_at IS NULL" in sql for sql in statements)


def test_rework_allocation_cannot_exceed_original_report(monkeypatch):
    user = actor()
    source = SimpleNamespace(id=uuid4(), org_id=user.org_id, product_item_id=uuid4(), planned_quantity=Decimal(10), status_code="completed")
    report_id = uuid4()
    async def item(*args): return SimpleNamespace(id=source.product_item_id)
    async def duplicate(*args): return False
    async def original(*args, **kwargs):
        assert kwargs["for_update"] is True
        return source
    async def report(*args): return SimpleNamespace(rework_quantity=Decimal(3)), object(), source
    async def allocated(*args): return Decimal(2)
    monkeypatch.setattr(service_module, "get_active_item", item)
    monkeypatch.setattr(repository, "work_order_no_exists", duplicate)
    monkeypatch.setattr(repository, "get_work_order", original)
    monkeypatch.setattr(repo, "rework_report", report)
    monkeypatch.setattr(repo, "allocated_quantity", allocated)
    body = WorkOrderCreate(org_id=user.org_id, work_order_no="R1", product_item_id=source.product_item_id, planned_quantity=2,
        source_work_order_id=source.id, rework_report_id=report_id, publish=False)
    with pytest.raises(AppException, match="返工数量"):
        asyncio.run(service._create_order(object(), body, user))


def test_rework_assignment_is_created_in_the_same_order_transaction(monkeypatch):
    user = actor()
    source = SimpleNamespace(id=uuid4(), org_id=user.org_id, product_item_id=uuid4(), planned_quantity=Decimal(10), status_code="completed")
    report_id = uuid4(); records = []
    async def item(*args): return SimpleNamespace(id=source.product_item_id, item_no="P1", item_name="产品", unit_code="pcs")
    async def no(*args): return False
    async def original(*args, **kwargs): return source
    async def report(*args): return SimpleNamespace(rework_quantity=Decimal(3)), object(), source
    async def allocated(*args): return Decimal(1)
    async def flush(): pass
    monkeypatch.setattr(service_module, "get_active_item", item)
    monkeypatch.setattr(repository, "work_order_no_exists", no)
    monkeypatch.setattr(repository, "get_work_order", original)
    monkeypatch.setattr(repo, "rework_report", report)
    monkeypatch.setattr(repo, "allocated_quantity", allocated)
    body = WorkOrderCreate(org_id=user.org_id, work_order_no="R1", product_item_id=source.product_item_id, planned_quantity=2,
        source_work_order_id=source.id, rework_report_id=report_id, publish=False)
    repair, _ = asyncio.run(service._create_order(SimpleNamespace(add=records.append, flush=flush), body, user))
    link = next(row for row in records if isinstance(row, MesReworkAssignment))
    assert link.work_order_id == repair.id and link.report_id == report_id
    assert repair.order_type_code == "repair" and source.planned_quantity == 10


def test_rework_listing_queries_fact_and_excludes_reversed_or_deleted_orders():
    sql = str(repo.rework_statement(actor()).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "rework_quantity > 0" in sql and "reversed" in sql
    assert "mes_production_report.org_id" in sql and "mes_work_order.deleted_at IS NULL" in sql


@pytest.mark.parametrize("history,version", [(True, 1), (False, 2)])
def test_drawing_mutation_rejects_execution_or_stale_order_before_binding(monkeypatch, history, version):
    user, order, tasks, commits, records, _, sessions = fixture(monkeypatch)
    async def original(*args, **kwargs): return order
    async def has_history(*args): return history
    async def forbidden(*args, **kwargs): pytest.fail("must not replace files")
    monkeypatch.setattr(repository, "get_work_order", original)
    monkeypatch.setattr(repository, "history_exists", has_history)
    monkeypatch.setattr(module.files, "replace", forbidden)
    from app.modules.mes import drawing_service as drawing_module
    monkeypatch.setattr(drawing_module, "get_session_context", sessions)
    with pytest.raises(AppException): asyncio.run(production_service.save_drawings(order.id, WorkOrderDrawingUpdate(version_no=version,
        attachment_ids=[uuid4()], revision_label="A", change_note="替换图纸"), user))
    assert not commits and not records


def test_drawing_access_requires_scoped_order_read(monkeypatch):
    user = actor()
    async def missing(*args): return None
    monkeypatch.setattr(repository, "get_work_order", missing)
    assert not asyncio.run(production_service.drawing_access(object(), user, uuid4()))
    user.permissions.remove("mes:work_order:list")
    assert not asyncio.run(production_service.drawing_access(object(), user, uuid4()))


def test_http_empty_default_filters_and_validation_are_checked_without_database(monkeypatch):
    app = FastAPI(); app.include_router(router)
    user = actor(); called = []
    for route in router.routes:
        if getattr(route, "path", None) in {"/api/mes/schedules", "/api/mes/reworks"}:
            dependency = route.dependant.dependencies[-1].call
            app.dependency_overrides[dependency] = lambda: user
    async def schedules(query, user):
        called.append(query)
        return dict(items=[], total=0, page=query.page, page_size=query.page_size)
    monkeypatch.setattr(production_service, "schedules", schedules)
    with TestClient(app) as client:
        assert client.get("/api/mes/schedules?page=1&page_size=20").status_code == 200
        assert client.get("/api/mes/schedules?start_date=invalid").status_code == 422
        assert client.get("/api/mes/schedules?page_size=101").status_code == 422
    assert len(called) == 1
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.get("/api/mes/schedules").status_code == 401
    user.permissions = []
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        assert client.get("/api/mes/schedules").status_code == 403
        assert client.get("/api/mes/reworks").status_code == 403
        assert client.get("/api/mes/process-templates").status_code == 403
