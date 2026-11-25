"""常规日历与午休语义；只使用内存SQLite，不访问业务库。"""
from datetime import date, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, select, func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.mes.calendar_models import MesResourceCalendar, MesResourceCalendarPeriod
from app.modules.mes import calendar_service as module
from app.modules.mes.calendar_service import service, WorkWeek, day_windows
from app.modules.mes.workforce_models import MesProductionPerson
from app.modules.masterdata.models import MdParty, MdPerson
from test_workforce_import import state, Adapter
from test_quotations import run


@pytest.fixture
def calendars(state, monkeypatch):
    metadata = MetaData()
    # 已有人员fixture建好了这些引用表，本组只补日历模型。
    from sqlalchemy import Table, Column, Uuid
    for name in ('sys_org','sys_user','mes_production_person','mes_equipment'):
        Table(name, metadata, Column('id',Uuid,primary_key=True))
    for model in (MesResourceCalendar, MesResourceCalendarPeriod):
        table=model.__table__.to_metadata(metadata)
        from sqlalchemy import JSON
        from sqlalchemy.dialects.postgresql import JSONB
        for column in table.columns:
            column.server_default=None
            if isinstance(column.type,JSONB):column.type=JSON()
        for index in table.indexes:
            where=index.dialect_options['postgresql'].get('where')
            if where is not None:index.dialect_options['sqlite']['where']=where
    metadata.create_all(state.engine)
    async def ready(*args):return []
    async def resources(*args):return state.resources
    async def noop(*args):pass
    async def options(*args):return {'mes_calendar_period_type':[{'item_code':'work'},{'item_code':'lunch'}]}
    monkeypatch.setattr(module.repository,'missing',ready)
    monkeypatch.setattr(module.repository,'imported_resources',resources)
    monkeypatch.setattr(module,'ensure_builtin_definitions',noop)
    monkeypatch.setattr(module.dictionaries,'options_in_session',options)
    person_id,equipment_id=uuid4(),uuid4()
    # 本组聚焦日历事务，使用已存在的合法人员/设备FK占位。
    with state.engine.begin() as connection:
        connection.exec_driver_sql('INSERT INTO mes_equipment (id) VALUES (?)',(equipment_id.hex,))
    with Session(state.engine) as session:
        party=MdParty(party_type_code='person',display_name='日历测试人员',created_by=state.actor.user_id)
        session.add(party);session.flush()
        session.add(MdPerson(party_id=party.id,full_name='日历测试人员'));session.flush()
        session.add(MesProductionPerson(id=person_id,org_id=state.org_id,person_no='CAL-P',party_id=party.id));session.commit()
    state.resources=[('person',person_id),('equipment',equipment_id)]
    return state


def test_person_85_hours_equipment_10_hours_and_weekend_empty(calendars):
    with Session(calendars.engine) as session:
        result=run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()));session.commit()
        assert result=={'new_calendars':2,'new_periods':20}
        periods=session.scalars(select(MesResourceCalendarPeriod)).all()
        for calendar in session.scalars(select(MesResourceCalendar)):
            window=day_windows(calendar,periods,date(2026,11,9))
            minutes=sum((end-start).total_seconds()/60 for start,end in window['work'])
            assert minutes==(510 if calendar.production_person_id else 600)
            assert len(window['lunch'])==(1 if calendar.production_person_id else 0)
            if calendar.production_person_id:
                assert [start.strftime('%H:%M') for start,end in window['work']]==['08:00','13:30']
            assert day_windows(calendar,periods,date(2026,11,14))=={'work':[],'lunch':[]}
            assert all(start.utcoffset()==timedelta(hours=8) for start,end in window['work'])
        assert run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,10),WorkWeek()))=={'new_calendars':0,'new_periods':0}


@pytest.mark.parametrize('change',['period','timezone','disabled','future','end'])
def test_existing_custom_or_inactive_calendar_not_overwritten(calendars,change):
    with Session(calendars.engine) as session:
        run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()));session.commit()
        calendar=session.scalar(select(MesResourceCalendar))
        if change=='period':session.scalar(select(MesResourceCalendarPeriod)).start_minute_of_day=500
        if change=='timezone':calendar.timezone_name='UTC'
        if change=='disabled':calendar.is_active=False
        if change=='future':calendar.valid_from=date(2026,11,10)
        if change=='end':calendar.valid_to=date(2026,12,1)
        session.commit()
        with pytest.raises(AppException):run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()))
        assert session.scalar(select(func.count()).select_from(MesResourceCalendar))==2


def test_missing_dictionary_and_caller_rollback_leave_no_calendars(calendars,monkeypatch):
    with Session(calendars.engine) as session:
        run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()));session.rollback()
        assert session.scalar(select(func.count()).select_from(MesResourceCalendar))==0
        async def invalid(*args):return {'mes_calendar_period_type':[{'item_code':'work'}]}
        monkeypatch.setattr(module.dictionaries,'options_in_session',invalid)
        with pytest.raises(AppException):run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()))
        assert session.scalar(select(func.count()).select_from(MesResourceCalendar))==0


def test_scope_and_invalid_lunch_fail_closed(calendars):
    with Session(calendars.engine) as session:
        with pytest.raises(AppException):run(service.apply(Adapter(session),calendars.actor,uuid4(),date(2026,11,9),WorkWeek()))
    with pytest.raises(ValueError):WorkWeek(lunch_end_minute=700).validate()
    with pytest.raises(ValueError):WorkWeek(start_minute=-1).validate()


def test_validity_end_and_disabled_period_do_not_create_work(calendars):
    with Session(calendars.engine) as session:
        run(service.apply(Adapter(session),calendars.actor,calendars.org_id,date(2026,11,9),WorkWeek()));session.commit()
        calendar=session.scalar(select(MesResourceCalendar).where(MesResourceCalendar.production_person_id.is_not(None)))
        periods=session.scalars(select(MesResourceCalendarPeriod)).all()
        calendar.valid_to=date(2026,11,10)
        assert day_windows(calendar,periods,date(2026,11,10))=={'work':[],'lunch':[]}
        calendar.valid_to=None
        first=next(p for p in periods if p.calendar_id==calendar.id and p.weekday_no==1 and p.period_type_code=='work')
        first.is_active=False
        assert len(day_windows(calendar,periods,date(2026,11,9))['work'])==1
