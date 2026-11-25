"""生产人员与资格的数据访问；自然人写入仅经主数据公开 Service。"""
from sqlalchemy import select, text, or_
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.modules.masterdata.models import MdPerson, MdParty
from .archive_models import MesProcess
from .external_import_models import MesExternalImportRow
from .workforce_models import MesProductionPerson, MesPersonProcess


class WorkforceImportRepository:
    async def missing(self, session):
        columns = set((await session.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all())
        required = [(model.__tablename__, c.name) for model in (MesProductionPerson, MesPersonProcess) for c in model.__table__.columns]
        required.append((MesExternalImportRow.__tablename__, "production_person_id"))
        return [f"{table}.{column}" for table,column in required if (table,column) not in columns]

    async def sources(self, session, user, org_id):
        return (await session.execute(select(MesExternalImportRow).where(MesExternalImportRow.org_id == org_id,
            MesExternalImportRow.source_system_key == "customer_roster", MesExternalImportRow.record_type_key == "person_roster",
            *scoped_conditions(MesExternalImportRow, user, "mes:schedule:manage")))).scalars().all()

    async def people(self, session, user, org_id):
        return (await session.execute(select(MesProductionPerson).where(MesProductionPerson.org_id == org_id,
            *scoped_conditions(MesProductionPerson, user, "mes:schedule:manage")))).scalars().all()

    async def processes(self, session, user, org_id):
        return (await session.execute(select(MesProcess).where(MesProcess.org_id == org_id,
            MesProcess.is_active.is_(True), *scoped_conditions(MesProcess, user, "mes:archive:process:manage")))).scalars().all()

    async def add_qualification(self, session, person, process_id, since, user_id):
        overlap = (await session.execute(select(MesPersonProcess.id).where(
            MesPersonProcess.org_id == person.org_id, MesPersonProcess.production_person_id == person.id,
            MesPersonProcess.process_id == process_id, MesPersonProcess.is_active.is_(True), MesPersonProcess.deleted_at.is_(None),
            or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to > since)).limit(1))).first()
        if overlap:
            raise AppException("该人员已有重叠的有效工艺资格，未重复登记", 409)
        session.add(MesPersonProcess(org_id=person.org_id, production_person_id=person.id, process_id=process_id,
            valid_from=since, created_at=since, created_by=user_id, updated_by=user_id))

    async def qualified(self, session, org_id, process_id, starts_at, ends_at, user):
        """排程资料读取契约：只返回已授权 MES 人员身份及自然人 ID。

        跨域只检查该身份对应的自然人有效状态，不读取姓名、联系方式或其他个人信息；
        工艺必须仍启用，资格须覆盖整个计划阶段。
        """
        return (await session.execute(select(MesProductionPerson.id, MesProductionPerson.party_id, MesProductionPerson.person_no)
            .join(MdPerson, (MdPerson.party_id == MesProductionPerson.party_id) & MdPerson.deleted_at.is_(None))
            .join(MdParty, (MdParty.id == MdPerson.party_id) & MdParty.deleted_at.is_(None) & MdParty.is_active.is_(True))
            .join(MesPersonProcess, (MesPersonProcess.production_person_id == MesProductionPerson.id)
                & (MesPersonProcess.org_id == MesProductionPerson.org_id))
            .join(MesProcess, (MesProcess.id == MesPersonProcess.process_id) & (MesProcess.org_id == MesPersonProcess.org_id)
                & MesProcess.deleted_at.is_(None) & MesProcess.is_active.is_(True))
            .where(MesProductionPerson.org_id == org_id, MesProductionPerson.is_active.is_(True),
                *scoped_conditions(MesProductionPerson, user, "mes:schedule:manage"),
                MesPersonProcess.process_id == process_id, MesPersonProcess.deleted_at.is_(None), MesPersonProcess.is_active.is_(True),
                MesPersonProcess.valid_from <= starts_at,
                or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to >= ends_at)).distinct())).mappings().all()

    def add(self, session, row): session.add(row)


repository = WorkforceImportRepository()
