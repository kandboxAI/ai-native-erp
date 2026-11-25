"""工单状态、配置与范围回归；不访问真实库、不执行迁移。"""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.mes import service as service_module
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation
from app.modules.mes.order_service import ensure_action, order_service
from app.modules.mes.repository import repository
from app.modules.mes.schemas import ProductionOrderCreate, ProductionOrderUpdate, MesOptionQuery, WorkOrderCommand, WorkOrderCreate, WorkOrderUpdate
from app.modules.mes.service import service
from test_web_production import actor


@pytest.fixture(autouse=True)
def no_pending_report_changes(monkeypatch):
    from app.modules.mes.inventory_service import inventory_service
    async def no_stock(*args, **kwargs): return False
    monkeypatch.setattr(inventory_service, "has_active", no_stock)
    monkeypatch.setattr(inventory_service, "has_history", no_stock)
    from app.modules.mes.report_repository import report_repository
    async def empty(*args): return False
    monkeypatch.setattr(report_repository, "pending_for_order", empty)



@pytest.mark.parametrize("action,status,options", [
    ("publish", "draft", {"operation_count": 1}), ("withdraw", "released", {}),
    ("pause", "in_progress", {}), ("resume", "paused", {}),
    ("complete", "in_progress", {}), ("cancel", "draft", {}), ("delete", "cancelled", {}),
])

def test_allowed_transitions(action, status, options):
    ensure_action(SimpleNamespace(version_no=4, status_code=status), action, 4, **options)


@pytest.mark.parametrize("action,status,options", [
    ("publish", "draft", {}), ("publish", "completed", {"operation_count": 1}),
    ("withdraw", "released", {"history": True}), ("cancel", "released", {"history": True}),
    ("delete", "draft", {"history": True}), ("complete", "in_progress", {"open_execution": True}),
    ("complete", "in_progress", {"waiting_quality": True}), ("withdraw", "in_progress", {}),
    ("resume", "completed", {}), ("unknown", "draft", {}),
])
def test_unsafe_transitions_rejected(action, status, options):
    with pytest.raises(AppException):
        ensure_action(SimpleNamespace(version_no=4, status_code=status), action, 4, **options)


def test_stale_version_is_always_rejected():
    with pytest.raises(AppException, match="更新"):
        ensure_action(SimpleNamespace(version_no=4, status_code="released"), "pause", 3)


@pytest.mark.parametrize("status", ["draft", "paused", "completed", "cancelled"])
def test_parent_state_guards_production_writes(status):
    with pytest.raises(AppException): service._ensure_order_executable(SimpleNamespace(status_code=status))


def test_draft_may_be_unconfigured_but_release_cannot():
    body = dict(work_order_no="D1", product_item_id=uuid4(), planned_quantity=1, operations=[])
    assert WorkOrderCreate(**body, publish=False).operations == []
    with pytest.raises(ValidationError): WorkOrderCreate(**body, publish=True)
    with pytest.raises(ValidationError): WorkOrderCreate(**dict(body, planned_quantity="0.0001"), publish=False)


def test_project_does_not_accept_duplicate_product_order_numbers():
    product = dict(work_order_no="D1", product_item_id=uuid4(), planned_quantity=1, operations=[], publish=False)
    with pytest.raises(ValidationError, match="不能重复"):
        ProductionOrderCreate(production_order_no="P1", project_name="项目", products=[product, product])


def lifecycle_fixture(monkeypatch, status="released"):
    import app.modules.mes.order_service as module
    user = actor("mes:work_order:manage")
    order = MesWorkOrder(org_id=user.org_id, work_order_no="O1", product_item_id=uuid4(), product_item_no_snapshot="P1",
        product_item_name_snapshot="产品", unit_code="pcs", planned_quantity=10, priority_code="normal", status_code=status)
    task = MesWorkOrderOperation(org_id=user.org_id, work_order_id=order.id, sequence_no=1,
        operation_no="10", operation_name_snapshot="下料", planned_quantity=10, status_code="pending", priority_code="normal")
    commits, records = [], []
    @asynccontextmanager
    async def sessions():
        async def commit(): commits.append(True)
        async def flush(): pass
        yield SimpleNamespace(add=records.append, commit=commit, flush=flush)
    async def get(*args, **kwargs):
        assert kwargs["permission"] == "mes:work_order:manage"
        assert kwargs["for_update"] is True
        return order
    async def ops(*args): return [task]
    async def no(*args): return False
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_work_order", get)
    monkeypatch.setattr(repository, "work_order_operations", ops)
    for name in ["history_exists", "open_executions_exist", "repair_exists"]: monkeypatch.setattr(repository, name, no)
    return user, order, task, commits, records


