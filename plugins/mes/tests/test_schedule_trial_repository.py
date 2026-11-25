"""真实SQLite查询验证双重数据范围与不泄露来源的资源占用契约。"""
import asyncio
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.modules.masterdata.models import MdParty, MdPerson, MdPersonContact
from app.modules.mes.archive_models import MesProcess, MesEquipment, MesEquipmentProcess, MesProcessDependency
from app.modules.mes.calendar_models import MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException
from app.modules.mes.workforce_models import MesProductionPerson, MesPersonProcess
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation, MesOperationExecution, MesProductionReport, MesExecutionEvent, MesWorkOrderEvent
from app.modules.mes.schedule_trial_repository import repository
from app.modules.mes.schedule_trial_schemas import TrialScope
from app.modules.mes.schedule_models import (MesOperationScheduleSetting, MesWorkOrderReadiness, MesWorkOrderInspectionSetting,
    MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment, MesOperationProductionPhase, MesWorkOrderFirstArticle)
from app.modules.mes.quality_models import MesQualityInspection


class Adapter:
    def __init__(self, session): self.session, self.bind = session, session.bind
    async def execute(self, statement): return self.session.execute(statement)


@pytest.fixture
def store():
    from app.framework.db.registry import import_all_models
    import_all_models()
    models = (MdParty, MdPerson, MdPersonContact, MesProcess, MesEquipment, MesEquipmentProcess, MesProcessDependency, MesProductionPerson,
        MesPersonProcess, MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException, MesWorkOrder, MesWorkOrderOperation,
        MesOperationExecution, MesProductionReport, MesExecutionEvent, MesWorkOrderEvent, MesOperationScheduleSetting, MesWorkOrderReadiness, MesWorkOrderInspectionSetting,
        MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment, MesOperationProductionPhase, MesWorkOrderFirstArticle, MesQualityInspection)
    metadata = MetaData()
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external: Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
        for index in table.indexes:
            where = index.dialect_options["postgresql"].get("where")
            if where is not None: index.dialect_options["sqlite"]["where"] = where
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    org, user, other = uuid4(), uuid4(), uuid4()
    actor = NS(user_id=user, org_id=org, org_ids=[], department_id=None, permissions=["mes:schedule:manage"],
        permission_scopes={"mes:schedule:manage": "self"}, org_access_mode_code="selected")
    with Session(engine,expire_on_commit=False) as session:
        work = MesWorkOrder(org_id=org, created_by=user, work_order_no="VISIBLE", product_item_id=uuid4(),
            product_item_no_snapshot="P", product_item_name_snapshot="零件", unit_code="piece",
            planned_quantity=Decimal(2), status_code="released", priority_code="normal")
        session.add(work); session.flush()
        task = MesWorkOrderOperation(org_id=org, created_by=user, work_order_id=work.id, operation_no="10",
            operation_name_snapshot="CNC", sequence_no=1, planned_quantity=2, status_code="pending", priority_code="normal")
        session.add(task); session.commit()
        yield NS(engine=engine, session=session, adapter=Adapter(session), actor=actor, work=work, task=task,
            org=org, user=user, other=other)
    engine.dispose()


def scope(store):
    start = datetime(2030, 11, 11, tzinfo=UTC)
    return TrialScope(org_id=store.org, work_order_ids=[store.work.id], start_at=start, end_at=start + timedelta(days=2))


def test_outsourced_operation_requires_execution_kind_instead_of_standard_minutes(store):
    from app.modules.mes.schedule_trial_planning import base_issues

    request = scope(store)
    process = MesProcess(org_id=store.org, created_by=store.user, process_no="GY25",
                         process_name="拉丝", processing_type_code="outsourced")
    store.session.add(process)
    store.session.flush()
    store.task.process_id = process.id
    store.work.due_at = request.end_at
    store.session.commit()
    snapshot = asyncio.run(repository.snapshot(store.adapter, request, store.actor))
    issues = base_issues(snapshot, request)
    assert len(issues) == 1 and "排程执行类别" in issues[0]

    process.execution_kind_code = "external"
    store.session.commit()
    snapshot = asyncio.run(repository.snapshot(store.adapter, request, store.actor))
    assert base_issues(snapshot, request) == []


