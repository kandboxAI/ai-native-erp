"""排程迁移专项：设备调配、批次原子性、资源汇总和访问范围；不访问真实库。"""
import asyncio
from datetime import date, datetime, UTC
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from app.core.exceptions import AppException
from app.modules.mes import production_service as module
from app.modules.mes.archive_models import MesEquipment
from app.modules.mes.archive_repository import archive_repository
from app.modules.mes.production_service import production_service, station_keys
from app.modules.mes.production_repository import production_repository as repo
from app.modules.mes.schemas import ScheduleQuery, ScheduleOperation, ScheduleUpdate
from app.modules.mes.scheduling_repository import resource_queries, daily_load_statement
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation, MesExecutionEvent
from test_production_management import fixture, update, period, actor
from test_quality import store


@pytest.fixture
def grouped_schedule_store():
    from sqlalchemy import create_engine, Column, Uuid, JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from app.modules.mes.models import MesProductionOrder
    user = actor()
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    models = (MesProductionOrder, MesWorkOrder, MesWorkOrderOperation)
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external:
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    with Session(engine) as session:
        orders = []
        for index, org in enumerate((user.org_id, user.org_id, uuid4(), user.org_id)):
            order = MesWorkOrder(org_id=org, work_order_no=f"GROUP-{index}", product_item_id=uuid4(),
                product_item_no_snapshot="P", product_item_name_snapshot="产品", unit_code="piece",
                planned_quantity=3, priority_code="normal", status_code="released")
            if index == 3:
                order.deleted_at = datetime(2026, 11, 10, tzinfo=UTC)
            session.add(order)
            session.flush()
            orders.append(order.id)
            for seq in range(1, 5):
                task = MesWorkOrderOperation(org_id=org, work_order_id=order.id, sequence_no=seq,
                    operation_no=str(seq), operation_name_snapshot=f"工序{seq}", planned_quantity=3,
                    status_code="completed" if seq == 1 else "pending", priority_code="normal")
                session.add(task)
            # 同工单的已删工序及越权工序不能因为读取完整路线而被带出。
            for deleted in (False, True):
                task = MesWorkOrderOperation(org_id=user.org_id if deleted else uuid4(), work_order_id=order.id,
                    sequence_no=8 if deleted else 9, operation_no="deleted" if deleted else "hidden", operation_name_snapshot="隐藏工序",
                    planned_quantity=3, status_code="pending", priority_code="normal")
                if deleted:
                    task.deleted_at = datetime(2026, 11, 10, tzinfo=UTC)
                session.add(task)
        session.commit()

        class Adapter:
            async def execute(self, statement):
                return session.execute(statement)

            async def exec(self, statement):
                return session.execute(statement)

        yield user, Adapter(), orders
    engine.dispose()


def test_grouped_schedule_pages_whole_orders_and_keeps_completed_predecessors(grouped_schedule_store):
    user, session, orders = grouped_schedule_store
    query = ScheduleQuery(group_by_work_order=True, unfinished_only=True, keyword="工序2", page_size=1)
    first, total = asyncio.run(repo.schedules(session, query, user))
    assert total == 2
    assert {order.id for _, order in first} == {orders[0]}
    assert [task.sequence_no for task, _ in first] == [1, 2, 3, 4]
    assert first[0][0].status_code == "completed"
    second, second_total = asyncio.run(repo.schedules(session, query.model_copy(update={"page": 2}), user))
    assert second_total == 2
    assert {order.id for _, order in second} == {orders[1]}
    assert len(second) == 4
    assert not asyncio.run(repo.schedules(session, query.model_copy(update={"page": 3}), user))[0]


def test_operation_pagination_remains_compatible(grouped_schedule_store):
    user, session, _ = grouped_schedule_store
    rows, total = asyncio.run(repo.schedules(session, ScheduleQuery(unfinished_only=True, page_size=1), user))
    assert total == 6
    assert len(rows) == 1
    assert rows[0][0].status_code == "pending"


@pytest.fixture(autouse=True)
def no_approval(monkeypatch):
    monkeypatch.setattr(module.service, "_ensure_no_pending_change", AsyncMock())
    monkeypatch.setattr(repo, "lock_schedule_equipment", AsyncMock())
    # 本组动作编排使用受控档案替身；多工艺真实关系查询另由设备导入测试覆盖。
    async def equipment_process_ids(session, equipment):
        return [equipment.process_id] if equipment.process_id else []
    monkeypatch.setattr(archive_repository, "equipment_process_ids", equipment_process_ids)


