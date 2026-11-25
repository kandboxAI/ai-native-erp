"""人员与有效期工艺资格导入；真实内存事务，不创建登录账号、不访问业务库。"""
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, select, func, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.masterdata.models import MdParty, MdPerson, MdPersonContact
from app.modules.masterdata import service as masterdata
from app.modules.mes.archive_models import MesProcess
from app.modules.mes.archive_repository import archive_repository
from app.modules.mes.external_import_models import MesExternalImportRow
from app.modules.mes.workforce_models import MesProductionPerson, MesPersonProcess
from app.modules.mes.workforce_import import read_roster, service, repository
from test_quotations import run


class Adapter:
    def __init__(self, session): self.session = session
    def add(self, row): self.session.add(row)
    async def execute(self, statement): return self.session.execute(statement)
    async def flush(self): self.session.flush()


@pytest.fixture
def state(monkeypatch):
    models = (MdParty, MdPerson, MdPersonContact, MesProductionPerson, MesPersonProcess, MesProcess, MesExternalImportRow)
    metadata = MetaData()
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit('.',1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external: Table(name,metadata,Column('id',Uuid,primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type,JSONB): column.type=JSON()
        for index in table.indexes:
            where = index.dialect_options['postgresql'].get('where')
            if where is not None: index.dialect_options['sqlite']['where'] = where
    engine = create_engine('sqlite:///:memory:')
    @event.listens_for(engine,'connect')
    def foreign_keys(connection,_): connection.execute('PRAGMA foreign_keys=ON')
    metadata.create_all(engine)
    org_id,user_id = uuid4(),uuid4()
    keys = ['mes:schedule:manage','mes:archive:process:manage']
    actor=NS(org_id=org_id,user_id=user_id,permissions=keys,permission_scopes={key:'organization' for key in keys},
        org_access_mode_code='selected',org_ids=[],department_id=None,enabled_plugin_keys=['mes'])
    with engine.begin() as connection:
        connection.execute(metadata.tables['sys_org'].insert().values(id=org_id))
        connection.execute(metadata.tables['sys_user'].insert().values(id=user_id))
    with Session(engine) as session:
        session.add_all([MesProcess(org_id=org_id,process_no=f'GY{index}',process_name=name) for index,name in enumerate(['CNC2','CNC4','CNC5'],1)])
        session.commit()
    async def noop(*args): pass
    async def ready(*args): return []
    monkeypatch.setattr(archive_repository,'lock_organization',noop)
    monkeypatch.setattr(repository,'missing',ready)
    yield NS(engine=engine,actor=actor,org_id=org_id)
    engine.dispose()


def data(tmp_path):
    photo = tmp_path/'roster.jpg'; photo.write_bytes(b'local test source')
    rows=[dict(source_row_no=1,full_name='测试甲',job_title='CNC技术员',axis_capabilities=[3,4,5]),
          dict(source_row_no=2,full_name='测试乙',job_title='CNC学徒',axis_capabilities=[3]),
          dict(source_row_no=3,full_name='测试丙',job_title='数控技术员',axis_capabilities=[])]
    manifest=dict(format_version=1,source_photo_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(),
        confirmed_axis_process_names={'3':'CNC2','4':'CNC4','5':'CNC5'},people=rows)
    path=tmp_path/'roster.json'; path.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    return read_roster(path,photo),path,photo


def test_real_people_qualification_counts_idempotency_and_no_accounts(state,tmp_path):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        result=run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.commit()
        assert result['new_people']==3 and result['new_qualifications']==4 and result['new_login_accounts']==0
        for model,count in [(MdParty,3),(MdPerson,3),(MdPersonContact,0),(MesProductionPerson,3),(MesPersonProcess,4),(MesExternalImportRow,3)]:
            assert session.scalar(select(func.count()).select_from(model))==count
        assert all(person.user_id is None for person in session.scalars(select(MdPerson)))
        assert run(service.apply(Adapter(session),rows,state.actor,state.org_id))['new_people']==0
        source=session.scalar(select(MesExternalImportRow))
        assert source.source_system_key=='customer_roster' and source.production_person_id is not None
        assert source.source_values_snapshot['axis_capabilities']==[3,4,5]


def test_qualification_covers_entire_stage_and_blank_role_gives_no_skill(state,tmp_path):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.commit()
        first=session.scalar(select(MesPersonProcess).order_by(MesPersonProcess.valid_from))
        start=first.valid_from+timedelta(hours=1); end=start+timedelta(hours=2)
        process_id=session.scalar(select(MesProcess.id).where(MesProcess.process_name=='CNC2'))
        assert len(run(repository.qualified(Adapter(session),state.org_id,process_id,start,end,state.actor)))==2
        qualification=session.scalar(select(MesPersonProcess).where(MesPersonProcess.process_id==process_id))
        qualification.valid_to=start+timedelta(hours=1);session.commit()
        assert len(run(repository.qualified(Adapter(session),state.org_id,process_id,start,end,state.actor)))==1
        assert len(run(repository.qualified(Adapter(session),state.org_id,process_id,start,qualification.valid_to,state.actor)))==2
        qualification.is_active=False;session.commit()
        assert len(run(repository.qualified(Adapter(session),state.org_id,process_id,start,qualification.valid_to,state.actor)))==1


@pytest.mark.parametrize('failure',['missing_process','ambiguous_process','inactive_process','scope','duplicate_person'])
def test_invalid_source_or_scope_rolls_back_before_writing_people(state,tmp_path,failure):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        if failure=='missing_process': session.scalar(select(MesProcess)).process_name='其他'
        if failure=='inactive_process': session.scalar(select(MesProcess)).is_active=False
        if failure=='ambiguous_process': session.add(MesProcess(org_id=state.org_id,process_no='DUP',process_name='CNC2'))
        if failure=='duplicate_person': run(masterdata.create_person(Adapter(session),full_name='测试甲',mobile=None,actor_id=state.actor.user_id))
        session.commit()
        original=session.scalar(select(func.count()).select_from(MdPerson))
        with pytest.raises(AppException):
            run(service.apply(Adapter(session),rows,state.actor,uuid4() if failure=='scope' else state.org_id))
        session.rollback()
        assert session.scalar(select(func.count()).select_from(MdPerson))==original
        assert session.scalar(select(func.count()).select_from(MesProductionPerson))==0


def test_caller_rollback_and_source_change_detection(state,tmp_path):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.rollback()
        assert session.scalar(select(func.count()).select_from(MdPerson))==0
        run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.commit()
        rows[0].values['job_title']='新职务'
        with pytest.raises(AppException): run(service.apply(Adapter(session),rows,state.actor,state.org_id))


def test_qualification_overlap_refused_and_timezone_models(state,tmp_path):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        result=run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.commit()
        row=session.scalar(select(MesPersonProcess)); person=session.get(MesProductionPerson,row.production_person_id)
        with pytest.raises(AppException): run(repository.add_qualification(Adapter(session),person,row.process_id,result['qualifications_valid_from'],state.actor.user_id))
        assert MesPersonProcess.__table__.c.valid_from.type.timezone and MesPersonProcess.__table__.c.valid_to.type.timezone


def test_inactive_person_or_process_not_eligible(state,tmp_path):
    rows,*_=data(tmp_path)
    with Session(state.engine) as session:
        result=run(service.apply(Adapter(session),rows,state.actor,state.org_id));session.commit()
        process=session.scalar(select(MesProcess).where(MesProcess.process_name=='CNC2'))
        start=result['qualifications_valid_from']+timedelta(hours=1);end=start+timedelta(hours=1)
        assert len(run(repository.qualified(Adapter(session),state.org_id,process.id,start,end,state.actor)))==2
        party=session.scalar(select(MdParty).where(MdParty.display_name=='测试甲'))
        party.is_active=False;session.commit()
        assert len(run(repository.qualified(Adapter(session),state.org_id,process.id,start,end,state.actor)))==1
        process.is_active=False;session.commit()
        assert run(repository.qualified(Adapter(session),state.org_id,process.id,start,end,state.actor))==[]


def test_source_digest_and_unconfirmed_mapping_rejected(tmp_path):
    rows,path,photo=data(tmp_path)
    value=json.loads(path.read_text(encoding='utf-8'))
    del value['confirmed_axis_process_names']['3']
    path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError):read_roster(path,photo)
    photo.write_bytes(b'changed')
    with pytest.raises(ValueError,match='摘要'):read_roster(path,photo)
