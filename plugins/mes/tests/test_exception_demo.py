"""异常演示数据专项：预览、幂等保留、事务回滚及不触发提醒。"""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from app.modules.mes.demo_seed import seed_exception_demo
from app.modules.mes.exception_demo_repository import exception_demo_repository as repo
from app.modules.mes.exception_models import MesExceptionCase,MesExceptionEvent
from app.modules.mes.models import MesWorkOrder,MesWorkOrderOperation
from app.modules.mes import exception_service as module
from test_exceptions import store, NOW


@pytest.fixture(autouse=True)
def active_users(store,monkeypatch):
    monkeypatch.setattr(repo,"users",AsyncMock(return_value=[store.user.user_id,store.owner]))


def run(store,apply=True,now=NOW):
    async def task():
        async with store.sessions() as session:
            result=await seed_exception_demo(session,work_order_no="MO1",apply=apply,now=now)
            if apply: await session.commit()
            return result
    return asyncio.run(task())


def test_preview_is_read_only_and_apply_creates_all_scenarios_without_touching_production(store):
    preview=run(store,apply=False)
    assert preview["created"]==6
    with Session(store.engine) as session:assert session.scalar(select(func.count()).select_from(MesExceptionCase))==0
    result=run(store)
    assert result["created"]==6
    with Session(store.engine) as session:
        rows=session.scalars(select(MesExceptionCase)).all()
        assert {row.status_code for row in rows}=={"pending","in_progress","waiting_confirmation","closed"}
        assert all(row.title.startswith("【演示】") and row.flex_form["demo"] for row in rows)
        closed=next(row for row in rows if row.status_code=="closed")
        assert closed.closed_by!=closed.resolved_by
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==17
        assert session.get(MesWorkOrder,store.order).status_code=="released"
        assert session.get(MesWorkOrderOperation,store.task).status_code=="pending"
    store.notify.assert_not_awaited()


def test_rerun_preserves_existing_demo_state_title_deadline_and_records(store):
    run(store)
    with Session(store.engine) as session:
        row=session.scalars(select(MesExceptionCase).where(MesExceptionCase.case_no=="EX-DEMO-EQUIPMENT")).one()
        identifier=row.id;deadline=row.due_at
        row.title="用户已修改演示标题";session.commit()
    result=run(store,now=NOW+timedelta(days=1))
    assert result["created"]==0 and result["preserved"]==6
    with Session(store.engine) as session:
        row=session.get(MesExceptionCase,identifier)
        assert row.title=="用户已修改演示标题" and row.due_at==deadline
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==17


def test_single_active_user_skips_closed_scenario_instead_of_self_review(store,monkeypatch):
    monkeypatch.setattr(repo,"users",AsyncMock(return_value=[store.user.user_id]))
    result=run(store)
    assert result["created"]==5 and len(result["skipped"])==1
    assert "第二名活动用户" in result["skipped"][0]


def test_demo_cases_do_not_generate_automatic_overdue_notices(store,monkeypatch):
    run(store)
    monkeypatch.setattr(module,"utc_now",lambda:NOW+timedelta(days=2))
    assert asyncio.run(module.exception_service.remind_overdue())==0
    store.notify.assert_not_awaited()


def test_conflicting_real_case_number_aborts_entire_seed_without_overwrite(store):
    with Session(store.engine) as session:
        session.add(MesExceptionCase(org_id=store.user.org_id,case_no="EX-DEMO-MATERIAL",work_order_id=store.order,title="真实记录",
            description="不可覆盖",exception_type_code="other",due_at=NOW+timedelta(hours=1),idempotency_key="real",request_hash="a"*64))
        session.commit()
    with pytest.raises(RuntimeError,match="占用"):run(store)
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesExceptionCase))==1
        assert session.scalar(select(func.count()).select_from(MesExceptionEvent))==0


def test_failure_rolls_back_all_inserted_demo_rows(store,monkeypatch):
    add=repo.add
    def fail(session,row):
        if isinstance(row,MesExceptionEvent):raise RuntimeError("event write failed")
        add(session,row)
    monkeypatch.setattr(repo,"add",fail)
    with pytest.raises(RuntimeError):run(store)
    with Session(store.engine) as session:assert session.scalar(select(func.count()).select_from(MesExceptionCase))==0