def test_assign_equipment_changes_snapshots_and_uses_new_resource_for_conflicts(monkeypatch):
    user, order, tasks, commits, records, _, _ = fixture(monkeypatch)
    process = uuid4(); tasks[0].process_id = process
    equipment = MesEquipment(org_id=user.org_id, equipment_no="CNC-01", equipment_name="加工中心", work_center_name="车间二", process_id=process)
    monkeypatch.setattr(archive_repository, "get", AsyncMock(return_value=equipment))
    seen = []
    async def conflict(session, task, *args):
        seen.append((task.equipment_id, task.workstation_name_snapshot))
        return False
    monkeypatch.setattr(repo, "station_conflict", conflict)
    body = update(tasks)
    body.operations[0].equipment_id = equipment.id
    asyncio.run(production_service.schedule(body, user))
    assert tasks[0].equipment_id == equipment.id and tasks[0].workstation_name_snapshot == "CNC-01"
    assert (equipment.id, "CNC-01") in seen
    assert commits == [True] and any("设备：" in (row.note or "") for row in records)


@pytest.mark.parametrize("failure", ["org", "inactive", "process", "conflict"])
def test_invalid_equipment_or_conflict_never_mutates_batch(monkeypatch, failure):
    user, _, tasks, commits, records, _, _ = fixture(monkeypatch)
    equipment = MesEquipment(org_id=uuid4() if failure == "org" else user.org_id, equipment_no="NEW", equipment_name="设备",
        is_active=failure != "inactive", process_id=uuid4() if failure == "process" else None)
    monkeypatch.setattr(archive_repository, "get", AsyncMock(return_value=equipment))
    if failure == "conflict": monkeypatch.setattr(repo, "station_conflict", AsyncMock(return_value=True))
    body = update(tasks); body.operations[0].equipment_id = equipment.id
    with pytest.raises(AppException): asyncio.run(production_service.schedule(body, user))
    assert tasks[0].equipment_id is None and tasks[0].workstation_name_snapshot == "S1"
    assert not commits and not records


def test_omitted_equipment_preserves_manual_station_and_explicit_null_unassigns(monkeypatch):
    user, _, tasks, _, _, _, _ = fixture(monkeypatch)
    asyncio.run(production_service.schedule(ScheduleUpdate(note="保留工作站", operations=[ScheduleOperation(operation_id=tasks[0].id, version_no=1)]), user))
    assert tasks[0].workstation_name_snapshot == "S1"
    asyncio.run(production_service.schedule(ScheduleUpdate(note="取消设备分配", operations=[ScheduleOperation(operation_id=tasks[0].id, version_no=2, equipment_id=None)]), user))
    assert tasks[0].workstation_name_snapshot is None and tasks[0].equipment_id is None


def test_equipment_identity_prevents_overlap_even_if_work_center_snapshots_differ(monkeypatch):
    user, _, tasks, commits, _, _, _ = fixture(monkeypatch)
    equipment = MesEquipment(org_id=user.org_id, equipment_no="CNC", equipment_name="设备")
    monkeypatch.setattr(archive_repository, "get", AsyncMock(return_value=equipment))
    tasks[0].equipment_id = tasks[1].equipment_id = equipment.id
    tasks[1].work_center_name_snapshot = "旧车间名"
    body = update(tasks)
    body.operations[1].planned_start_at = period(8)
    monkeypatch.setattr(module, "validate_schedule", lambda *_: None)
    assert station_keys(tasks[0]) & station_keys(tasks[1])
    with pytest.raises(AppException, match="同一工作站"): asyncio.run(production_service.schedule(body, user))
    assert not commits


@pytest.mark.parametrize("start,end", [(date(2026, 10, 24), None), (date(2026, 11, 1), date(2026, 10, 1)), (date(2026, 10, 1), date(2026, 11, 1))])
def test_display_range_requires_bounded_valid_dates(start, end):
    with pytest.raises(ValidationError): ScheduleQuery(window_start=start, window_end=end)


def test_resource_and_daily_queries_aggregate_scoped_rows_before_paging():
    user = actor(); query = ScheduleQuery(unfinished_only=True, product_keyword="支架", equipment_keyword="CNC", window_start=date(2026, 10, 23), window_end=date(2026, 10, 30))
    base, resources = resource_queries(query, user)
    sql = str(select(resources).compile(dialect=postgresql.dialect()))
    assert "resource_totals" in sql and "GROUP BY" in sql and "LIMIT" not in sql
    assert "deleted_at IS NULL" in sql and "org_id" in sql and "md_" not in sql
    assert "product_item_name_snapshot ILIKE" in sql and "status_code NOT IN" in sql
    daily = str(daily_load_statement(base, ["resource"], query.window_start, query.window_end).compile(dialect=postgresql.dialect()))
    assert "least(" in daily and "greatest(" in daily and "planned_end_at >" in daily and "planned_start_at <" in daily


