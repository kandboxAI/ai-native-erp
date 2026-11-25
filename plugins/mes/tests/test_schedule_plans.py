"""正式方案保存及原子应用；纯内存数据，真实CP-SAT子进程，不连接业务库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import UUID,uuid4
from sqlalchemy import DateTime, select, func
from sqlalchemy.orm.attributes import set_committed_value
import pytest
from app.core.exceptions import AppException
from app.modules.masterdata.models import MdParty, MdPerson
from app.modules.mes import schedule_plan_service as module
from app.modules.mes.schedule_plan_service import service
from app.modules.mes.schedule_plan_schemas import SchedulePlanCreate, SchedulePlanCommand
from app.modules.mes.schedule_trial_schemas import TrialScope
from app.modules.mes.schedule_trial_planning import snapshot_key
from app.modules.mes.archive_models import MesProcess,MesEquipment,MesEquipmentProcess
from app.modules.mes.workforce_models import MesProductionPerson,MesPersonProcess
from app.modules.mes.calendar_models import MesResourceCalendar,MesResourceCalendarPeriod
from app.modules.mes.calendar_service import WorkWeek
from app.modules.mes.schedule_models import MesSchedulePlan,MesSchedulePlanSegment,MesOperationProductionPhase,MesWorkOrderFirstArticle
from test_schedule_trial_repository import store

START=datetime(2030,11,11,0,tzinfo=UTC)


@pytest.fixture
def state(store,monkeypatch):
    actor=store.actor
    actor.enabled_plugin_keys=["mes"]
    for key in (module.LIST,module.MANAGE,module.APPLY):
        if key not in actor.permissions:actor.permissions.append(key)
        actor.permission_scopes[key]="organization"
    class Adapter:
        bind=store.engine
        class Result:
            def __init__(self,value):self.value=value
            def normalize(self,value):
                if isinstance(value,datetime) and value.tzinfo is None:return value.replace(tzinfo=UTC)
                if isinstance(value,list):return [self.normalize(v) for v in value]
                if hasattr(value,"__table__"):
                    for c in value.__table__.columns:
                        v=getattr(value,c.name,None)
                        if isinstance(c.type,DateTime) and isinstance(v,datetime) and v.tzinfo is None:set_committed_value(value,c.name,v.replace(tzinfo=UTC))
                    return value
                if isinstance(value,tuple) or hasattr(value,"_mapping"):
                    values=tuple(self.normalize(v) for v in value)
                    return value if all(a is b for a,b in zip(values,value)) else values
                return value
            def scalars(self):return type(self)(self.value.scalars())
            def __getattr__(self,name):
                attr=getattr(self.value,name)
                if name in {"all","first","one","one_or_none","scalar","scalar_one","scalar_one_or_none","fetchall"}:
                    return lambda *args,**kwargs:self.normalize(attr(*args,**kwargs))
                return attr
        async def execute(self,statement):return self.Result(store.session.execute(statement))
        async def exec(self,statement):return await self.execute(statement)
        def add(self,row):store.session.add(row)
        async def flush(self):store.session.flush()
        async def commit(self):store.session.commit()
    adapter=Adapter()
    @asynccontextmanager
    async def context():
        try:yield adapter
        except BaseException:store.session.rollback();raise
    async def lock(*args):pass
    monkeypatch.setattr(module,"get_session_context",context)
    monkeypatch.setattr(module.archive_repository,"lock_organization",lock)
    monkeypatch.setattr(module.repository,"lock_resources",lock)  # SQLite无PG advisory lock；保留全部查询与事务检查。
    monkeypatch.setattr(module,"utc_now",lambda:START)
    monkeypatch.setattr("app.modules.mes.schedule_trial_service.utc_now",lambda:START)
    original=module.sources.snapshot
    async def snapshot(*args,**kwargs):
        data=await original(*args,**kwargs)
        # SQLite不保留时区；测试适配恢复PG接口承诺，生产不作隐式时区推断。
        for values in data.values():
            if not isinstance(values,list):continue
            for row in values:
                if not hasattr(row,"__table__"):continue
                for column in row.__table__.columns:
                    value=getattr(row,column.name,None)
                    if isinstance(column.type,DateTime) and isinstance(value,datetime) and value.tzinfo is None:
                        set_committed_value(row,column.name,value.replace(tzinfo=UTC))
        for key in ("reservations","phase_reservations","absences"):
            data[key]=[tuple(v.replace(tzinfo=UTC) if isinstance(v,datetime) and v.tzinfo is None else v for v in row) for row in data.get(key,[])]
        return data
    monkeypatch.setattr(module.sources,"snapshot",snapshot)
    party=MdParty(party_type_code="person",display_name="离线排程人员")
    store.session.add(party);store.session.flush()
    store.session.add(MdPerson(party_id=party.id,full_name="离线排程人员"))
    store.session.flush()
    person=MesProductionPerson(org_id=store.org,party_id=party.id,person_no="TEST",created_by=actor.user_id)
    process=MesProcess(org_id=store.org,process_no="P",process_name="加工",execution_kind_code="machine",is_equipment_required=True,created_by=actor.user_id)
    qc=MesProcess(org_id=store.org,process_no="QC",process_name="质检",execution_kind_code="inspection",is_equipment_required=False,created_by=actor.user_id)
    equipment=MesEquipment(org_id=store.org,equipment_no="E1",equipment_name="测试机",created_by=actor.user_id)
    store.session.add_all([person,process,qc,equipment]);store.session.flush()
    store.session.add(MesEquipmentProcess(org_id=store.org,equipment_id=equipment.id,process_id=process.id,created_by=actor.user_id))
    for proc in (process,qc):store.session.add(MesPersonProcess(org_id=store.org,production_person_id=person.id,process_id=proc.id,valid_from=START,created_by=actor.user_id))
    for kind,identifier in (("person",person.id),("equipment",equipment.id)):
        c=MesResourceCalendar(org_id=store.org,production_person_id=identifier if kind=="person" else None,equipment_id=identifier if kind=="equipment" else None,
            calendar_name=kind,timezone_name="Asia/Shanghai",valid_from=date(2030,11,11),created_by=actor.user_id)
        store.session.add(c);store.session.flush()
        for day,key,start,end in WorkWeek().periods(kind):store.session.add(MesResourceCalendarPeriod(org_id=store.org,calendar_id=c.id,
            weekday_no=day,period_type_code=key,start_minute_of_day=start,end_minute_of_day=end,created_by=actor.user_id))
    store.task.process_id=process.id;store.task.standard_minutes_per_unit=Decimal(10)
    store.work.due_at=START+timedelta(days=1)
    store.session.commit()
    scope=TrialScope(org_id=store.org,work_order_ids=[store.work.id],start_at=START+timedelta(hours=1),end_at=START+timedelta(days=2))
    snap=asyncio.run(module.sources.snapshot(adapter,scope,actor))
    body=SchedulePlanCreate(**scope.model_dump(),snapshot_key=snapshot_key(snap),plan_name="离线完整方案",
        operation_rules=[dict(operation_id=store.task.id,version_no=store.task.version_no,kind_key="machine",setup_minutes=0,load_minutes=1,unload_minutes=1,
            supervision_key="two_machines",is_lunch_auto_allowed=True,is_timing_confirmed=True)],
        order_rules=[dict(work_order_id=store.work.id,version_no=store.work.version_no,ready_at=scope.start_at,is_readiness_confirmed=True)],
        inspection=dict(process_id=qc.id,is_equipment_required=False,minutes_per_piece=1),is_regular_calendar_confirmed=True,time_limit_seconds=1,
        readiness=[dict(work_order_id=store.work.id,readiness_kind_code=key,expected_at=scope.start_at,is_confirmed=False) for key in ("material","drawing","program","tool")])
    return NS(**{**vars(store),"adapter":adapter,"body":body,"person":person,"equipment":equipment})


def test_formal_compute_persists_relational_segments_without_changing_production(state):
    result=asyncio.run(service.create(state.body,state.actor))
    plan=state.session.get(MesSchedulePlan,UUID(result["plan_id"]))
    assert plan.status_code=="ready" and result["segments"]
    assert state.task.planned_start_at is None and state.task.equipment_id is None
    assert state.session.scalar(select(func.count()).select_from(MesSchedulePlanSegment))>0
    assert state.session.scalar(select(func.count()).select_from(MesOperationProductionPhase))==0


def test_manual_plan_cannot_replace_applied_formal_stage_schedule(state):
    from app.core.exceptions import AppException
    from app.modules.mes.schedule_execution import guard_manual_schedule
    from app.modules.mes.schemas import ScheduleOperation
    result=asyncio.run(service.create(state.body,state.actor))
    asyncio.run(service.apply(UUID(result["plan_id"]),SchedulePlanCommand(version_no=result["plan_version_no"],note="确认自动方案"),state.actor))
    change=ScheduleOperation(operation_id=state.task.id,version_no=state.task.version_no,planned_start_at=START+timedelta(hours=3),planned_end_at=START+timedelta(hours=4))
    with pytest.raises(AppException,match="阶段安排"):
        asyncio.run(guard_manual_schedule(state.adapter,[(state.task,state.work)],{state.task.id:change}))


def test_apply_rechecks_and_creates_separate_first_and_remaining_phases(state):
    result=asyncio.run(service.create(state.body,state.actor))
    identifier=__import__('uuid').UUID(result["plan_id"])
    command=SchedulePlanCommand(version_no=result["plan_version_no"],note="测试确认")
    applied=asyncio.run(service.apply(identifier,command,state.actor))
    assert applied["status_code"]=="applied"
    assert state.task.equipment_id==state.equipment.id and state.task.planned_start_at is not None
    phases=state.session.scalars(select(MesOperationProductionPhase)).all()
    assert {(p.production_phase_code,p.planned_quantity) for p in phases}=={("first",Decimal(1)),("remaining",Decimal(1))}
    assert state.session.scalar(select(MesWorkOrderFirstArticle)).status_code=="pending"
    again=asyncio.run(service.apply(identifier,command,state.actor))
    assert again["status_code"]=="applied" and state.session.scalar(select(func.count()).select_from(MesOperationProductionPhase))==2


def test_changed_resource_invalidates_plan_without_partial_application(state):
    result=asyncio.run(service.create(state.body,state.actor))
    state.equipment.is_active=False;state.equipment.version_no+=1;state.session.commit()
    identifier=__import__('uuid').UUID(result["plan_id"])
    with pytest.raises(AppException):asyncio.run(service.apply(identifier,SchedulePlanCommand(version_no=result["plan_version_no"],note="过期测试"),state.actor))
    assert state.session.get(MesSchedulePlan,identifier).status_code=="invalid"
    assert state.task.planned_start_at is None and state.session.scalar(select(func.count()).select_from(MesOperationProductionPhase))==0
