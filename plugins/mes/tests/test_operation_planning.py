"""工序配置计划和精确报工筛选的离线验证。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.mes import service as module
from app.modules.mes.models import MesWorkOrderOperation, MesProductionReport
from app.modules.mes.operation_planning import configuration_plan
from app.modules.mes.repository import repository
from app.modules.mes.schemas import WorkOrderCreate, ProductionReportListQuery
from app.modules.mes.service import service
from test_web_production import actor

NOW = datetime(2026, 10, 26, 8, tzinfo=UTC)

def operation(sequence, minutes=None, quantity=10, **extra):
    return MesWorkOrderOperation(org_id=uuid4(), work_order_id=uuid4(), sequence_no=sequence,
        operation_no=str(sequence), operation_name_snapshot="工序", planned_quantity=Decimal(str(quantity)),
        standard_minutes_per_unit=Decimal(str(minutes)) if minutes is not None else None,
        created_at=NOW, **extra)

def test_configuration_start_is_persisted_creation_and_duration_multiplies_each_operation_quantity():
    first, second = operation(1, "1.5", 20), operation(2, 3, 5)
    plan = configuration_plan([second, first])
    assert plan[first.id]["planned_start_at"] == NOW
    assert plan[first.id]["planned_end_at"] == NOW + timedelta(minutes=30)
    assert plan[second.id]["planned_start_at"] == NOW + timedelta(minutes=30)
    assert plan[second.id]["planned_end_at"] == NOW + timedelta(minutes=45)
    first.updated_at = NOW + timedelta(days=2)
    assert configuration_plan([first])[first.id]["planned_start_at"] == NOW
    assert first.planned_start_at is None  # 估算不偷偷占用资源排程。

def test_missing_duration_stops_estimate_chain_and_explicit_schedule_restores_anchor():
    first, second, third = operation(1), operation(2, 2), operation(3, "0.25", 4)
    assert configuration_plan([first, second])[second.id]["planned_start_at"] is None
    second.planned_start_at, second.planned_end_at = NOW + timedelta(hours=1), NOW + timedelta(hours=2)
    plan = configuration_plan([first, second, third])
    assert plan[second.id]["plan_source_key"] == "schedule"
    assert plan[third.id]["planned_start_at"] == second.planned_end_at
    assert plan[third.id]["planned_end_at"] == second.planned_end_at + timedelta(minutes=1)

@pytest.mark.parametrize("minutes", [0, -1, "0.00001", "5256001"])
def test_invalid_per_unit_minutes_rejected(minutes):
    with pytest.raises(ValidationError):
        WorkOrderCreate(work_order_no="MO", product_item_id=uuid4(), planned_quantity=10,
            operations=[dict(operation_no="10", operation_name="CNC", standard_minutes_per_unit=minutes)])

def test_total_duration_cannot_overflow_calendar():
    with pytest.raises(ValidationError, match="预计总时长"):
        WorkOrderCreate(work_order_no="MO", product_item_id=uuid4(), planned_quantity=1000000,
            operations=[dict(operation_no="10", operation_name="CNC", standard_minutes_per_unit=60)])

def test_report_filter_is_exact_and_keeps_report_scope_and_parent_org():
    statements = []
    class Session:
        async def execute(self, statement): return SimpleNamespace(scalar_one=lambda: 0)
        async def exec(self, statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds":True})))
            return SimpleNamespace(all=lambda: [])
    user, operation_id, order_id = actor("mes:production_report:list", "self"), uuid4(), uuid4()
    asyncio.run(repository.list_reports(Session(), ProductionReportListQuery(operation_id=operation_id, work_order_id=order_id), user))
    sql = statements[0]
    assert str(operation_id) in sql and str(order_id) in sql and str(user.user_id) in sql
    assert "mes_production_report.org_id = mes_work_order.org_id" in sql

@pytest.mark.parametrize("reason", ["missing_permission", "unreadable", "wrong_parent"])
def test_operation_report_request_cannot_bypass_parent_access(monkeypatch, reason):
    user = actor("mes:production_report:list")
    if reason != "missing_permission": user.permissions.append("mes:work_order:list")
    @asynccontextmanager
    async def sessions(): yield object()
    async def task(*args, **kwargs):
        return None if reason == "unreadable" else (SimpleNamespace(org_id=user.org_id), SimpleNamespace(id=uuid4(), org_id=user.org_id))
    async def forbidden(*args): pytest.fail("授权失败不能读取报工记录")
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_task", task)
    monkeypatch.setattr(repository, "list_reports", forbidden)
    with pytest.raises(AppException):
        asyncio.run(service.list_reports(ProductionReportListQuery(operation_id=uuid4(), work_order_id=uuid4()), user))


def test_readable_operation_report_returns_scoped_reporter_and_record(monkeypatch):
    user = actor("mes:production_report:list")
    user.permissions.append("mes:work_order:list")
    task = SimpleNamespace(id=uuid4(), org_id=user.org_id, operation_no="10", operation_name_snapshot="CNC")
    order = SimpleNamespace(id=uuid4(), org_id=user.org_id, work_order_no="MO1", product_item_no_snapshot="P1", product_item_name_snapshot="产品")
    report = MesProductionReport(org_id=user.org_id, operation_id=task.id, report_no="RP1", created_by=user.user_id,
        source_code="web", status_code="posted", reported_at=NOW, good_quantity=3, scrap_quantity=0, rework_quantity=0, note="首批完成")
    @asynccontextmanager
    async def sessions(): yield object()
    async def parent(*args, **kwargs): return task, order
    async def page(*args): return [(report, task, order)], 1
    async def names(session, ids):
        assert ids == {user.user_id}
        return {user.user_id: "操作员"}
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_task", parent)
    monkeypatch.setattr(repository, "list_reports", page)
    monkeypatch.setattr(module, "user_display_names", names)
    result = asyncio.run(service.list_reports(ProductionReportListQuery(operation_id=task.id, work_order_id=order.id), user))
    assert result["items"][0]["reporter_name"] == "操作员"
    assert result["items"][0]["note"] == "首批完成"
    assert result["items"][0]["good_quantity"] == 3
