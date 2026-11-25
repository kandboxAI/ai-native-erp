"""生产资源维护专项：真实内存事务、资格有效期、日历例外与授权；不连接业务库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from app.core.exceptions import AppException
from app.modules.masterdata.models import MdPerson
from app.modules.mes import schedule_resource_service as module
from app.modules.mes.schedule_resource_service import service, within_calendar
from app.modules.mes.schedule_resource_schemas import PersonBody, QualificationBody, CalendarBody, CalendarExceptionBody
from app.modules.mes.workforce_models import MesProductionPerson, MesPersonProcess
from app.modules.mes.archive_models import MesProcess
from app.modules.mes.calendar_models import MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException
from app.modules.mes.calendar_windows import effective_windows
from test_schedule_trial_repository import store

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2030, 11, 11, 8, tzinfo=TZ)


@pytest.fixture
def state(store, monkeypatch):
    actor = store.actor
    for permission in (module.LIST, module.MANAGE):
        actor.permissions.append(permission)
        actor.permission_scopes[permission] = "organization"
    actor.enabled_plugin_keys = ["mes"]
    class Adapter:
        async def execute(self, statement): return store.session.execute(statement)
        def add(self, row): store.session.add(row)
        async def flush(self): store.session.flush()
        async def commit(self): store.session.commit()
    @asynccontextmanager
    async def context():
        try: yield Adapter()
        except BaseException: store.session.rollback(); raise
    async def lock(*args): pass
    monkeypatch.setattr(module, "get_session_context", context)
    monkeypatch.setattr(module.archive_repository, "lock_organization", lock)
    person = asyncio.run(service.save_person(PersonBody(org_id=store.org, person_no="P1", full_name="内存测试员工"), actor))
    process = MesProcess(org_id=store.org, process_no="PROC", process_name="试验工艺", created_by=actor.user_id)
    store.session.add(process); store.session.commit()
    return NS(**vars(store), person=person, process=process)


def calendar_body(state):
    return CalendarBody(org_id=state.org, production_person_id=state.person["id"], calendar_name="正常班", valid_from=date(2030, 11, 11),
        periods=[dict(weekday_no=1, period_type_code=kind, start_minute_of_day=a, end_minute_of_day=b)
            for kind, a, b in (("work",480,720),("lunch",720,810),("work",810,1080))])


def test_person_identity_uses_master_data_and_does_not_create_login(state):
    assert state.session.scalar(select(func.count()).select_from(MdPerson)) == 1
    assert state.session.scalar(select(MdPerson)).user_id is None
    body = PersonBody(org_id=state.org, person_no="P2", full_name="内存测试员工")
    with pytest.raises(AppException): asyncio.run(service.save_person(body, state.actor))
    assert state.session.scalar(select(func.count()).select_from(MesProductionPerson)) == 1


def test_skill_cannot_overlap_and_stale_version_is_rejected(state):
    body = QualificationBody(org_id=state.org, process_id=state.process.id, valid_from=START)
    row = asyncio.run(service.save_qualification(state.person["id"], body, state.actor))
    with pytest.raises(AppException): asyncio.run(service.save_qualification(state.person["id"], body, state.actor))
    body.version_no = row["version_no"] + 1
    with pytest.raises(AppException): asyncio.run(service.save_qualification(state.person["id"], body, state.actor, row["id"]))
    assert state.session.scalar(select(func.count()).select_from(MesPersonProcess)) == 1


def test_adjacent_qualifications_are_allowed_and_foreign_process_is_denied(state):
    first = QualificationBody(org_id=state.org, process_id=state.process.id, valid_from=START, valid_to=START+timedelta(days=1))
    asyncio.run(service.save_qualification(state.person["id"], first, state.actor))
    second = QualificationBody(org_id=state.org, process_id=state.process.id, valid_from=first.valid_to)
    asyncio.run(service.save_qualification(state.person["id"], second, state.actor))
    second.org_id = uuid4()
    with pytest.raises(AppException): asyncio.run(service.save_qualification(state.person["id"], second, state.actor))


def test_calendar_updates_keep_old_periods_and_reject_overlapping_dates(state):
    body = calendar_body(state)
    row = asyncio.run(service.save_calendar(body, state.actor))
    with pytest.raises(AppException): asyncio.run(service.save_calendar(body, state.actor))
    body.version_no = row["version_no"]
    body.calendar_name = "调整班次"
    asyncio.run(service.save_calendar(body, state.actor, row["id"]))
    assert state.session.scalar(select(func.count()).select_from(MesResourceCalendarPeriod)) == 6
    assert state.session.scalar(select(func.count()).select_from(MesResourceCalendarPeriod).where(MesResourceCalendarPeriod.deleted_at.is_(None))) == 3


def test_resource_permissions_and_plugin_state_cannot_be_bypassed(state):
    state.actor.enabled_plugin_keys = []
    with pytest.raises(AppException): asyncio.run(service.save_calendar(calendar_body(state), state.actor))


def test_resource_http_permissions_and_calendar_validation_before_service(state,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.dependencies import get_current_user
    from app.modules.mes.schedule_resource_api import router
    from unittest.mock import AsyncMock
    app=FastAPI();app.include_router(router,prefix="/api/mes")
    app.dependency_overrides[get_current_user]=lambda:state.actor
    page=AsyncMock(return_value=dict(items=[],total=0,page=1,page_size=20))
    monkeypatch.setattr(service,"page",page)
    with TestClient(app) as client:
        assert client.get("/api/mes/schedule-resources/people").status_code==200
        state.actor.permissions=["mes:schedule_resource:list"]
        assert client.post("/api/mes/schedule-resources/calendars",json={}).status_code==403
        state.actor.permissions.append("mes:schedule_resource:manage")
        assert client.post("/api/mes/schedule-resources/calendars",json={}).status_code==422


@pytest.mark.parametrize("changes", ["overlap", "timezone", "both_resources", "backwards"])
def test_invalid_calendar_contract_rejected(changes, state):
    body = calendar_body(state).model_dump()
    if changes == "overlap": body["periods"][1]["start_minute_of_day"] = 700
    if changes == "timezone": body["timezone_name"] = "Not/A_Zone"
    if changes == "both_resources": body["equipment_id"] = uuid4()
    if changes == "backwards": body["valid_to"] = date(2030,11,10)
    with pytest.raises(ValidationError): CalendarBody(**body)


def test_exceptions_are_versioned_and_limited_to_parent_effective_dates(state):
    row = asyncio.run(service.save_calendar(calendar_body(state), state.actor))
    body = CalendarExceptionBody(org_id=state.org, start_at=START+timedelta(hours=1), end_at=START+timedelta(hours=2),
        exception_type_code="unavailable", reason="维修")
    saved = asyncio.run(service.save_exception(row["id"], body, state.actor))
    assert saved["calendar_id"] == row["id"]
    assert state.session.get(MesResourceCalendar,row["id"]).version_no == 2
    body.start_at = START - timedelta(days=1)
    with pytest.raises(AppException): asyncio.run(service.save_exception(row["id"], body, state.actor))


def test_right_open_calendar_allows_exception_ending_at_expiry_midnight():
    assert within_calendar(START, datetime(2030,11,12,tzinfo=TZ), date(2030,11,11),date(2030,11,12),"Asia/Shanghai")


def test_absence_overrides_overtime_and_does_not_become_lunch(state):
    body=calendar_body(state)
    c=NS(id=uuid4(), org_id=state.org, timezone_name="Asia/Shanghai", valid_from=body.valid_from, valid_to=None, is_active=True, deleted_at=None)
    periods=[NS(**p.model_dump(), calendar_id=c.id, org_id=c.org_id,is_active=True,deleted_at=None) for p in body.periods]
    exceptions=[NS(calendar_id=c.id,is_active=True,deleted_at=None,start_at=START,end_at=START+timedelta(hours=4),exception_type_code="extra_available"),
        NS(calendar_id=c.id,is_active=True,deleted_at=None,start_at=START+timedelta(hours=1),end_at=START+timedelta(hours=2),exception_type_code="unavailable")]
    result=effective_windows(c,periods,exceptions,body.valid_from)
    assert result["work"][0] == (START,START+timedelta(hours=1))
    assert result["work"][1][0] == START+timedelta(hours=2)
    assert not any(a <= START+timedelta(hours=1,minutes=30) < b for a,b in result["auto"])