def test_parent_pause_preserves_independently_paused_task(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch, "in_progress")
    task.status_code = "paused"
    asyncio.run(order_service.command(order.id, "pause", WorkOrderCommand(version_no=1), user))
    assert order.status_code == "paused" and task.status_code == "paused"
    assert order.resume_status_code == "in_progress"
    asyncio.run(order_service.command(order.id, "resume", WorkOrderCommand(version_no=2), user))
    assert order.status_code == "in_progress" and task.status_code == "paused"
    assert len(commits) == 2 and len(records) == 2


def test_withdrawn_order_stops_all_tasks(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch)
    asyncio.run(order_service.command(order.id, "withdraw", WorkOrderCommand(version_no=1), user))
    assert order.status_code == task.status_code == "draft"
    assert order.released_at is None and task.version_no == 2


def test_different_manager_can_configure_then_publish_an_unconfigured_product(monkeypatch):
    import app.modules.mes.order_service as module
    user, order, _, commits, records = lifecycle_fixture(monkeypatch, "draft")
    creator = uuid4()
    order.created_by = creator
    assert "mes:work_order:create" not in user.permissions
    async def operations(*args):
        return [row for row in records if isinstance(row, MesWorkOrderOperation)]
    async def item(*args):
        return SimpleNamespace(id=order.product_item_id, item_no="P1", item_name="产品", unit_code="pcs")
    monkeypatch.setattr(repository, "work_order_operations", operations)
    monkeypatch.setattr(module, "get_active_item", item)
    with pytest.raises(AppException, match="至少配置"):
        asyncio.run(order_service.command(order.id, "publish", WorkOrderCommand(version_no=1), user))
    assert not commits
    body = WorkOrderUpdate(work_order_no=order.work_order_no, product_item_id=order.product_item_id,
        planned_quantity=10, version_no=1, operations=[dict(operation_no="10", operation_name="CNC加工")])
    asyncio.run(order_service.update(order.id, body, user))
    task = next(row for row in records if isinstance(row, MesWorkOrderOperation))
    assert order.status_code == task.status_code == "draft"
    assert order.created_by == creator and task.created_by == user.user_id
    asyncio.run(order_service.command(order.id, "publish", WorkOrderCommand(version_no=order.version_no), user))
    assert order.status_code == "released" and task.status_code == "pending"
    assert len(commits) == 2


def test_manual_completion_uses_final_actual_output_without_faking_missing_output(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch, "in_progress")
    task.good_quantity, task.scrap_quantity = Decimal("6"), Decimal("1")
    asyncio.run(order_service.command(order.id, "complete", WorkOrderCommand(version_no=1, note="客户取消剩余数量"), user))
    assert order.good_quantity == 6 and order.scrap_quantity == 1
    assert order.status_code == "completed" and task.status_code == "cancelled"
    assert order.closed_at and commits == [True]


def test_unreadable_order_cannot_be_changed(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch)
    async def missing(*args, **kwargs): return None
    monkeypatch.setattr(repository, "get_work_order", missing)
    with pytest.raises(AppException, match="无权"):
        asyncio.run(order_service.command(order.id, "pause", WorkOrderCommand(version_no=1), user))
    assert not commits and not records


def test_running_order_rejects_configuration_changes(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch, "in_progress")
    body = WorkOrderUpdate(org_id=order.org_id, work_order_no=order.work_order_no, product_item_id=order.product_item_id,
        planned_quantity=10, version_no=1, operations=[])
    with pytest.raises(AppException, match="工序"):
        asyncio.run(order_service.update(order.id, body, user))
    assert not commits


