"""常规日历与例外的纯区间计算；不可用优先，非午休空档永不视为无人运行。"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .calendar_service import day_windows


def union(periods):
    result = []
    for start, end in sorted(periods):
        if start >= end: continue
        if result and start <= result[-1][1]: result[-1] = (result[-1][0], max(end, result[-1][1]))
        else: result.append((start, end))
    return result


def subtract(periods, blocked):
    result = union(periods)
    for a, b in union(blocked):
        remaining = []
        for start, end in result:
            if b <= start or a >= end: remaining.append((start, end))
            else:
                if start < a: remaining.append((start, a))
                if b < end: remaining.append((b, end))
        result = remaining
    return result


def effective_windows(calendar, periods, exceptions, day, extra_absences=()):
    result = day_windows(calendar, periods, day)
    if not calendar.is_active or calendar.deleted_at or day < calendar.valid_from or (calendar.valid_to and day >= calendar.valid_to):
        return dict(work=[], auto=[], lunch=[])
    origin = datetime.combine(day, time.min, ZoneInfo(calendar.timezone_name))
    finish = origin + timedelta(days=1)
    extras, blocked = [], list(extra_absences)
    for e in exceptions:
        if e.calendar_id != calendar.id or not e.is_active or e.deleted_at: continue
        a, b = max(e.start_at, origin), min(e.end_at, finish)
        if a >= b: continue
        if e.exception_type_code == "extra_available": extras.append((a, b))
        elif e.exception_type_code == "unavailable": blocked.append((a, b))
        else: raise ValueError("日历包含未知例外类型")
    work = subtract(result["work"] + extras, blocked)
    lunch = subtract(result["lunch"], blocked + work)
    # 只有显式午休桥接前后工作段，孤立午休不产生可自动加工的时段。
    auto = list(work)
    for a, b in lunch:
        if any(end == a for _, end in work) and any(start == b for start, _ in work): auto.append((a, b))
    return dict(work=work, lunch=lunch, auto=union(auto))
