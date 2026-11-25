"""工序检验相关回归：真实 SQLite 事务，权限、返工复检及产出门禁；不访问开发库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.mes import quality_service as module, service as execution_module
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation, MesOperationExecution, MesExecutionEvent, MesWorkOrderEvent
from app.modules.mes.quality_models import MesQualityInspection
from app.modules.mes import schedule_models
from app.modules.mes.workforce_models import MesProductionPerson
from app.modules.masterdata.models import MdPerson,MdParty
from app.modules.mes.quality_schemas import QualityInspectionBody, QualityQuery
from app.modules.mes.quality_service import quality_service
from app.modules.mes.schemas import ProductionActionBody
from app.modules.mes.service import service
from app.modules.mes.inventory_service import inventory_service
from app.modules.mes.inventory_repository import inventory_repository
from test_production_management import actor


@pytest.fixture
def store(monkeypatch):
    user = actor()
    for key in ("mes:quality:list", "mes:quality:inspect", "mes:operation_task:manage", "mes:operation_task:list", "mes:production_report:create"):
        user.permissions.append(key)
        user.permission_scopes[key] = "organization"
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    # 挂接正式排程后，旧人工计划依然查询空的批次关系；夹具保留真实关系表而非模拟业务结果。
    models = (MesWorkOrder, MesWorkOrderOperation, MesOperationExecution, MesExecutionEvent, MesWorkOrderEvent, MesQualityInspection,
        MdParty,MdPerson,MesProductionPerson,*[value for value in vars(schedule_models).values() if isinstance(value,type) and value.__module__==schedule_models.__name__ and hasattr(value,"__table__")])
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external:
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
    metadata.create_all(engine)
    product = uuid4()
    with engine.begin() as connection:
        for name, identifiers in (("sys_org", [user.org_id]), ("sys_user", [user.user_id]), ("md_item", [product])):
            for identifier in identifiers:
                connection.execute(metadata.tables[name].insert().values(id=identifier))
    order = MesWorkOrder(org_id=user.org_id, work_order_no="Q-01", product_item_id=product, product_item_no_snapshot="P1",
        product_item_name_snapshot="支架", unit_code="piece", planned_quantity=10, priority_code="normal", status_code="in_progress")
    task = MesWorkOrderOperation(org_id=user.org_id, work_order_id=order.id, sequence_no=1, operation_no="10", operation_name_snapshot="终检",
        planned_quantity=10, good_quantity=10, status_code="waiting_quality", priority_code="normal", is_quality_required=True)
    execution = MesOperationExecution(org_id=user.org_id, operation_id=task.id, worker_user_id=user.user_id, status_code="completed",
        tracked_in_at=datetime(2026, 10, 24, tzinfo=UTC), tracked_out_at=datetime(2026, 10, 24, 1, tzinfo=UTC))
    with Session(engine, expire_on_commit=False) as s:
        s.add(order); s.flush(); s.add(task); s.flush(); s.add(execution); s.commit()
    class Adapter:
        def __init__(self, session): self.session = session
        async def exec(self, statement): return self.session.execute(statement)
        async def execute(self, statement): return self.session.execute(statement)
        async def flush(self): self.session.flush()
        async def commit(self): self.session.commit()
        def add(self, row): self.session.add(row)
    @asynccontextmanager
    async def sessions():
        with Session(engine, expire_on_commit=False) as session:
            try: yield Adapter(session)
            except BaseException:
                session.rollback()
                raise
    async def no_change(*_): return False
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(execution_module, "get_session_context", sessions)
    monkeypatch.setattr(execution_module.report_repository, "pending_for_order", no_change)
    monkeypatch.setattr(service, "_detail", lambda_detail)
    from app.modules.mes.archive_repository import archive_repository
    monkeypatch.setattr(archive_repository,"lock_organization",no_change)  # SQLite无PG事务 advisory lock；真实并发门禁由PG实现。
    from app.modules.mes.schedule_plan_repository import repository as plan_repository
    monkeypatch.setattr(plan_repository,"lock_resources",no_change)
    result = NS(user=user, engine=engine, sessions=sessions, order=order.id, task=task.id, execution=execution.id)
    yield result
    engine.dispose()


async def lambda_detail(session, task, order, user):
    return NS(version_no=task.version_no, status_code=task.status_code)


def body(version=1, result="pass", key=None):
    return QualityInspectionBody(version_no=version, result_code=result, note="复检确认" if result == "pass" else "表面毛刺，退回精整", idempotency_key=key or f"inspection-{version}-{result}")


def inspect(store, request=None, user=None):
    return asyncio.run(quality_service.inspect(store.task, request or body(), user or store.user))


def test_release_completes_order_and_unlocks_finished_receipt(store, monkeypatch):
    async def run():
        async with store.sessions() as session:
            order = (await session.exec(select(MesWorkOrder))).scalar_one()
            monkeypatch.setattr(inventory_repository, "operations", lambda_operations)
            assert await inventory_service.produced(session, order) == 0
        result = await quality_service.inspect(store.task, body(), store.user)
        assert result["task"]["status_code"] == "completed"
        async with store.sessions() as session:
            order = (await session.exec(select(MesWorkOrder))).scalar_one()
            assert order.status_code == "completed" and order.good_quantity == 10
            assert await inventory_service.produced(session, order) == 10
            assert len((await session.exec(select(MesExecutionEvent))).scalars().all()) == 1
    asyncio.run(run())


async def lambda_operations(session, identifier):
    return (await session.exec(select(MesWorkOrderOperation).where(MesWorkOrderOperation.work_order_id == identifier))).scalars().all()


def test_fail_requires_new_execution_before_reinspection_without_double_output(store, monkeypatch):
    result = inspect(store, body(result="fail"))
    assert result["task"]["status_code"] == "pending"
    assert result["task"]["good_quantity"] == 10
    with pytest.raises(AppException, match="仅待检验"):
        inspect(store, body(version=2))
    async def run():
        monkeypatch.setattr(inventory_repository, "operations", lambda_operations)
        async with store.sessions() as session:
            order = (await session.exec(select(MesWorkOrder))).scalar_one()
            assert await inventory_service.produced(session, order) == 0
        current = await service.track_in(store.task, ProductionActionBody(version_no=2), store.user)
        assert current.status_code == "in_progress"
        current = await service.track_out(store.task, ProductionActionBody(version_no=current.version_no), store.user)
        assert current.status_code == "waiting_quality"
        result = await quality_service.inspect(store.task, body(version=current.version_no), store.user)
        assert result["task"]["status_code"] == "completed" and result["task"]["good_quantity"] == 10
        detail = await quality_service.detail(store.task, store.user)
        assert [i["result_code"] for i in detail["inspections"]] == ["pass", "fail"]
        assert len({i["execution_id"] for i in detail["inspections"]}) == 2
    asyncio.run(run())


def test_partial_quantity_pass_stays_pending(store):
    with Session(store.engine) as s:
        s.get(MesWorkOrderOperation, store.task).good_quantity = 4
        s.commit()
    result = inspect(store)
    assert result["task"]["status_code"] == "pending"
    assert result["task"]["work_order_status_code"] == "in_progress"


def test_release_nonfinal_process_allows_next_track_in(store):
    with Session(store.engine) as s:
        following = MesWorkOrderOperation(org_id=store.user.org_id, work_order_id=store.order, sequence_no=2, operation_no="20",
            operation_name_snapshot="包装", planned_quantity=10, status_code="pending", priority_code="normal")
        s.add(following); s.commit(); following_id = following.id
    inspect(store)
    result = asyncio.run(service.track_in(following_id, ProductionActionBody(version_no=1), store.user))
    assert result.status_code == "in_progress"


def test_idempotency_stale_version_and_changed_payload(store):
    request = body()
    first, second = inspect(store, request), inspect(store, request)
    assert first["inspection"]["id"] == second["inspection"]["id"]
    assert first["task"]["version_no"] == second["task"]["version_no"]
    with pytest.raises(AppException, match="不同检验"):
        inspect(store, request.model_copy(update={"note": "内容变化"}))
    with pytest.raises(AppException, match="已被其他人员更新"):
        inspect(store, body(key="different-key"))


@pytest.mark.parametrize("scope,expected", [("missing", 403), ("other_org", 404)])
def test_inspect_requires_exact_permission_and_organization_scope(store, scope, expected):
    user = store.user.model_copy(deep=True)
    if scope == "missing": user.permissions.remove("mes:quality:inspect")
    else: user.org_id, user.org_ids = uuid4(), []
    with pytest.raises(AppException) as error:
        inspect(store, user=user)
    assert error.value.status_code == expected
    if scope == "other_org":
        assert asyncio.run(quality_service.tasks(QualityQuery(), user))["total"] == 0
        with pytest.raises(AppException): asyncio.run(quality_service.detail(store.task, user))


@pytest.mark.parametrize("status", ["paused", "cancelled", "completed", "draft"])
def test_frozen_orders_cannot_be_inspected(store, status):
    with Session(store.engine) as s:
        s.get(MesWorkOrder, store.order).status_code = status; s.commit()
    with pytest.raises(AppException, match="当前不能执行"):
        inspect(store)


def test_pending_report_change_blocks_inspection(store, monkeypatch):
    async def pending(*_): return True
    monkeypatch.setattr(execution_module.report_repository, "pending_for_order", pending)
    with pytest.raises(AppException, match="审批中的报工变更"):
        inspect(store)


def test_failed_event_rolls_back_inspection_and_status(store, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError("event failed")
    monkeypatch.setattr(service, "_event", fail)
    with pytest.raises(RuntimeError): inspect(store)
    with Session(store.engine) as s:
        assert s.get(MesWorkOrderOperation, store.task).status_code == "waiting_quality"
        assert s.execute(select(MesQualityInspection)).scalars().all() == []
        assert s.get(MesWorkOrder, store.order).status_code == "in_progress"


@pytest.mark.parametrize("change", ["task_deleted", "order_deleted", "not_required", "open_execution", "no_execution", "no_quantity"])
def test_invalid_task_or_execution_cannot_be_released(store, change):
    with Session(store.engine) as s:
        task, order = s.get(MesWorkOrderOperation, store.task), s.get(MesWorkOrder, store.order)
        if change == "task_deleted": task.deleted_at = datetime.now(UTC)
        elif change == "order_deleted": order.deleted_at = datetime.now(UTC)
        elif change == "not_required": task.is_quality_required = False
        elif change == "no_quantity": task.good_quantity = 0
        elif change == "open_execution": s.get(MesOperationExecution, store.execution).status_code = "in_progress"
        else: s.delete(s.get(MesOperationExecution, store.execution))
        s.commit()
    with pytest.raises(AppException): inspect(store)


def test_inspector_need_not_be_assigned_worker(store):
    other_worker = uuid4()
    with store.engine.begin() as connection:
        connection.execute(Table("sys_user", MetaData(), autoload_with=connection).insert().values(id=other_worker.hex))
    with Session(store.engine) as s:
        s.get(MesWorkOrderOperation, store.task).assigned_user_id = other_worker
        s.commit()
    store.user.permissions.remove("mes:operation_task:manage")
    assert inspect(store)["task"]["status_code"] == "completed"


def test_payload_rejects_missing_reason_extra_fields_and_unknown_conclusion():
    for changes in ({"note": "  "}, {"schema": "t_other"}, {"result_code": "waived"}):
        with pytest.raises(ValidationError):
            QualityInspectionBody.model_validate(dict(version_no=1, result_code="fail", note="尺寸偏差", idempotency_key="inspection-1", **{}) | changes)


def test_no_ai_quality_route_or_table_allowlist():
    from app.integrations.harness_api_policy import http_registry
    from app.modules.mes.ai_catalog import PROVIDER
    registry = http_registry()
    assert registry.resolve("GET", "/api/mes/quality/tasks") is None
    assert registry.resolve("POST", "/api/mes/quality/tasks/{identifier}/inspections") is None
    assert "mes_quality_inspection" not in {resource.table_name for resource in PROVIDER.resources}


def test_http_contract_and_exact_inspection_permission(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from app.auth.dependencies import get_current_user
    from app.modules.mes.quality_api import router
    user = actor()
    user.permissions.extend(["mes:quality:list", "mes:quality:inspect"])
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    app.dependency_overrides[get_current_user] = lambda: user
    submit = AsyncMock(return_value={"task": {"status_code": "completed"}, "inspection": {"result_code": "pass"}})
    monkeypatch.setattr(quality_service, "inspect", submit)
    with TestClient(app) as client:
        path = f"/api/mes/quality/tasks/{uuid4()}/inspections"
        response = client.post(path, json=body().model_dump())
        assert response.status_code == 200 and response.json()["data"]["inspection"]["result_code"] == "pass"
        assert client.post(path, json=body().model_dump() | {"result_code": "fail", "note": " "}).status_code == 422
        user.permissions.remove("mes:quality:inspect")
        assert client.post(path, json=body().model_dump()).status_code == 403
        assert submit.await_count == 1
