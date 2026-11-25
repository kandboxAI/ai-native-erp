"""业务时间统一规范（全项目直接 import 本模块调用，勿再手写 ±8 小时）。

- 数据库存储：所有时间点为 ``timestamptz``（规范 §4）；Python 侧一律使用**带时区**的 datetime。
- 写库：``local_now()`` 或 ``app.framework.db.models.utc_now()``（两者同一时刻，时区不同）。
- API 入参：``parse_datetime_input`` 返回带时区的上海时间；无时区的字符串按上海墙钟解释。
- API 出参展示：``format_display_datetime`` → 上海时间 ``YYYY-MM-DD HH:mm:ss``。
- 前端 el-date-picker：``format_picker_datetime`` → ``YYYY-MM-DDTHH:mm:ss``（上海墙钟，无时区后缀）。
- ``naive_local_now`` / ``to_naive_local_datetime`` 只用于取日期、格式化等计算，不得写入数据库。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")

DISPLAY_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
PICKER_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S"


def local_now() -> datetime:
    """当前时刻（带时区，Asia/Shanghai），可直接写入 timestamptz 字段。"""
    return datetime.now(LOCAL_TIMEZONE)


def naive_local_now() -> datetime:
    """当前上海墙钟（naive），只用于日期计算与格式化，不得写入数据库。"""
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)


def to_local_datetime(dt: datetime | None) -> datetime | None:
    """转为带时区的上海时间；naive 视为上海墙钟。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TIMEZONE)
    return dt.astimezone(LOCAL_TIMEZONE)


def to_naive_local_datetime(dt: datetime | None) -> datetime | None:
    """将任意 datetime 转为上海墙钟 naive；已为 naive 则原样（视为已是墙钟）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def parse_datetime_input(value: Any) -> datetime | None:
    """将 API / 表单 / Pydantic 入参转为带时区的上海时间，供入库或比较。

    - ``datetime``：aware 转上海时区；naive 视为上海墙钟
    - ``str`` 末尾 ``Z`` 或 ``+00:00``：按 UTC 解析后转本地
    - ``str`` 无时区：按上海墙钟解析（``YYYY-MM-DDTHH:mm:ss`` 或空格分隔）
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_local_datetime(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    normalized = s.replace(" ", "T", 1) if " " in s and "T" not in s else s
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return to_local_datetime(parsed)


def format_display_datetime(dt: datetime | None) -> str | None:
    """列表/详情展示：上海时间 ``YYYY-MM-DD HH:mm:ss``。"""
    local = to_naive_local_datetime(dt)
    if local is None:
        return None
    return local.strftime(DISPLAY_DATETIME_FMT)


def format_picker_datetime(dt: datetime | None) -> str | None:
    """与前端 ``PICKER_DATETIME_FORMAT`` 一致的无时区 ISO。"""
    local = to_naive_local_datetime(dt)
    if local is None:
        return None
    return local.strftime(PICKER_DATETIME_FMT)


def local_date_start(value: date) -> datetime:
    """日期筛选：上海时间当天 00:00:00（带时区）。"""
    return datetime.combine(value, time.min, tzinfo=LOCAL_TIMEZONE)


def local_date_end(value: date) -> datetime:
    """日期筛选：上海时间当天 23:59:59.999999（带时区）。"""
    return datetime.combine(value, time.max, tzinfo=LOCAL_TIMEZONE)


def parse_business_datetime_input(value: Any) -> datetime | None:
    """业务事件时间入参（入住/退住/充值/评估等）：解析后并对「今日 00:00:00」补当前时刻。"""
    parsed = parse_datetime_input(value)
    if parsed is None:
        return None
    return resolve_business_datetime_from_date_only(parsed) or parsed


def resolve_business_datetime_from_date_only(dt: datetime | None) -> datetime | None:
    """仅传「某日 00:00:00」且为今天时，视为当日实际办理，取当前时刻（避免列表显示 00:00）。"""
    local = to_local_datetime(dt)
    if local is None:
        return None
    today = local_now().date()
    if (
        local.date() == today
        and local.hour == 0
        and local.minute == 0
        and local.second == 0
        and local.microsecond == 0
    ):
        return local_now()
    return local


def coerce_payload_datetimes(payload: dict[str, Any], *field_names: str) -> dict[str, Any]:
    """批量规范化 payload 中的时间字段（返回新 dict 浅拷贝）。"""
    data = dict(payload)
    for name in field_names:
        if name not in data:
            continue
        parsed = parse_business_datetime_input(data[name])
        if parsed is not None:
            data[name] = parsed
    return data