def test_visible_order_does_not_make_invisible_child_route_visible(store):
    store.task.created_by = store.other
    store.session.commit()
    snapshot = asyncio.run(repository.snapshot(store.adapter, scope(store), store.actor))
    assert [row.id for row in snapshot["orders"]] == [store.work.id]
    assert not snapshot["tasks"] and snapshot["hidden_route"]


def test_invisible_parent_does_not_leak_visible_task(store):
    store.work.created_by = store.other
    store.session.commit()
    snapshot = asyncio.run(repository.snapshot(store.adapter, scope(store), store.actor))
    assert not snapshot["orders"] and not snapshot["tasks"]


def test_soft_deleted_and_foreign_organization_work_orders_are_excluded(store):
    store.work.deleted_at = datetime.now(UTC)
    store.session.commit()
    assert not asyncio.run(repository.snapshot(store.adapter, scope(store), store.actor))["orders"]
    store.work.deleted_at = None
    store.work.org_id = uuid4()
    store.session.commit()
    assert not asyncio.run(repository.snapshot(store.adapter, scope(store), store.actor))["orders"]


def test_invisible_source_still_reserves_visible_physical_resource_without_source_details(store):
    device = MesEquipment(org_id=store.org, created_by=store.user, equipment_no="E1", equipment_name="测试")
    store.session.add(device); store.session.flush()
    start = scope(store).start_at
    hidden = MesWorkOrder(org_id=store.org, created_by=store.other, work_order_no="CONFIDENTIAL", product_item_id=uuid4(),
        product_item_no_snapshot="SECRET", product_item_name_snapshot="机密", unit_code="piece", planned_quantity=1,
        status_code="released", priority_code="normal")
    store.session.add(hidden); store.session.flush()
    store.session.add(MesWorkOrderOperation(org_id=store.org, created_by=store.other, work_order_id=hidden.id,
        equipment_id=device.id, operation_no="20", operation_name_snapshot="隐藏任务", sequence_no=1, planned_quantity=1,
        status_code="pending", priority_code="normal", planned_start_at=start, planned_end_at=start + timedelta(hours=1)))
    store.session.commit()
    snapshot = asyncio.run(repository.snapshot(store.adapter, scope(store), store.actor))
    assert len(snapshot["reservations"]) == 1
    assert snapshot["reservations"][0][0] == device.id
    assert "CONFIDENTIAL" not in str(snapshot["reservations"]) and "SECRET" not in str(snapshot["reservations"])
    assert len(snapshot["orders"]) == 1


def test_authorized_calendar_keeps_unavailable_exception_created_by_another_user(store):
    device=MesEquipment(org_id=store.org,created_by=store.user,equipment_no="E1",equipment_name="设备")
    store.session.add(device);store.session.flush()
    calendar=MesResourceCalendar(org_id=store.org,created_by=store.user,equipment_id=device.id,
        calendar_name="设备周历",timezone_name="Asia/Shanghai",valid_from=scope(store).start_at.date())
    store.session.add(calendar);store.session.flush()
    blocked=MesResourceCalendarException(org_id=store.org,created_by=store.other,calendar_id=calendar.id,
        start_at=scope(store).start_at,end_at=scope(store).start_at+timedelta(hours=1),exception_type_code="unavailable",reason="不应暴露的原因正文")
    store.session.add(blocked);store.session.commit()
    data=asyncio.run(repository.snapshot(store.adapter,scope(store),store.actor))
    assert {e.id for e in data["exceptions"]}=={blocked.id}
    from app.modules.mes.schedule_trial_planning import prepare
    assert "不应暴露的原因正文" not in str(prepare(data,scope(store)))
