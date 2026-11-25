"""资源常规工作日历；不生成执行事实，不据空档推断午休。"""
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlalchemy.schema import conv
from sqlmodel import Field
from .archive_models import ArchiveFields


class MesResourceCalendar(ArchiveFields, table=True):
    __tablename__ = "mes_resource_calendar"
    __table_args__ = (
        # 索引列名部分缩写，满足 PostgreSQL 63 字节名称限制。
        Index("uk_mes_resource_calendar_person_start", "org_id", "production_person_id", "valid_from", unique=True,
            postgresql_where=text("deleted_at is null and production_person_id is not null")),
        Index("uk_mes_resource_calendar_equipment_start", "org_id", "equipment_id", "valid_from", unique=True,
            postgresql_where=text("deleted_at is null and equipment_id is not null")),
        CheckConstraint("(production_person_id IS NOT NULL AND equipment_id IS NULL) OR (production_person_id IS NULL AND equipment_id IS NOT NULL)", name="ck_mes_resource_calendar_one_resource"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_mes_resource_calendar_valid_period"),
        {"comment": "制造资源常规日历；一行代表同组织一个人员或一台设备在有效日期内的工作日历，不是考勤或实际产量。"},
    )
    production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "人员日历所属生产身份；设备日历为空，与设备外键恰好一个非空"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "设备日历所属物理设备；人员日历为空，与人员外键恰好一个非空"})
    calendar_name: str = Field(max_length=128, sa_column_kwargs={"comment": "日历名称；不使用人员姓名作为资源标识"})
    timezone_name: str = Field(max_length=64, sa_column_kwargs={"comment": "本地时段使用的IANA时区名称，如Asia/Shanghai"})
    valid_from: date = Field(sa_column_kwargs={"comment": "日历生效本地日期；左闭端"})
    valid_to: date | None = Field(default=None, sa_column_kwargs={"comment": "日历失效本地日期；右开端，空表示持续有效"})


class MesResourceCalendarPeriod(ArchiveFields, table=True):
    __tablename__ = "mes_resource_calendar_period"
    __table_args__ = (
        # 按63字节限制缩写索引列名部分：calendar_id/weekday_no/start_minute_of_day。
        Index("uk_mes_resource_calendar_period_calendar_day_start", "calendar_id", "weekday_no", "start_minute_of_day", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("weekday_no >= 1 AND weekday_no <= 7", name="ck_mes_resource_calendar_period_weekday"),
        CheckConstraint("start_minute_of_day >= 0 AND start_minute_of_day < end_minute_of_day AND end_minute_of_day <= 1440", name="ck_mes_resource_calendar_period_minutes"),
        {"comment": "制造常规日历时段；一行代表资源每周某天的一段工作或明确午休，左闭右开，不存ID数组或假期推断。"},
    )
    calendar_id: UUID = Field(foreign_key="mes_resource_calendar.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属同组织资源日历"})
    weekday_no: int = Field(sa_column_kwargs={"comment": "本地星期编号；1为周一、7为周日"})
    period_type_code: str = Field(max_length=64, sa_column_kwargs={"comment": "时段类型；字典 mes_calendar_period_type；午休不是人员工作时间"})
    start_minute_of_day: int = Field(sa_column_kwargs={"comment": "本地日内开始分钟；0至1439，左闭端"})
    end_minute_of_day: int = Field(sa_column_kwargs={"comment": "本地日内结束分钟；1至1440，右开端，须大于开始"})


class MesResourceCalendarException(ArchiveFields, table=True):
    __tablename__ = "mes_resource_calendar_exception"
    __table_args__ = (
        Index("idx_mes_resource_calendar_exception_calendar_start", "calendar_id", "start_at"),
        CheckConstraint("end_at > start_at", name=conv("ck_mes_resource_calendar_exception_period")),
        {"comment": "制造资源日历例外；一行代表资源的一段临时可用或不可用时段，不可用优先，不作为午休无人运行许可。"},
    )
    calendar_id: UUID = Field(foreign_key="mes_resource_calendar.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属资源日历；须同组织且位于日历有效期内"})
    start_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "例外开始时间；左闭端"})
    end_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "例外结束时间；右开端"})
    exception_type_code: str = Field(max_length=64, sa_column_kwargs={"comment": "例外类型；字典 mes_calendar_exception_type"})
    reason: str = Field(max_length=500, sa_column_kwargs={"comment": "例外原因；自由文本不进入AI或求解器"})
