"""业务状态及整单下单回归；内存 SQLite / 模拟事务，不访问业务库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, create_engine, select
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.mes import order_service as module
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation, MesProductionOrder
from app.modules.mes.order_service import order_service
from app.modules.mes.order_status import ORDER_STATUS_LABELS, work_order_status, project_order_status
from app.modules.mes.repository import repository
from app.modules.mes.schemas import MesWorkOrderListQuery, ProjectPlaceOrder, WorkOrderCommand
from app.modules.mes.service import service
from test_web_production import actor


@pytest.mark.parametrize("state,count,expected", [
    ("draft", 0, "unconfigured"), ("draft", 2, "ready"),
    ("released", 2, "ordered"), ("in_progress", 2, "ordered"),
    ("paused", 2, "paused"), ("completed", 2, "completed"), ("cancelled", 0, "cancelled"),
])
def test_business_status_distinguishes_configuration_from_ordering(state, count, expected):
    assert work_order_status(state, count) == expected
    order = MesWorkOrder(org_id=uuid4(), work_order_no="W1", product_item_id=uuid4(),
        product_item_no_snapshot="P1", product_item_name_snapshot="支架", unit_code="pcs",
        planned_quantity=1, priority_code="normal", status_code=state)
    item = service._work_order_item(order, count, 0)
    assert item.display_status_key == expected and item.status_label == ORDER_STATUS_LABELS[expected]
    assert "草稿" not in item.status_label


@pytest.mark.parametrize("has_pending_change", [False, True])
def test_work_order_exposes_reason_for_production_pause(has_pending_change):
    order = MesWorkOrder(org_id=uuid4(), work_order_no="W1", product_item_id=uuid4(),
        product_item_no_snapshot="P1", product_item_name_snapshot="支架", unit_code="pcs",
        planned_quantity=1, priority_code="normal", status_code="paused",
        is_process_change_pending=has_pending_change)
    item = service._work_order_item(order, 1, 0).model_dump()
    assert item["status_code"] == "paused"
    assert item["is_process_change_pending"] is has_pending_change


def test_sql_status_filters_and_project_aggregation_match_visible_records():
    user = actor("mes:work_order:list")
    meta = MetaData()
    orders = Table("mes_work_order", meta, Column("id", Uuid, primary_key=True), Column("org_id", Uuid),
        Column("created_by", Uuid), Column("deleted_at", DateTime), Column("status_code", String), Column("production_order_id", Uuid))
    ops = Table("mes_work_order_operation", meta, Column("id", Uuid, primary_key=True), Column("work_order_id", Uuid), Column("deleted_at", DateTime))
    projects = Table("mes_production_order", meta, Column("id", Uuid, primary_key=True))
    engine = create_engine("sqlite:///:memory:")
    meta.create_all(engine)
    project_ids = [uuid4() for _ in range(7)]
    groups = [[("draft", 0)], [("draft", 1)], [("released", 1), ("draft", 0)],
              [("paused", 1)], [("completed", 1), ("cancelled", 0)], [("cancelled", 0)], [("in_progress", 1)]]
    records, operations, configured = [], [], set()
    for project_id, group in zip(project_ids, groups):
        for state, count in group:
            order_id = uuid4()
            records.append(dict(id=order_id, org_id=user.org_id, created_by=user.user_id,
                deleted_at=None, status_code=state, production_order_id=project_id))
            if count:
                configured.add(order_id)
                operations.append(dict(id=uuid4(), work_order_id=order_id, deleted_at=None))
    # Soft-deleted operations must not make a product configured; hidden children must not alter project state.
    from datetime import datetime
    operations.append(dict(id=uuid4(), work_order_id=records[0]["id"], deleted_at=datetime.now()))
    hidden_id = uuid4()
    hidden = dict(id=hidden_id, org_id=uuid4(), created_by=uuid4(), deleted_at=None,
                  status_code="released", production_order_id=project_ids[0])
    with engine.begin() as connection:
        connection.execute(projects.insert(), [dict(id=id_) for id_ in project_ids])
        connection.execute(orders.insert(), [*records, hidden])
        connection.execute(ops.insert(), operations)
        for state in ORDER_STATUS_LABELS:
            ids = set(connection.execute(select(MesWorkOrder.id).where(*repository.work_order_conditions(
                MesWorkOrderListQuery(status_code=state), user))).scalars())
            expected = {row["id"] for row in records if work_order_status(row["status_code"], row["id"] in configured) == state}
            assert ids == expected
        expression = repository.project_status_expression(user)
        projected = dict(connection.execute(select(MesProductionOrder.id, expression)).all())
        for project_id in project_ids:
            children = [SimpleNamespace(**row) for row in records if row["production_order_id"] == project_id]
            assert projected[project_id] == project_order_status(children, configured)
            filtered = set(connection.execute(select(MesProductionOrder.id).where(expression == projected[project_id])).scalars())
            assert project_id in filtered
    engine.dispose()


def placement_fixture(monkeypatch):
    user = actor("mes:work_order:manage")
    project = SimpleNamespace(id=uuid4(), version_no=1)
    orders = [MesWorkOrder(org_id=user.org_id, work_order_no=f"W{i}", product_item_id=uuid4(),
        product_item_no_snapshot=f"P{i}", product_item_name_snapshot="支架", unit_code="pcs", planned_quantity=10,
        priority_code="normal", status_code="draft", production_order_id=project.id) for i in range(2)]
    tasks = {row.id: [MesWorkOrderOperation(org_id=row.org_id, work_order_id=row.id, operation_no="10",
        operation_name_snapshot="CNC", sequence_no=1, planned_quantity=10, status_code="draft", priority_code="normal")] for row in orders}
    commits, rollbacks, events = [], [], []
    @asynccontextmanager
    async def sessions():
        async def commit(): commits.append(True)
        try: yield SimpleNamespace(commit=commit, add=events.append)
        except Exception:
            rollbacks.append(True)
            raise
    async def get_project(*args, **kwargs): return project
    async def pending(*args): return orders
    async def get(session, id_, actor_, **kwargs):
        assert kwargs == {"permission": "mes:work_order:manage", "for_update": True}
        return next(row for row in orders if row.id == id_)
    async def operations(session, id_): return tasks[id_]
    async def item(*args): return SimpleNamespace(id=args[-1])
    async def no_change(*args): pass
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_project", get_project)
    monkeypatch.setattr(repository, "project_orders_for_placement", pending)
    monkeypatch.setattr(repository, "get_work_order", get)
    monkeypatch.setattr(repository, "work_order_operations", operations)
    monkeypatch.setattr(module, "get_active_item", item)
    monkeypatch.setattr(service, "_ensure_no_pending_change", no_change)
    body = ProjectPlaceOrder(version_no=1, orders=[dict(id=row.id, version_no=1) for row in orders])
    return user, project, orders, tasks, body, commits, rollbacks, events


def test_whole_project_ordering_only_changes_states_and_audit(monkeypatch):
    user, project, orders, tasks, body, commits, _, events = placement_fixture(monkeypatch)
    result = asyncio.run(order_service.place_project(project.id, body, user))
    assert result["placed_count"] == 2 and project.version_no == 2
    assert all(row.status_code == "released" and row.good_quantity == 0 and row.planned_quantity == 10 for row in orders)
    assert all(task.status_code == "pending" and task.good_quantity == 0 for group in tasks.values() for task in group)
    assert len(events) == 2 and commits == [True]


@pytest.mark.parametrize("failure", ["unconfigured", "project_version", "child_version", "missing_child", "scope"])
def test_whole_project_ordering_failure_does_not_commit(monkeypatch, failure):
    user, project, orders, tasks, body, commits, rollbacks, _ = placement_fixture(monkeypatch)
    if failure == "unconfigured": tasks[orders[1].id] = []
    elif failure == "project_version": body.version_no = 2
    elif failure == "child_version": body.orders[1].version_no = 2
    elif failure == "missing_child": body.orders.pop()
    else:
        async def blocked(*args): return None
        monkeypatch.setattr(repository, "project_orders_for_placement", blocked)
    with pytest.raises(AppException):
        asyncio.run(order_service.place_project(project.id, body, user))
    assert commits == [] and rollbacks == [True]


def test_individual_place_alias_has_the_same_state_transition(monkeypatch):
    user, _, orders, tasks, _, commits, _, _ = placement_fixture(monkeypatch)
    asyncio.run(order_service.command(orders[0].id, "place", WorkOrderCommand(version_no=1), user))
    assert orders[0].status_code == "released" and tasks[orders[0].id][0].status_code == "pending"
    assert orders[1].status_code == "draft" and commits == [True]


def test_project_placement_checks_scope_and_locks_in_uuid_order():
    statements = []
    class Session:
        async def execute(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return SimpleNamespace(scalar_one=lambda: False)
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    asyncio.run(repository.project_orders_for_placement(Session(), uuid4(), actor("mes:work_order:manage")))
    assert "NOT (" in statements[0] and "org_id" in statements[0]
    assert "org_id" in statements[1] and "deleted_at IS NULL" in statements[1]
    assert "ORDER BY mes_work_order.id FOR UPDATE" in statements[1]


def test_project_placement_rejects_duplicate_ids():
    row = dict(id=uuid4(), version_no=1)
    with pytest.raises(ValidationError): ProjectPlaceOrder(version_no=1, orders=[row, row])


@pytest.mark.parametrize("count", [0, 1])
def test_repair_status_projection_only_loads_authorized_operations(monkeypatch, count):
    from datetime import UTC, datetime
    from app.modules.mes import production_service as production_module
    from app.modules.mes.production_service import production_service
    report = SimpleNamespace(id=uuid4(), report_no="R1", rework_quantity=1, reported_at=datetime.now(UTC))
    order = SimpleNamespace(id=uuid4(), work_order_no="W1", product_item_name_snapshot="支架", unit_code="pcs")
    repair = SimpleNamespace(id=uuid4(), work_order_no="RW1", planned_quantity=1, good_quantity=0, status_code="draft")
    @asynccontextmanager
    async def sessions(): yield object()
    async def reworks(*args):
        return [(report, SimpleNamespace(operation_name_snapshot="CNC"), order)], [(report.id, repair)], {repair.id}, 1
    async def operations(session, ids):
        assert set(ids) == {repair.id}
        return [SimpleNamespace(work_order_id=repair.id)] * count
    monkeypatch.setattr(production_module, "get_session_context", sessions)
    monkeypatch.setattr(production_module.repo, "reworks", reworks)
    monkeypatch.setattr(repository, "operations_for_orders", operations)
    result = asyncio.run(production_service.reworks(SimpleNamespace(page=1, page_size=20), actor()))
    assert result["items"][0]["repairs"][0]["operation_count"] == count


def test_project_placement_http_requires_manage_permission_and_keeps_payload_validation(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.dependencies import get_current_user
    from app.modules.mes.api import router
    app = FastAPI()
    app.include_router(router)
    project_id = uuid4()
    payload = {"version_no": 1, "orders": [{"id": str(uuid4()), "version_no": 1}]}
    called = []
    async def place(id_, body, user):
        called.append(id_)
        return {"id": str(id_), "placed_count": 1, "version_no": 2}
    monkeypatch.setattr(order_service, "place_project", place)
    with TestClient(app) as client:
        assert client.post(f"/api/mes/production-orders/{project_id}/place", json=payload).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: actor("mes:work_order:create")
        assert client.post(f"/api/mes/production-orders/{project_id}/place", json=payload).status_code == 403
        assert not called
        app.dependency_overrides[get_current_user] = lambda: actor("mes:work_order:manage")
        assert client.post(f"/api/mes/production-orders/{project_id}/place", json=payload).status_code == 200
        payload["orders"] *= 2
        assert client.post(f"/api/mes/production-orders/{project_id}/place", json=payload).status_code == 422
        assert called == [project_id]
