"""制造异常专项：SQLite 真事务，范围、角色分工、幂等与通知；不访问开发库。"""
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
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppException
from app.modules.mes import exception_service as module
from app.modules.mes.exception_service import exception_service as service
from app.modules.mes.exception_repository import exception_repository as repo
from app.modules.mes.exception_models import MesExceptionCase, MesExceptionEvent
from app.modules.mes.exception_schemas import ExceptionCreate, ExceptionCommand, ExceptionQuery
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation
from app.modules.mes.api import router
from test_production_management import actor

NOW=datetime(2026,10,25,4,tzinfo=UTC)
PERMISSIONS=[f"mes:exception:{suffix}" for suffix in ("list","create","manage","handle","review")]


@pytest.fixture
def store(monkeypatch):
    from app.framework.db.registry import import_all_models
    import_all_models()
    user=actor(); user.permissions+=PERMISSIONS; user.permission_scopes.update({key:"organization" for key in PERMISSIONS})
    owner,other_org,product=uuid4(),uuid4(),uuid4()
    engine=create_engine("sqlite:///:memory:")
    @event.listens_for(engine,"connect")
    def foreign_keys(connection,_): connection.execute("PRAGMA foreign_keys=ON")
    metadata=MetaData(); models=(MesWorkOrder,MesWorkOrderOperation,MesExceptionCase,MesExceptionEvent)
    names={model.__tablename__ for model in models}
    external={fk.target_fullname.rsplit(".",1)[0] for model in models for fk in model.__table__.foreign_keys}-names
    for name in external: Table(name,metadata,Column("id",Uuid,primary_key=True))
    for model in models:
        table=model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default=None
            if isinstance(column.type,JSONB): column.type=JSON()
    metadata.create_all(engine)
    with engine.begin() as connection:
        for name,ids in (("sys_org",[user.org_id,other_org]),("sys_user",[user.user_id,owner]),("md_item",[product])):
            for identifier in ids: connection.execute(metadata.tables[name].insert().values(id=identifier))
    order=MesWorkOrder(org_id=user.org_id,created_by=user.user_id,work_order_no="MO1",product_item_id=product,
        product_item_no_snapshot="P1",product_item_name_snapshot="支架",unit_code="piece",planned_quantity=10,priority_code="normal",status_code="released")
    task=MesWorkOrderOperation(org_id=user.org_id,work_order_id=order.id,sequence_no=1,operation_no="10",operation_name_snapshot="机加",planned_quantity=10,priority_code="normal",status_code="pending")
    with Session(engine) as session: session.add(order);session.flush();session.add(task);session.commit()
    # UUID 在 commit 前保存，避免离线 Session 关闭后触发过期字段加载。
    with Session(engine) as session:
        order_id=session.scalar(select(MesWorkOrder.id));task_id=session.scalar(select(MesWorkOrderOperation.id))
    class Adapter:
        def __init__(self,session):self.session=session
        async def execute(self,statement):return self.session.execute(statement)
        async def exec(self,statement):return self.session.execute(statement)
        async def flush(self):self.session.flush()
        async def commit(self):self.session.commit()
        def add(self,row):self.session.add(row)
    @asynccontextmanager
    async def sessions():
        with Session(engine,expire_on_commit=False) as session:
            try:yield Adapter(session)
            except BaseException:session.rollback();raise
    monkeypatch.setattr(module,"get_session_context",sessions)
    monkeypatch.setattr(module,"utc_now",lambda:NOW)
    monkeypatch.setattr(module,"user_display_names",AsyncMock(return_value={owner:"责任人",user.user_id:"提出人"}))
    async def valid_assignee(session,identifier,org):return identifier in {owner,user.user_id} and org==user.org_id
    monkeypatch.setattr(module.production_repo,"is_active_assignee",valid_assignee)
    notice=AsyncMock(return_value=NS(created=True,skipped_reason=None))
    monkeypatch.setattr(module,"notify",notice)
    monkeypatch.setattr(repo,"is_ready",AsyncMock(return_value=True))
    result=NS(user=user,owner=owner,other_org=other_org,engine=engine,order=order_id,task=task_id,sessions=sessions,notify=notice)
    yield result
    engine.dispose()