@pytest.mark.parametrize("change_configuration", [False, True])
def test_scheduled_tasks_are_preserved_or_require_explicit_plan_clearing(monkeypatch, change_configuration):
    from datetime import UTC, datetime
    import app.modules.mes.order_service as module
    user, order, task, commits, records = lifecycle_fixture(monkeypatch)
    task.planned_start_at = datetime(2026, 10, 23, 8, tzinfo=UTC)
    task.planned_end_at = datetime(2026, 10, 23, 9, tzinfo=UTC)
    async def item(*args): return SimpleNamespace(id=order.product_item_id, item_no="P1", item_name="产品", unit_code="pcs")
    monkeypatch.setattr(module, "get_active_item", item)
    body = WorkOrderUpdate(org_id=order.org_id, work_order_no=order.work_order_no, product_item_id=order.product_item_id,
        planned_quantity=10, version_no=1, note="更新说明", operations=[dict(operation_no="10", operation_name="新工序" if change_configuration else "下料")])
    if change_configuration:
        with pytest.raises(AppException, match="先清空"):
            asyncio.run(order_service.update(order.id, body, user))
        assert not commits and not records
    else:
        asyncio.run(order_service.update(order.id, body, user))
        assert task.deleted_at is None and task.planned_start_at.hour == 8
        assert commits == [True] and len(records) == 1
        assert order.note == "更新说明"


def test_task_write_locks_parent_before_task_and_rechecks_permission_scope():
    statements = []
    user = actor("mes:production_report:create")
    class Session:
        async def execute(self, statement): statements.append(str(statement.compile(dialect=postgresql.dialect())))
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return SimpleNamespace(first=lambda: None)
    asyncio.run(repository.get_task(Session(), uuid4(), user, for_update=True))
    assert "FOR UPDATE" in statements[0] and "mes_work_order.id" in statements[0]
    assert "FOR UPDATE OF mes_work_order_operation" in statements[1]
    assert "org_id" in statements[0] and "org_id" in statements[1]


def test_project_creation_has_single_transaction_and_no_commit_on_second_product_failure(monkeypatch):
    user = actor()
    commits, created = [], []
    @asynccontextmanager
    async def sessions():
        async def flush(): pass
        async def commit(): commits.append(True)
        yield SimpleNamespace(add=lambda row: None, flush=flush, commit=commit)
    async def create(session, body, actor, **kwargs):
        created.append(body.work_order_no)
        if len(created) == 2: raise AppException("产品已停用")
        return SimpleNamespace(id=uuid4()), None
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(service, "_create_order", create)
    products = [WorkOrderCreate(work_order_no=no, product_item_id=uuid4(), planned_quantity=1, publish=False) for no in ["D1", "D2"]]
    with pytest.raises(AppException):
        asyncio.run(service.create_production_order(ProductionOrderCreate(production_order_no="P1", project_name="项目", products=products), user))
    assert created == ["D1", "D2"] and not commits


def test_project_metadata_change_checks_version_and_keeps_product_records(monkeypatch):
    user = actor("mes:work_order:manage")
    project = SimpleNamespace(id=uuid4(), org_id=user.org_id, version_no=3)
    commits = []
    @asynccontextmanager
    async def sessions():
        async def commit(): commits.append(True)
        yield SimpleNamespace(commit=commit)
    async def get(*args, **kwargs): return project
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_project", get)
    body = ProductionOrderUpdate(org_id=user.org_id, version_no=2, production_order_no="P1", project_name="新名称", products=[])
    with pytest.raises(AppException, match="更新"):
        asyncio.run(service.update_production_order(project.id, body, user))
    body.version_no = 3
    asyncio.run(service.update_production_order(project.id, body, user))
    assert project.version_no == 4 and project.project_name == "新名称" and commits == [True]


def test_append_product_needs_create_permission(monkeypatch):
    user = actor("mes:work_order:manage")
    project = SimpleNamespace(id=uuid4(), org_id=user.org_id, version_no=1)
    @asynccontextmanager
    async def sessions(): yield object()
    async def get(*args, **kwargs): return project
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_project", get)
    body = ProductionOrderUpdate(org_id=user.org_id, version_no=1, production_order_no="P1", project_name="项目", products=[WorkOrderCreate(work_order_no="D1", product_item_id=uuid4(), planned_quantity=1, publish=False)])
    with pytest.raises(AppException, match="创建生产工单权限"):
        asyncio.run(service.update_production_order(project.id, body, user))


def test_edit_assignee_lookup_uses_manage_scope_when_create_scope_is_narrower(monkeypatch):
    user = actor("mes:work_order:manage")
    user.permissions.append("mes:work_order:create")
    user.permission_scopes["mes:work_order:create"] = "self"
    @asynccontextmanager
    async def sessions(): yield object()
    async def options(session, actor, org_id, permission, *args):
        assert permission == "mes:work_order:manage"
        return []
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(service_module, "list_assignee_options", options)
    asyncio.run(service.creation_options("assignees", MesOptionQuery(), user, user.org_id, for_edit=True))