def test_unassigned_candidate_query_excludes_started_tasks_and_unavailable_orders():
    from app.modules.mes.scheduling_repository import schedule_statement
    query = ScheduleQuery(unassigned_only=True, unstarted_only=True)
    sql = str(schedule_statement(query, actor()).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "equipment_id IS NULL" in sql
    assert "('draft', 'pending', 'dispatched')" in sql
    assert "('draft', 'released', 'in_progress')" in sql


def test_schedule_only_process_options_do_not_expose_archive_notes(monkeypatch):
    from app.modules.mes import archive_service as archives
    from app.modules.mes.archive_models import MesProcess
    from app.modules.mes.archive_schemas import ArchiveQuery
    user, _, _, _, _, _, sessions = fixture(monkeypatch)
    user.permissions = ["mes:schedule:list"]
    row = MesProcess(org_id=user.org_id, process_no="P1", process_name="工艺", description="不需要显示的自由说明")
    monkeypatch.setattr(archives, "get_session_context", sessions)
    monkeypatch.setattr(archive_repository, "page", AsyncMock(return_value=([row], 1)))
    result = asyncio.run(archives.archive_service.options("processes", ArchiveQuery(org_id=user.org_id), user))
    assert result["items"][0]["record_name"] == "工艺"
    assert "description" not in result["items"][0] and "previous_process_ids" not in result["items"][0]


def test_schedule_metadata_endpoints_do_not_auto_publish_ai_tools():
    from app.integrations.harness_api_policy import http_registry
    registry = http_registry()
    assert registry.resolve("GET", "/api/mes/schedule-resources") is None
    assert registry.resolve("GET", "/api/mes/schedule-options/organizations") is None


@pytest.mark.parametrize("permission,kind", [("mes:schedule:list", "processes"), ("mes:schedule:manage", "equipment")])
def test_schedule_only_user_reaches_archive_option_http_route(monkeypatch, permission, kind):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.dependencies import get_current_user
    from app.modules.mes.archive_api import router
    from app.modules.mes.archive_service import archive_service
    user = actor(); user.permissions = [permission]
    app = FastAPI(); app.include_router(router, prefix="/api/mes")
    app.dependency_overrides[get_current_user] = lambda: user
    options = AsyncMock(return_value=dict(items=[], total=0, page=1, page_size=50))
    monkeypatch.setattr(archive_service, "options", options)
    with TestClient(app) as client:
        response = client.get(f"/api/mes/archive-options/{kind}", params={"org_id": str(user.org_id)})
        assert response.status_code == 200
        options.assert_awaited_once()
        user.permissions = []
        assert client.get(f"/api/mes/archive-options/{kind}").status_code == 403


@pytest.mark.parametrize("fail", [False, True])
def test_real_transaction_persists_or_rolls_back_device_time_and_event(store, monkeypatch, fail):
    equipment_id = uuid4()
    with store.engine.begin() as connection:
        connection.execute(Table("mes_equipment", MetaData(), autoload_with=connection).insert().values(id=equipment_id.hex))
    with Session(store.engine) as session:
        session.get(MesWorkOrderOperation, store.task).status_code = "pending"
        session.commit()
    equipment = MesEquipment(id=equipment_id, org_id=store.user.org_id, equipment_no="E01", equipment_name="设备", work_center_name="机加")
    monkeypatch.setattr(module, "get_session_context", store.sessions)
    monkeypatch.setattr(repo, "lock_workstations", AsyncMock())
    monkeypatch.setattr(archive_repository, "get", AsyncMock(return_value=equipment))
    if fail:
        def event_failure(*args, **kwargs): raise RuntimeError("event failed")
        monkeypatch.setattr(module.service, "_event", event_failure)
    body = ScheduleUpdate(note="安排加工", operations=[ScheduleOperation(operation_id=store.task, version_no=1,
        planned_start_at=datetime(2026, 10, 25, 1, tzinfo=UTC), planned_end_at=datetime(2026, 10, 25, 2, tzinfo=UTC), equipment_id=equipment_id)])
    if fail:
        with pytest.raises(RuntimeError): asyncio.run(production_service.schedule(body, store.user))
    else: asyncio.run(production_service.schedule(body, store.user))
    with Session(store.engine) as session:
        task = session.get(MesWorkOrderOperation, store.task)
        order = session.get(MesWorkOrder, store.order)
        events = session.execute(select(MesExecutionEvent)).scalars().all()
        assert task.equipment_id == (None if fail else equipment_id)
        assert task.planned_start_at is None if fail else task.planned_start_at is not None
        assert task.version_no == order.version_no == (1 if fail else 2)
        assert len(events) == (0 if fail else 1)
