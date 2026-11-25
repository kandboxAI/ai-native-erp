"""显式创建客户已确认的常规日历；不覆盖已有个性化日历，不生成排程。"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.modules.dictionary.service import ensure_builtin_definitions, service as dictionaries
from .archive_repository import archive_repository
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod
from .calendar_repository import repository
from .dictionary_specs import CALENDAR_PERIOD_DEFINITION


@dataclass(frozen=True)
class WorkWeek:
    start_minute: int = 480
    end_minute: int = 1080
    lunch_start_minute: int = 720
    lunch_end_minute: int = 810
    timezone_name: str = "Asia/Shanghai"

    def validate(self):
        ZoneInfo(self.timezone_name)
        if not 0 <= self.start_minute < self.lunch_start_minute < self.lunch_end_minute < self.end_minute <= 1440:
            raise ValueError("工作与午休时段须按开始、午休开始、午休结束、下班顺序且在一天内")

    def periods(self, kind):
        self.validate()
        if kind not in {"person", "equipment"}:
            raise ValueError("未知资源类型")
        daily = [("work", self.start_minute, self.end_minute)] if kind == "equipment" else [
            ("work", self.start_minute, self.lunch_start_minute),
            ("lunch", self.lunch_start_minute, self.lunch_end_minute),
            ("work", self.lunch_end_minute, self.end_minute)]
        return sorted((weekday, code, start, end) for weekday in range(1, 6) for code, start, end in daily)


def day_windows(calendar, periods, day):
    """展开常规日历，工作/午休分别返回；不推算节假日、加班或请假例外。"""
    result = {"work": [], "lunch": []}
    if not calendar.is_active or calendar.deleted_at or day < calendar.valid_from or (calendar.valid_to and day >= calendar.valid_to):
        return result
    zone = ZoneInfo(calendar.timezone_name)
    origin = datetime.combine(day, time.min, zone)
    chosen = sorted((p for p in periods if p.calendar_id == calendar.id and p.org_id == calendar.org_id
        and p.weekday_no == day.isoweekday() and p.is_active and not p.deleted_at), key=lambda p: p.start_minute_of_day)
    end = -1
    for p in chosen:
        if p.period_type_code not in result or not 0 <= p.start_minute_of_day < p.end_minute_of_day <= 1440 or p.start_minute_of_day < end:
            raise ValueError("资源常规日历包含未知类型、重叠或无效时段")
        result[p.period_type_code].append((origin + timedelta(minutes=p.start_minute_of_day), origin + timedelta(minutes=p.end_minute_of_day)))
        end = p.end_minute_of_day
    return result


class CalendarService:
    def authorize(self, user, org_id):
        key = "mes:schedule:manage"
        if "mes" not in user.enabled_plugin_keys or key not in user.permissions:
            raise AppException("缺少MES排程管理权限或租户未启用MES", 403)
        resolve_write_org_id(user, org_id, key)

    async def plan(self, session, user, org_id, starts_on, week):
        self.authorize(user, org_id)
        week.validate()
        resources = await repository.imported_resources(session, user, org_id)
        if not resources:
            raise AppException("当前范围内没有已导入的有效生产人员或设备", 409)
        existing = await repository.calendars(session, user, org_id)
        periods = await repository.periods(session, [c.id for c in existing], org_id)
        new = []
        for kind, identifier in resources:
            field = "production_person_id" if kind == "person" else "equipment_id"
            overlaps = [c for c in existing if getattr(c, field) == identifier and (c.valid_to is None or c.valid_to > starts_on)]
            if not overlaps:
                new.append((kind, identifier))
                continue
            calendar = overlaps[0]
            actual = [p for p in periods if p.calendar_id == calendar.id]
            signature = sorted((p.weekday_no, p.period_type_code, p.start_minute_of_day, p.end_minute_of_day) for p in actual)
            if (len(overlaps) != 1 or not calendar.is_active or calendar.valid_from > starts_on or calendar.valid_to is not None
                    or calendar.timezone_name != week.timezone_name or not all(p.is_active for p in actual) or signature != week.periods(kind)):
                raise AppException("资源已有不同、停用或有效期冲突的日历，未自动覆盖；请先人工核对", 409)
        return resources, new

    async def preview(self, session, user, org_id, starts_on, week):
        self.authorize(user, org_id)
        week.validate()
        missing = await repository.missing(session)
        resources = await repository.imported_resources(session, user, org_id)
        if missing:
            return dict(missing_columns=missing, people=sum(kind == "person" for kind, _ in resources),
                equipment=sum(kind == "equipment" for kind, _ in resources), proposed_calendars=len(resources),
                proposed_periods=sum(len(week.periods(kind)) for kind, _ in resources))
        resources, new = await self.plan(session, user, org_id, starts_on, week)
        return dict(missing_columns=[], people=sum(kind == "person" for kind, _ in resources),
            equipment=sum(kind == "equipment" for kind, _ in resources), new_calendars=len(new),
            new_periods=sum(len(week.periods(kind)) for kind, _ in new))

    async def apply(self, session, user, org_id, starts_on, week):
        self.authorize(user, org_id)
        await archive_repository.lock_organization(session, org_id)
        if await repository.missing(session):
            raise AppException("常规资源日历尚未升级，请先审核执行迁移", 409)
        _, new = await self.plan(session, user, org_id, starts_on, week)
        await ensure_builtin_definitions(session, [CALENDAR_PERIOD_DEFINITION])
        options = await dictionaries.options_in_session(session, [CALENDAR_PERIOD_DEFINITION[0]])
        if not {"work", "lunch"} <= {r["item_code"] for r in options.get(CALENDAR_PERIOD_DEFINITION[0], [])}:
            raise AppException("日历工作/午休字典缺失或停用，未自动重新启用", 409)
        count = 0
        for kind, identifier in new:
            calendar = MesResourceCalendar(org_id=org_id, calendar_name="生产人员默认工作日历" if kind == "person" else "设备默认工作日历",
                timezone_name=week.timezone_name, valid_from=starts_on,
                **{"production_person_id" if kind == "person" else "equipment_id": identifier},
                created_by=user.user_id, updated_by=user.user_id)
            repository.add(session, calendar)
            await session.flush()
            for weekday, code, start, end in week.periods(kind):
                repository.add(session, MesResourceCalendarPeriod(org_id=org_id, calendar_id=calendar.id,
                    weekday_no=weekday, period_type_code=code, start_minute_of_day=start, end_minute_of_day=end,
                    created_by=user.user_id, updated_by=user.user_id))
                count += 1
        await session.flush()
        return dict(new_calendars=len(new), new_periods=count)


service = CalendarService()
