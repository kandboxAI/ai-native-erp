"""配置工时的只读计划估算；不占用设备，不代替人工排程。"""
from datetime import timedelta
from decimal import Decimal

MAX_PLAN_MINUTES = Decimal("5256000")


def configuration_plan(operations):
    ordered = sorted(operations, key=lambda op: (op.sequence_no, str(op.id)))
    cursor = getattr(ordered[0], "created_at", None) if ordered else None
    result = {}
    for op in ordered:
        per_unit = getattr(op, "standard_minutes_per_unit", None)
        minutes = Decimal(str(per_unit)) * Decimal(str(op.planned_quantity)) if per_unit is not None else None
        start, end = getattr(op, "planned_start_at", None), getattr(op, "planned_end_at", None)
        if start is not None and end is not None:
            source = "schedule"
        elif getattr(op, "is_imported_snapshot", False):
            source, start, end = None, None, None
        else:
            source = "configuration" if cursor is not None and minutes is not None else None
            start = cursor if minutes is not None else None
            end = start + timedelta(seconds=float(minutes * 60)) if start is not None else None
        cursor = end
        result[op.id] = dict(planned_start_at=start, planned_end_at=end, plan_source_key=source,
            standard_minutes_per_unit=float(per_unit) if per_unit is not None else None,
            planned_duration_minutes=(end-start).total_seconds()/60 if start is not None and end is not None else None)
    return result
