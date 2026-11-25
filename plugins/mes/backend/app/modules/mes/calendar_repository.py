"""资源日历数据访问；仅处理调用方排程范围内的资源，不写人员/设备主档。"""
from sqlalchemy import select, text
from app.auth.scope_filters import scoped_conditions
from app.modules.masterdata.models import MdPerson, MdParty
from .archive_models import MesEquipment
from .workforce_models import MesProductionPerson
from .external_import_models import MesExternalImportRow
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod


class CalendarRepository:
    async def missing(self, session):
        columns = set((await session.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all())
        return [f"{model.__tablename__}.{c.name}" for model in (MesResourceCalendar, MesResourceCalendarPeriod)
            for c in model.__table__.columns if (model.__tablename__, c.name) not in columns]

    async def imported_resources(self, session, user, org_id):
        # 人员跨域契约仅检查MES身份对应自然人的有效性，不读取姓名或联系方式。
        people = (await session.execute(select(MesProductionPerson.id)
            .join(MdPerson, (MdPerson.party_id == MesProductionPerson.party_id) & MdPerson.deleted_at.is_(None))
            .join(MdParty, (MdParty.id == MdPerson.party_id) & MdParty.deleted_at.is_(None) & MdParty.is_active.is_(True))
            .where(MesProductionPerson.org_id == org_id, MesProductionPerson.is_active.is_(True),
                *scoped_conditions(MesProductionPerson, user, "mes:schedule:manage"),
                select(MesExternalImportRow.id).where(MesExternalImportRow.production_person_id == MesProductionPerson.id,
                    MesExternalImportRow.org_id == org_id, MesExternalImportRow.record_type_key == "person_roster",
                    MesExternalImportRow.source_system_key == "customer_roster").exists()))).scalars().all()
        equipment = (await session.execute(select(MesEquipment.id).where(MesEquipment.org_id == org_id,
            MesEquipment.is_active.is_(True), *scoped_conditions(MesEquipment, user, "mes:schedule:manage"),
            select(MesExternalImportRow.id).where(MesExternalImportRow.equipment_id == MesEquipment.id,
                MesExternalImportRow.org_id == org_id, MesExternalImportRow.record_type_key == "equipment_archive",
                MesExternalImportRow.source_system_key == "gendanbao").exists()))).scalars().all()
        return [("person", identifier) for identifier in people] + [("equipment", identifier) for identifier in equipment]

    async def calendars(self, session, user, org_id):
        return (await session.execute(select(MesResourceCalendar).where(MesResourceCalendar.org_id == org_id,
            *scoped_conditions(MesResourceCalendar, user, "mes:schedule:manage")))).scalars().all()

    async def periods(self, session, calendars, org_id):
        if not calendars:
            return []
        return (await session.execute(select(MesResourceCalendarPeriod).where(MesResourceCalendarPeriod.calendar_id.in_(calendars),
            MesResourceCalendarPeriod.org_id == org_id, MesResourceCalendarPeriod.deleted_at.is_(None)))).scalars().all()

    def add(self, session, row): session.add(row)


repository = CalendarRepository()
