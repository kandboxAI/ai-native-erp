from datetime import datetime, time
from zoneinfo import ZoneInfo
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.masterdata import service as masterdata
from .archive_models import MesEquipment, MesProcess
from .archive_repository import archive_repository
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException
from .workforce_models import MesProductionPerson, MesPersonProcess
from .schedule_resource_repository import repository

LIST, MANAGE = "mes:schedule_resource:list", "mes:schedule_resource:manage"


def require(user, write=False):
    permission = MANAGE if write or LIST not in user.permissions else LIST
    if "mes" not in user.enabled_plugin_keys or permission not in user.permissions:
        raise AppException("缺少排程资源维护权限或MES未启用", 403)
    return permission


def data(row):
    return row.model_dump(exclude={"flex_form", "deleted_at", "deleted_by", "description"})


def touch(row, user, version=None):
    if version is not None and row.version_no != version:
        raise AppException("资料已被修改，请重新读取后再保存", 409)
    row.version_no += 1
    row.updated_at, row.updated_by = utc_now(), user.user_id


def within_calendar(start, end, valid_from, valid_to, timezone_name):
    zone = ZoneInfo(timezone_name)
    return start >= datetime.combine(valid_from, time.min, zone) and (
        not valid_to or end <= datetime.combine(valid_to, time.min, zone))