def body(store,**changes):
    return ExceptionCreate(**{**dict(work_order_id=store.order,operation_id=store.task,title="设备故障",description="内部现场说明",
        exception_type_code="equipment_failure",assigned_user_id=store.owner,due_at=NOW+timedelta(hours=1),idempotency_key="create1"),**changes})


def create(store,**changes):return asyncio.run(service.create(body(store,**changes),store.user))


def owner(store):
    user=store.user.model_copy(deep=True);user.user_id=store.owner
    user.permissions=["mes:exception:list","mes:exception:handle"]
    user.permission_scopes={key:"self" for key in user.permissions}
    return user


def command(store,row,action,user=None,**changes):
    return asyncio.run(service.command(row["id"],action,ExceptionCommand(**{**dict(version_no=row["version_no"],note="处理说明"),**changes}),user or store.user))


def test_create_retries_are_idempotent_and_notification_does_not_include_free_text(store):
    first=create(store);second=create(store)
    assert first["id"]==second["id"] and first["status_code"]=="pending"
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesExceptionCase))==1
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==1
    assert store.notify.await_count==1
    assert "内部现场说明" not in str(store.notify.call_args.kwargs)
    with pytest.raises(AppException,match="其他内容"):create(store,title="其他故障")


def test_complete_lifecycle_requires_owner_then_independent_reviewer_and_preserves_history(store):
    row=create(store)
    with pytest.raises(AppException):command(store,row,"start")
    row=command(store,row,"start",owner(store));assert row["status_code"]=="in_progress"
    row=command(store,row,"progress",owner(store))
    row=command(store,row,"resolve",owner(store));assert row["status_code"]=="waiting_confirmation"
    row=command(store,row,"reject");assert row["status_code"]=="in_progress"
    row=command(store,row,"resolve",owner(store))
    row=command(store,row,"approve");assert row["status_code"]=="closed"
    row=command(store,row,"reopen");assert row["status_code"]=="in_progress" and row["closed_at"] is None
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==8
        assert session.get(MesWorkOrder,store.order).status_code=="released"
        assert session.get(MesWorkOrderOperation,store.task).status_code=="pending"


def test_handler_cannot_review_own_resolution_even_with_review_permission(store):
    row=create(store);handler=owner(store)
    handler.permissions.append("mes:exception:review");handler.permission_scopes["mes:exception:review"]="self"
    row=command(store,row,"start",handler);row=command(store,row,"resolve",handler)
    assert "approve" not in row["allowed_actions"]
    with pytest.raises(AppException):command(store,row,"approve",handler)


def test_stale_version_invalid_assignee_or_cross_order_operation_do_not_change_data(store):
    with pytest.raises(AppException):create(store,operation_id=uuid4())
    with pytest.raises(AppException):create(store,assigned_user_id=uuid4())
    row=create(store)
    with pytest.raises(AppException):command(store,row,"assign",assigned_user_id=uuid4())
    changed=command(store,row,"start",owner(store))
    with pytest.raises(AppException,match="已更新"):command(store,row,"resolve",owner(store))
    current=asyncio.run(service.detail(row["id"],store.user))
    assert current["version_no"]==changed["version_no"] and current["status_code"]=="in_progress"


def test_self_scope_includes_assignee_but_reassignment_removes_old_owner_access(store):
    row=create(store)
    assert asyncio.run(service.page(ExceptionQuery(),owner(store)))["total"]==1
    command(store,row,"assign",assigned_user_id=store.user.user_id,due_at=NOW+timedelta(hours=2))
    assert asyncio.run(service.page(ExceptionQuery(),owner(store)))["total"]==0
    with pytest.raises(AppException):asyncio.run(service.detail(row["id"],owner(store)))
    with pytest.raises(AppException):asyncio.run(service.history(row["id"],ExceptionQuery(),owner(store)))
    foreign=store.user.model_copy(deep=True);foreign.org_id=store.other_org
    assert asyncio.run(service.page(ExceptionQuery(),foreign))["total"]==0
    store.user.permission_scopes["mes:exception:list"]="related"
    assert asyncio.run(service.page(ExceptionQuery(),store.user))["total"]==0


def test_notification_failure_rolls_back_case_and_event(store):
    store.notify.side_effect=RuntimeError("notification failure")
    with pytest.raises(RuntimeError):create(store)
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesExceptionCase))==0
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==0


