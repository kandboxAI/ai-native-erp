"""MES资源维护查询；人员名称仅供授权人员维护，不发布联系方式或AI上下文。"""
from sqlalchemy import func, or_, select
from app.auth.scope_filters import scoped_conditions
from app.modules.masterdata.models import MdParty, MdPerson
from .archive_models import MesEquipment, MesProcess
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException
from .workforce_models import MesProductionPerson, MesPersonProcess


class ResourceRepository:
    async def get(self, session, model, identifier, user, permission, lock=False):
        statement = select(model).where(model.id == identifier, *scoped_conditions(model, user, permission))
        if lock: statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def page(self, session, model, query, user, permission):
        conditions = scoped_conditions(model, user, permission)
        if query.org_id: conditions.append(model.org_id == query.org_id)
        if query.is_active is not None: conditions.append(model.is_active == query.is_active)
        statement = select(model)
        if model is MesProductionPerson:
            statement = statement.add_columns(MdParty.display_name).join(MdPerson, MdPerson.party_id == model.party_id).join(MdParty, MdParty.id == model.party_id)
            conditions.extend([MdPerson.deleted_at.is_(None), MdParty.deleted_at.is_(None)])
            if query.keyword:
                conditions.append(or_(model.person_no.ilike(f"%{query.keyword}%"), MdParty.display_name.ilike(f"%{query.keyword}%")))
            if query.process_id:
                conditions.append(select(MesPersonProcess.id).where(MesPersonProcess.production_person_id == model.id,
                    MesPersonProcess.process_id == query.process_id, MesPersonProcess.is_active.is_(True),
                    MesPersonProcess.deleted_at.is_(None), MesPersonProcess.valid_from <= func.now(),
                    or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to > func.now())).exists())
        elif query.keyword:
            conditions.append(model.calendar_name.ilike(f"%{query.keyword}%"))
        statement = statement.where(*conditions)
        count = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        result = await session.execute(statement.order_by(model.updated_at.desc(), model.id).offset((query.page - 1) * query.page_size).limit(query.page_size))
        return (result.all() if model is MesProductionPerson else result.scalars().all()), count

    async def qualifications(self, session, person, user, permission):
        return (await session.execute(select(MesPersonProcess, MesProcess.process_name).join(MesProcess,
            (MesProcess.id == MesPersonProcess.process_id) & (MesProcess.org_id == person.org_id))
            .where(MesPersonProcess.production_person_id == person.id,
                *scoped_conditions(MesPersonProcess, user, permission), MesProcess.deleted_at.is_(None))
            .order_by(MesProcess.process_name, MesPersonProcess.valid_from.desc()))).all()

    async def qualification_overlap(self, session, person, body, exclude=None):
        return (await session.execute(select(MesPersonProcess.id).where(
            MesPersonProcess.production_person_id == person.id, MesPersonProcess.process_id == body.process_id,
            MesPersonProcess.deleted_at.is_(None), MesPersonProcess.is_active.is_(True),
            MesPersonProcess.id != exclude if exclude else True,
            or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to > body.valid_from),
            MesPersonProcess.valid_from < body.valid_to if body.valid_to else True))).first() is not None

    async def calendar_overlap(self, session, body, exclude=None):
        model = MesResourceCalendar
        return (await session.execute(select(model.id).where(model.org_id == body.org_id, model.deleted_at.is_(None),
            model.production_person_id == body.production_person_id if body.production_person_id else model.equipment_id == body.equipment_id,
            model.id != exclude if exclude else True, or_(model.valid_to.is_(None), model.valid_to > body.valid_from),
            model.valid_from < body.valid_to if body.valid_to else True))).first() is not None

    async def calendar_children(self, session, calendar, user, permission):
        result = []
        for model in (MesResourceCalendarPeriod, MesResourceCalendarException):
            result.append((await session.execute(select(model).where(model.calendar_id == calendar.id,
                model.org_id == calendar.org_id, *scoped_conditions(model, user, permission)).order_by(model.id))).scalars().all())
        return result

    async def calendar_child_counts(self, session, calendar):
        result = []
        for model in (MesResourceCalendarPeriod, MesResourceCalendarException):
            result.append((await session.execute(select(func.count()).select_from(model).where(model.calendar_id == calendar.id,
                model.org_id == calendar.org_id, model.deleted_at.is_(None)))).scalar_one())
        return result

    async def name(self, session, person):
        return (await session.execute(select(MdParty.display_name).where(MdParty.id == person.party_id,
            MdParty.deleted_at.is_(None)))).scalar_one_or_none()

    async def resource_options(self, session, org_id, user, permission):
        people = (await session.execute(select(MesProductionPerson, MdParty.display_name).join(MdParty, MdParty.id == MesProductionPerson.party_id)
            .where(MesProductionPerson.org_id == org_id, MesProductionPerson.is_active.is_(True), MdParty.deleted_at.is_(None),
                MdParty.is_active.is_(True), *scoped_conditions(MesProductionPerson, user, permission)).order_by(MesProductionPerson.person_no))).all()
        equipment = (await session.execute(select(MesEquipment).where(MesEquipment.org_id == org_id, MesEquipment.is_active.is_(True),
            *scoped_conditions(MesEquipment, user, permission)).order_by(MesEquipment.equipment_no))).scalars().all()
        return people, equipment

    async def process_options(self, session, org_id, keyword, user, permission):
        condition = scoped_conditions(MesProcess, user, permission)
        condition.extend([MesProcess.org_id == org_id, MesProcess.is_active.is_(True)])
        if keyword: condition.append(or_(MesProcess.process_name.ilike(f"%{keyword}%"), MesProcess.process_no.ilike(f"%{keyword}%")))
        return (await session.execute(select(MesProcess.id, MesProcess.process_name, MesProcess.process_no)
            .where(*condition).order_by(MesProcess.process_no).limit(50))).all()

    def add(self, session, row): session.add(row)


repository = ResourceRepository()
