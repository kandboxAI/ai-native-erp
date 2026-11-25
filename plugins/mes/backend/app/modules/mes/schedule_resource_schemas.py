from datetime import date
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.db.pagination import PageParams


class ResourceQuery(PageParams):
    org_id: UUID | None = None
    keyword: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    process_id: UUID | None = None


class ResourceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    org_id: UUID
    version_no: int | None = Field(default=None, ge=1)
    is_active: bool = True


class PersonBody(ResourceBody):
    person_no: str = Field(min_length=1, max_length=64)
    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    job_title_snapshot: str | None = Field(default=None, max_length=128)


class QualificationBody(ResourceBody):
    process_id: UUID
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("资格结束时间须晚于开始时间")
        return self


class CalendarPeriodBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday_no: int = Field(ge=1, le=7)
    period_type_code: Literal["work", "lunch"]
    start_minute_of_day: int = Field(ge=0, lt=1440)
    end_minute_of_day: int = Field(gt=0, le=1440)


class CalendarBody(ResourceBody):
    production_person_id: UUID | None = None
    equipment_id: UUID | None = None
    calendar_name: str = Field(min_length=1, max_length=128)
    timezone_name: str = Field(default="Asia/Shanghai", max_length=64)
    valid_from: date
    valid_to: date | None = None
    periods: list[CalendarPeriodBody] = Field(min_length=1, max_length=70)

    @model_validator(mode="after")
    def validate_periods(self):
        if (self.production_person_id is None) == (self.equipment_id is None):
            raise ValueError("人员和设备必须选择其中一个")
        try: ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as error: raise ValueError("请输入有效IANA时区，如Asia/Shanghai") from error
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("日历结束日期须晚于开始日期")
        last = {}
        for p in sorted(self.periods, key=lambda p: (p.weekday_no, p.start_minute_of_day)):
            if p.start_minute_of_day >= p.end_minute_of_day or p.start_minute_of_day < last.get(p.weekday_no, -1):
                raise ValueError("同一天的工作/午休时段不得重叠，结束须晚于开始")
            last[p.weekday_no] = p.end_minute_of_day
        return self


class CalendarBatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendars: list[CalendarBody] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def same_org(self):
        if len({c.org_id for c in self.calendars}) > 1: raise ValueError("一次批量创建须为同一组织")
        return self


class CalendarExceptionBody(ResourceBody):
    start_at: AwareDatetime
    end_at: AwareDatetime
    exception_type_code: Literal["extra_available", "unavailable"]
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_period(self):
        if self.end_at <= self.start_at:
            raise ValueError("例外结束时间须晚于开始时间")
        return self