def test_failed_result_notification_rolls_back_state_revision_and_processing_event(store):
    row=command(store,create(store),"start",owner(store))
    store.notify.side_effect=RuntimeError("notification failed")
    with pytest.raises(RuntimeError):command(store,row,"resolve",owner(store))
    with Session(store.engine) as session:
        case=session.get(MesExceptionCase,row["id"])
        assert case.status_code=="in_progress" and case.version_no==2 and case.resolved_by is None
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==2


def test_overdue_reminder_is_locked_throttled_and_does_not_increment_business_version(store,monkeypatch):
    row=create(store)
    monkeypatch.setattr(module,"utc_now",lambda:NOW+timedelta(hours=2))
    assert asyncio.run(service.remind_overdue())==1
    assert asyncio.run(service.remind_overdue())==0
    with Session(store.engine) as session:
        case=session.get(MesExceptionCase,row["id"])
        assert case.last_reminded_at is not None and case.version_no==1
    monkeypatch.setattr(module,"utc_now",lambda:NOW+timedelta(hours=27))
    assert asyncio.run(service.remind_overdue())==1


def test_unconfigured_notification_does_not_falsely_mark_reminder_delivered(store,monkeypatch):
    row=create(store);store.notify.return_value=NS(created=False,skipped_reason="scene_disabled")
    monkeypatch.setattr(module,"utc_now",lambda:NOW+timedelta(hours=2))
    assert asyncio.run(service.remind_overdue())==0
    with Session(store.engine) as session:assert session.get(MesExceptionCase,row["id"]).last_reminded_at is None


def test_closed_case_stops_overdue_reminders(store,monkeypatch):
    row=command(store,create(store),"start",owner(store))
    row=command(store,row,"resolve",owner(store));command(store,row,"approve")
    monkeypatch.setattr(module,"utc_now",lambda:NOW+timedelta(hours=2))
    count=store.notify.await_count
    assert asyncio.run(service.remind_overdue())==0 and store.notify.await_count==count


def test_past_deadline_rejected_before_any_case_or_notice_is_saved(store):
    with pytest.raises(AppException,match="期限"):create(store,due_at=NOW-timedelta(hours=1))
    store.notify.assert_not_awaited()
    with Session(store.engine) as session:assert session.scalar(select(func.count()).select_from(MesExceptionCase))==0


@pytest.mark.parametrize("changes",[{"title":" "},{"due_at":"2026-10-25T12:00:00"},{"exception_type_code":"unknown"}])
def test_invalid_registration_rejected(store,changes):
    with pytest.raises(ValidationError):body(store,**changes)


def test_http_requires_permission_and_history_does_not_bypass_source_scope(store,monkeypatch):
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:store.user
    monkeypatch.setattr(service,"page",AsyncMock(return_value=dict(items=[],total=0,page=1,page_size=20)))
    with TestClient(app) as client:
        assert client.get("/api/mes/exceptions").status_code==200
        assert client.get("/api/mes/exceptions?status_code=unknown").status_code==422
        store.user.permissions=[]
        assert client.get("/api/mes/exceptions").status_code==403
        assert client.post(f"/api/mes/exceptions/{uuid4()}/actions/approve",json={"version_no":1}).status_code==403
    app.dependency_overrides.clear()
    with TestClient(app) as client:assert client.get("/api/mes/exceptions").status_code==401


def test_new_models_and_notifications_registered_without_auto_publishing_ai_tools():
    from app.integrations.harness_api_policy import http_registry
    from app.modules.notification_center.tenant_setup import builtin_scene_specs
    from app.modules.mes.jobs import JOBS
    assert http_registry().resolve("GET","/api/mes/exceptions") is None
    assert http_registry().resolve("POST","/api/mes/exceptions") is None
    assert http_registry().resolve("POST",f"/api/mes/exceptions/{uuid4()}/actions/approve") is None
    assert {row["scene_key"] for row in builtin_scene_specs()} >= {"mes.exception.assigned","mes.exception.review","mes.exception.closed","mes.exception.overdue"}
    assert JOBS[0].key=="mes.exception.overdue" and JOBS[0].per_tenant