class ResourceService:
    async def record(self, session, model, identifier, user, write=False):
        permission = require(user, write)
        row = await repository.get(session, model, identifier, user, permission, lock=write)
        if row is None: raise AppException("资源不存在或无权访问", 404)
        return row

    async def page(self, kind, query, user):
        permission = require(user)
        model = MesProductionPerson if kind == "people" else MesResourceCalendar
        async with get_session_context() as session:
            rows, total = await repository.page(session, model, query, user, permission)
            items = [dict(**data(row), full_name=name) for row, name in rows] if kind == "people" else [data(row) for row in rows]
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)

    async def options(self, org_id, user):
        permission = require(user)
        async with get_session_context() as session:
            people, equipment = await repository.resource_options(session, org_id, user, permission)
            return dict(people=[dict(id=p.id, label=f"{name} · {p.person_no}", version_no=p.version_no) for p, name in people],
                equipment=[dict(id=e.id, label=f"{e.equipment_no} · {e.equipment_name}", version_no=e.version_no) for e in equipment])

    async def detail(self, kind, identifier, user):
        permission = require(user)
        async with get_session_context() as session:
            if kind == "people":
                person = await self.record(session, MesProductionPerson, identifier, user)
                skills = await repository.qualifications(session, person, user, permission)
                return dict(**data(person), full_name=await repository.name(session, person),
                    qualifications=[dict(**data(q), process_name=name) for q, name in skills])
            calendar = await self.record(session, MesResourceCalendar, identifier, user)
            periods, exceptions = await repository.calendar_children(session, calendar, user, permission)
            return dict(**data(calendar), periods=[data(p) for p in periods], exceptions=[data(e) for e in exceptions])

    async def save_person(self, body, user, identifier=None):
        permission = require(user, True)
        resolve_write_org_id(user, body.org_id, permission)
        async with get_session_context() as session:
            await archive_repository.lock_organization(session, body.org_id)
            if identifier:
                person = await self.record(session, MesProductionPerson, identifier, user, True)
                if person.org_id != body.org_id or body.version_no is None:
                    raise AppException("不能更换人员所属组织；请携带最新版本", 409)
                if body.full_name and body.full_name != await repository.name(session, person):
                    raise AppException("姓名由公共人员主数据维护，此处仅维护生产身份和技能", 409)
                touch(person, user, body.version_no)
            else:
                if not body.full_name: raise AppException("请输入人员姓名", 422)
                if await masterdata.existing_person_names(session, names=[body.full_name]):
                    raise AppException("租户内存在同名自然人，请由管理员核对并关联现有身份，不能自动重复建档", 409)
                master = await masterdata.create_person(session, full_name=body.full_name, mobile=None, actor_id=user.user_id)
                person = MesProductionPerson(org_id=body.org_id, party_id=master.party_id, person_no=body.person_no,
                    created_by=user.user_id, updated_by=user.user_id)
                repository.add(session, person)
            person.person_no, person.job_title_snapshot, person.is_active = body.person_no, body.job_title_snapshot, body.is_active
            await session.flush()
            result = data(person)
            await session.commit()
            return result

    async def save_qualification(self, person_id, body, user, identifier=None):
        permission = require(user, True)
        resolve_write_org_id(user, body.org_id, permission)
        async with get_session_context() as session:
            await archive_repository.lock_organization(session, body.org_id)
            person = await self.record(session, MesProductionPerson, person_id, user, True)
            process = await repository.get(session, MesProcess, body.process_id, user, permission)
            if person.org_id != body.org_id or not process or process.org_id != body.org_id or not process.is_active:
                raise AppException("人员与工艺必须属于同一授权组织且工艺已启用", 409)
            if body.is_active and await repository.qualification_overlap(session, person, body, identifier):
                raise AppException("同一人员和工艺的有效资格时段不能重叠", 409)
            if identifier:
                row = await self.record(session, MesPersonProcess, identifier, user, True)
                if row.production_person_id != person_id or row.process_id != body.process_id or body.version_no is None:
                    raise AppException("资格归属或版本不正确", 409)
                touch(row, user, body.version_no)
            else:
                row = MesPersonProcess(org_id=body.org_id, production_person_id=person_id, process_id=body.process_id,
                    valid_from=body.valid_from, created_by=user.user_id, updated_by=user.user_id)
                repository.add(session, row)
            for name in ("process_id", "valid_from", "valid_to", "is_active"): setattr(row, name, getattr(body, name))
            touch(person, user)
            await session.flush()
            result = data(row)
            await session.commit()
            return result

    async def save_calendar_in_session(self, session, body, user, identifier=None):
        permission = require(user, True)
        resolve_write_org_id(user, body.org_id, permission)
        await archive_repository.lock_organization(session, body.org_id)
        model, resource_id = (MesProductionPerson, body.production_person_id) if body.production_person_id else (MesEquipment, body.equipment_id)
        resource = await repository.get(session, model, resource_id, user, permission)
        if not resource or resource.org_id != body.org_id or not resource.is_active:
            raise AppException("请选择同组织已启用的授权人员或设备", 409)
        if await repository.calendar_overlap(session, body, identifier):
            raise AppException("该资源已存在有效日期重叠的日历，请修改现有日历或调整有效期", 409)
        if identifier:
            row = await self.record(session, MesResourceCalendar, identifier, user, True)
            if row.org_id != body.org_id or row.production_person_id != body.production_person_id or row.equipment_id != body.equipment_id or body.version_no is None:
                raise AppException("不能更换日历资源归属；请携带最新版本", 409)
            touch(row, user, body.version_no)
            periods, exceptions = await repository.calendar_children(session, row, user, permission)
            if [len(periods), len(exceptions)] != await repository.calendar_child_counts(session, row):
                raise AppException("日历包含当前无权维护的时段或例外，不能覆盖部分资料", 403)
            for exception in exceptions:
                if exception.is_active and not within_calendar(exception.start_at, exception.end_at, body.valid_from, body.valid_to, body.timezone_name):
                    raise AppException("日历有效期须包含已登记的例外，请先调整例外", 409)
            for period in periods:
                period.deleted_at, period.deleted_by = utc_now(), user.user_id
            await session.flush()
        else:
            row = MesResourceCalendar(**body.model_dump(exclude={"periods", "version_no"}), created_by=user.user_id, updated_by=user.user_id)
            repository.add(session, row)
            await session.flush()
        for name in ("calendar_name", "timezone_name", "valid_from", "valid_to", "is_active"): setattr(row, name, getattr(body, name))
        for p in body.periods:
            repository.add(session, MesResourceCalendarPeriod(org_id=row.org_id, calendar_id=row.id,
                **p.model_dump(), created_by=user.user_id, updated_by=user.user_id))
        await session.flush()
        return data(row)

    async def save_calendar(self, body, user, identifier=None):
        async with get_session_context() as session:
            result = await self.save_calendar_in_session(session, body, user, identifier)
            await session.commit()
            return result

    async def batch_calendars(self, body, user):
        async with get_session_context() as session:
            result = []
            for entry in body.calendars:
                result.append(await self.save_calendar_in_session(session, entry, user))
            await session.commit()
            return result

    async def save_exception(self, calendar_id, body, user, identifier=None):
        permission = require(user, True)
        resolve_write_org_id(user, body.org_id, permission)
        async with get_session_context() as session:
            await archive_repository.lock_organization(session, body.org_id)
            calendar = await self.record(session, MesResourceCalendar, calendar_id, user, True)
            start = body.start_at.astimezone(ZoneInfo(calendar.timezone_name))
            end = body.end_at.astimezone(ZoneInfo(calendar.timezone_name))
            if calendar.org_id != body.org_id or not within_calendar(start, end, calendar.valid_from, calendar.valid_to, calendar.timezone_name):
                raise AppException("例外须属于该日历组织并位于其有效期内", 409)
            if identifier:
                row = await self.record(session, MesResourceCalendarException, identifier, user, True)
                if row.calendar_id != calendar_id or body.version_no is None: raise AppException("例外归属或版本不正确", 409)
                touch(row, user, body.version_no)
                for name in ("start_at", "end_at", "exception_type_code", "reason", "is_active"): setattr(row, name, getattr(body, name))
            else:
                row = MesResourceCalendarException(**body.model_dump(exclude={"version_no"}), calendar_id=calendar_id,
                    created_by=user.user_id, updated_by=user.user_id)
                repository.add(session, row)
            touch(calendar, user)
            await session.flush()
            result = data(row)
            await session.commit()
            return result


service = ResourceService()
