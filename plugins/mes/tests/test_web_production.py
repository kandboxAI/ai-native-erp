"""Web production regressions; mocked sessions / compiled SQL, no database connection."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.mes import service as service_module
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation
from app.modules.mes.repository import repository
from app.modules.mes.schemas import MesOptionQuery, MesWorkOrderListQuery, WorkOrderCreate
from app.modules.mes.service import service


def actor(permission="mes:work_order:create", scope="organization"):
    return AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test",
        tenant_schema="t_test", user_id=uuid4(), org_id=uuid4(), permissions=[permission],
        permission_scopes={permission: scope})


def payload(**overrides):
    return dict(work_order_no=" MO-001 ", product_item_id=uuid4(), planned_quantity=10,
        operations=[dict(operation_no="10", operation_name="下料"), dict(operation_no="20", operation_name="装配")],
        **overrides)


@pytest.mark.parametrize("operations", [
    [dict(operation_no="10", operation_name="下料"), dict(operation_no=" 10 ", operation_name="装配")],
    [dict(operation_no="10", operation_name=" ")],
    [dict(operation_no="10", operation_name="下料", planned_quantity=0)],
])
def test_invalid_operations_rejected_before_writing(operations):
    body = payload()
    body["operations"] = operations
    with pytest.raises(ValidationError):
        WorkOrderCreate(**body)


def test_creation_uses_shared_item_and_keeps_all_operations(monkeypatch):
    user = actor()
    added, commits = [], []
    @asynccontextmanager
    async def sessions():
        async def flush(): pass
        async def commit(): commits.append(True)
        yield SimpleNamespace(flush=flush, commit=commit)
    async def item(*args):
        # Tenant-wide MdItem deliberately has no org_id.
        return SimpleNamespace(id=uuid4(), item_no="P1", item_name="产品", unit_code="pcs")
    async def exists(*args): return False
    async def detail(session, task, order, user): return task
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(service_module, "get_active_item", item)
    monkeypatch.setattr(repository, "work_order_no_exists", exists)
    monkeypatch.setattr(repository, "add", lambda session, row: added.append(row))
    monkeypatch.setattr(service, "_detail", detail)
    body = WorkOrderCreate(**payload())
    asyncio.run(service.create_work_order(body, user))
    order = next(row for row in added if isinstance(row, MesWorkOrder))
    tasks = [row for row in added if isinstance(row, MesWorkOrderOperation)]
    assert order.org_id == user.org_id and order.work_order_no == "MO-001"
    assert [(task.sequence_no, task.operation_no) for task in tasks] == [(1, "10"), (2, "20")]
    assert all(task.planned_quantity == Decimal("10") for task in tasks)
    assert commits == [True]


def test_foreign_org_rejected_before_item_or_assignee_lookup(monkeypatch):
    @asynccontextmanager
    async def sessions(): yield object()
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    with pytest.raises(AppException, match="无权访问"):
        asyncio.run(service.create_work_order(WorkOrderCreate(**payload(org_id=uuid4())), actor()))


def test_assignee_options_require_scoped_task(monkeypatch):
    @asynccontextmanager
    async def sessions(): yield object()
    async def missing(*args, **kwargs): return None
    async def forbidden(*args, **kwargs): pytest.fail("must not query people for an unreadable task")
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_task", missing)
    monkeypatch.setattr(service_module, "list_assignee_options", forbidden)
    with pytest.raises(AppException, match="无权派工"):
        asyncio.run(service.dispatch_options(uuid4(), MesOptionQuery(), actor("mes:operation_task:manage")))


def test_work_order_filter_sql_is_scoped_and_excludes_closed_overdue():
    statements = []
    class Session:
        async def execute(self, statement):
            return SimpleNamespace(scalar_one=lambda: 0)
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    user = actor("mes:work_order:list")
    asyncio.run(repository.list_work_orders(Session(), MesWorkOrderListQuery(keyword="P1", priority_code="urgent", overdue_only=True), user))
    sql = statements[0]
    assert str(user.org_id) in sql and "deleted_at IS NULL" in sql
    assert "priority_code = 'urgent'" in sql and "due_at <" in sql
    assert "NOT IN ('completed', 'cancelled')" in sql and "ILIKE" in sql


@pytest.mark.parametrize("status,finished", [("completed", True), ("pending", False), ("waiting_quality", False)])
def test_actual_completion_is_not_a_partial_execution_end(monkeypatch, status, finished):
    now = datetime.now(UTC)
    user = actor()
    task = MesWorkOrderOperation(org_id=user.org_id, work_order_id=uuid4(), sequence_no=1, operation_no="10",
        operation_name_snapshot="下料", planned_quantity=10, status_code=status, priority_code="normal")
    order = SimpleNamespace(id=task.work_order_id, work_order_no="MO1", product_item_no_snapshot="P1",
        product_item_name_snapshot="产品", unit_code="pcs", due_at=None, status_code="in_progress")
    async def names(*args): return {}
    async def summaries(*args): return {task.id: SimpleNamespace(started_at=now, finished_at=now)}
    monkeypatch.setattr(service_module, "user_display_names", names)
    monkeypatch.setattr(repository, "execution_summaries", summaries)
    item = asyncio.run(service._task_items(object(), [(task, order)]))[0]
    assert item.actual_started_at == now
    assert (item.actual_finished_at is not None) == finished


def test_assignee_query_has_minimal_fields_and_org_membership():
    from app.modules.user_profile.repository import repository as users
    statements = []
    class Session:
        async def execute(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    org_id = uuid4()
    asyncio.run(users.assignee_options(Session(), org_id, "操作员", 50))
    sql = statements[0]
    assert str(org_id) in sql and "sys_user_org" in sql and "is_active IS true" in sql
    assert "email" not in sql and "mobile" not in sql and "auth_user" not in sql
