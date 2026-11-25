"""交付驾驶舱专项：离线 SQLite 真查询与 HTTP 鉴权，不访问业务数据库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppException
from app.modules.mes import cockpit_service as module
from app.modules.mes.api import router
from app.modules.mes.cockpit_service import cockpit_service
from app.modules.mes.cockpit_schemas import DeliveryCockpitQuery
from app.modules.mes.cockpit_repository import cockpit_repository, midnight
from app.modules.mes.models import MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesProductionReport, MesProductionReportChange
from app.modules.mes.delivery_models import MesShipment, MesShipmentLine
from app.modules.mes.exception_models import MesExceptionCase, MesExceptionEvent
from test_production_management import actor

NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)


@pytest.fixture
def store(monkeypatch):
    from app.framework.db.registry import import_all_models
    import_all_models()
    user = actor()
    user.permissions.append("mes:dashboard:view")
    user.permission_scopes["mes:dashboard:view"] = "organization"
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    models = (MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesProductionReport, MesProductionReportChange, MesShipment, MesShipmentLine, MesExceptionCase, MesExceptionEvent)
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external: Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
    metadata.create_all(engine)
    product, other_org, other_user = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        for name, identifiers in (("sys_org", [user.org_id, other_org]), ("sys_user", [user.user_id, other_user]), ("md_item", [product])):
            for identifier in identifiers: connection.execute(metadata.tables[name].insert().values(id=identifier))
    reads = []
    class Adapter:
        def __init__(self, session): self.session = session
        async def execute(self, statement):
            reads.append(statement)
            return self.session.execute(statement)
    @asynccontextmanager
    async def sessions():
        with Session(engine) as session: yield Adapter(session)
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(module, "utc_now", lambda: NOW)
    result = NS(user=user, product=product, other_org=other_org, other_user=other_user, engine=engine, sessions=sessions, reads=reads)
    yield result
    engine.dispose()


def order(store, number="MO-01", **changes):
    row = MesWorkOrder(**{**dict(org_id=store.user.org_id, created_by=store.user.user_id, work_order_no=number,
        product_item_id=store.product, product_item_no_snapshot="P1", product_item_name_snapshot="支架", unit_code="piece",
        planned_quantity=10, priority_code="normal", status_code="in_progress", due_at=NOW-timedelta(days=1)), **changes})
    with Session(store.engine, expire_on_commit=False) as session: session.add(row); session.commit()
    return row.id


def operation(store, order_id, sequence=1, **changes):
    row = MesWorkOrderOperation(**{**dict(org_id=store.user.org_id, work_order_id=order_id, sequence_no=sequence,
        operation_no=str(sequence), operation_name_snapshot=f"工序{sequence}", planned_quantity=10, priority_code="normal", status_code="pending"), **changes})
    with Session(store.engine, expire_on_commit=False) as session: session.add(row); session.commit()
    return row.id


def shipment(store, order_id, quantity, status="posted", mode="direct"):
    header = MesShipment(org_id=store.user.org_id, shipment_no=str(uuid4()), customer_no_snapshot="C1", customer_name_snapshot="客户",
        business_date=NOW.date(), status_code=status, fulfillment_mode_code=mode, idempotency_key=str(uuid4()), request_hash="a"*64)
    line = MesShipmentLine(org_id=store.user.org_id, shipment_id=header.id, work_order_id=order_id, product_item_id=store.product,
        work_order_no_snapshot="MO", product_item_no_snapshot="P1", product_item_name_snapshot="支架", unit_code="piece", quantity=quantity, unit_price=1, amount=quantity)
    with Session(store.engine) as session: session.add(header); session.flush(); session.add(line); session.commit()


def read(store, **query):
    return asyncio.run(cockpit_service.read(DeliveryCockpitQuery(**query), store.user))


def test_summary_covers_all_pages_and_shipment_aggregation_does_not_multiply_operations(store):
    first = order(store)
    operation(store, first, 1, status_code="completed", good_quantity=100)
    operation(store, first, 2, status_code="completed", good_quantity=10, is_quality_required=True)
    shipment(store, first, 2)
    shipment(store, first, 3, mode="stock")
    for status in ("draft", "awaiting_stock", "cancelled"): shipment(store, first, 8, status=status)
    for index in range(11): order(store, f"OTHER-{index}")
    result = read(store, page_size=1)
    assert result["summary"]["total"] == result["total"] == 12
    assert len(result["items"]) == 1
    second_page = read(store, page=2, page_size=1)
    assert second_page["summary"]["total"] == 12 and len(second_page["items"]) == 1
    item = read(store, keyword="MO-01")["items"][0]
    assert item["shipped_quantity"] == "5.000" and item["outstanding_quantity"] == "5.000"
    assert item["released_good_quantity"] == "10.000" and item["operation_count"] == 2
    assert len(store.reads) == 6 and all(statement.is_select for statement in store.reads)
    assert not {"amount", "unit_price", "created_by", "note", "actor_name_snapshot"} & item.keys()


def test_completion_is_not_delivery_and_cancelled_shipments_release_delivery_quantity(store):
    identifier = order(store, status_code="completed")
    operation(store, identifier, status_code="completed", good_quantity=10)
    result = read(store)
    assert result["summary"]["overdue"] == 1 and result["summary"]["delivered"] == 0
    shipment(store, identifier, 10)
    delivered = read(store, focus="delivered")
    assert delivered["total"] == 1 and delivered["items"][0]["delivery_status"] == "delivered"
    assert read(store)["total"] == 0
    with Session(store.engine) as session:
        row = session.query(MesShipment).one(); row.status_code = "cancelled"; session.commit()
    assert read(store)["total"] == 1


def test_quality_and_approval_gates_do_not_claim_released_output(store):
    identifier = order(store)
    task_id = operation(store, identifier, status_code="waiting_quality", good_quantity=10, is_quality_required=True)
    item = read(store)["items"][0]
    assert item["released_good_quantity"] == "0.000" or item["released_good_quantity"] == "0"
    assert "waiting_quality" in item["risk_flags"]
    with Session(store.engine) as session:
        session.get(MesWorkOrderOperation, task_id).status_code = "completed"
        report = MesProductionReport(org_id=store.user.org_id, operation_id=task_id, report_no="R1", good_quantity=10,
            scrap_quantity=0, rework_quantity=0, idempotency_key="r1", source_code="web", status_code="posted", reported_at=NOW, created_by=store.user.user_id)
        session.add(report); session.flush()
        session.add(MesProductionReportChange(org_id=store.user.org_id, report_id=report.id, change_type_code="reverse", status_code="submitted",
            good_quantity=0, scrap_quantity=0, rework_quantity=0, reason="检查", idempotency_key="c1")); session.commit()
    result = read(store)
    assert result["summary"]["released_output"] == 0 and result["summary"]["blocked"] == 1
    assert "pending_change" in result["items"][0]["risk_flags"]


def test_due_buckets_use_beijing_midnight_and_soon_window_has_exclusive_end(store):
    today = NOW.astimezone(module.TZ).date()
    order(store, "TODAY", due_at=midnight(today)+timedelta(hours=20))
    order(store, "TOMORROW", due_at=midnight(today)+timedelta(days=1))
    order(store, "BOUNDARY", due_at=midnight(today)+timedelta(days=7))
    order(store, "UNSET", due_at=None)
    result = read(store, focus="due_soon")
    assert result["total"] == 2
    assert [item["order_count"] for item in result["due_buckets"][:2]] == [1, 1]
    assert read(store, focus="no_due")["total"] == 1
    assert read(store, due_from=today, due_to=today)["total"] == 1


def test_scopes_intersect_and_soft_deleted_or_cancelled_orders_are_excluded(store):
    order(store, "MINE")
    order(store, "OTHER-USER", created_by=store.other_user)
    order(store, "OTHER-ORG", org_id=store.other_org)
    order(store, "DELETED", deleted_at=NOW, deleted_by=store.user.user_id)
    order(store, "CANCELLED", status_code="cancelled")
    store.user.permission_scopes["mes:dashboard:view"] = "self"
    result = read(store, focus="all")
    assert result["total"] == 1 and result["items"][0]["work_order_no"] == "MINE"
    store.user.permission_scopes["mes:dashboard:view"] = "all"
    assert read(store)["total"] == 2
    assert read(store, org_id=store.other_org)["total"] == 0
    store.user.permission_scopes["mes:work_order:list"] = "related"
    assert read(store)["total"] == 0


def test_current_operation_and_late_plan_flags_use_first_unfinished_operation(store):
    identifier = order(store, due_at=NOW+timedelta(days=1))
    operation(store, identifier, 1, status_code="completed", good_quantity=10)
    operation(store, identifier, 2, status_code="in_progress", planned_start_at=NOW-timedelta(hours=2), planned_end_at=NOW-timedelta(hours=1))
    operation(store, identifier, 3, planned_start_at=NOW+timedelta(days=2), planned_end_at=NOW+timedelta(days=3))
    result = read(store, focus="blocked")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["current_operation_name"] == "工序2"
    assert {"operation_late", "plan_after_due"}.issubset(item["risk_flags"])


def test_cockpit_counts_unclosed_exceptions_without_multiplying_orders_or_exposing_notes(store):
    identifier=order(store,status_code="completed")
    shipment(store,identifier,10)
    with Session(store.engine) as session:
        for index,status in enumerate(("pending","in_progress","closed")):
            session.add(MesExceptionCase(org_id=store.user.org_id,case_no=f"E{index}",work_order_id=identifier,title="内部说明",
                description="不可出现在驾驶舱",exception_type_code="other",status_code=status,due_at=NOW-timedelta(hours=1),idempotency_key=f"k{index}",request_hash="a"*64))
        session.commit()
    result=read(store,focus="exceptions")
    assert result["total"]==result["summary"]["exceptions"]==1
    item=result["items"][0]
    assert item["open_exception_count"]==item["overdue_exception_count"]==2
    assert item["delivery_status"]=="delivered" and "overdue_exception" in item["risk_flags"]
    assert "内部说明" not in str(result) and "不可出现在驾驶舱" not in str(result)


@pytest.mark.parametrize("query", [{"due_from":"2026-10-26","due_to":"2026-10-25"}, {"soon_days":31}, {"page_size":101}, {"focus":"invented"}])
def test_invalid_query_is_rejected(query):
    with pytest.raises(ValidationError): DeliveryCockpitQuery(**query)


def test_http_requires_both_permissions_and_does_not_publish_ai_tool(monkeypatch):
    app = FastAPI(); app.include_router(router)
    user = actor(); user.permissions.append("mes:dashboard:view")
    app.dependency_overrides[get_current_user] = lambda: user
    mock = AsyncMock(return_value={"items":[], "summary":{}})
    monkeypatch.setattr(cockpit_service, "read", mock)
    with TestClient(app) as client:
        assert client.get("/api/mes/delivery-cockpit").status_code == 200
        assert client.get("/api/mes/delivery-cockpit?soon_days=99").status_code == 422
        user.permissions = ["mes:dashboard:view"]
        assert client.get("/api/mes/delivery-cockpit").status_code == 403
        user.permissions = ["mes:work_order:list"]
        assert client.get("/api/mes/delivery-cockpit").status_code == 403
    app.dependency_overrides.clear()
    with TestClient(app) as client: assert client.get("/api/mes/delivery-cockpit").status_code == 401
    from app.integrations.harness_api_policy import http_registry
    assert http_registry().resolve("GET", "/api/mes/delivery-cockpit") is None


def test_service_permission_check_precedes_any_database_access(store):
    store.user.permissions.remove("mes:dashboard:view")
    with pytest.raises(AppException): read(store)
    assert not store.reads
