"""交付驾驶舱编排；只读已授权工单的最小履约投影。"""
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .cockpit_repository import cockpit_repository, TZ


def decorate(row, now, soon_days):
    def aware(value):
        # PostgreSQL 返回带时区值；离线 SQLite 测试返回无时区 UTC。
        from datetime import UTC
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
    due = aware(row["due_at"])
    open_ = row["outstanding_quantity"] > 0
    row["delivery_status"] = ("delivered" if not open_ else "no_due" if due is None else "overdue" if due < now
        else "due_soon" if (due.astimezone(TZ).date() - now.astimezone(TZ).date()).days < soon_days else "on_track")
    flags = []
    if row["open_exception_count"]: flags.append("open_exception")
    if row["overdue_exception_count"]: flags.append("overdue_exception")
    if open_:
        for condition, flag in (
            (row["status_code"] == "draft", "unreleased"), (row["status_code"] == "paused", "paused"),
            (row["operation_count"] == 0, "unconfigured"), (row["waiting_quality_count"] > 0, "waiting_quality"),
            (row["pending_change_count"] > 0, "pending_change"), (row["blocked_operation_count"] > 0, "blocked_operation"),
            (row["unplanned_count"] > 0, "unplanned"),
            (bool(row["latest_planned_end_at"] and due and aware(row["latest_planned_end_at"]) > due), "plan_after_due"),
            (bool(row["current_planned_end_at"] and aware(row["current_planned_end_at"]) < now), "operation_late"),
        ):
            if condition: flags.append(flag)
    row["risk_flags"] = flags
    for name in ("planned_quantity", "shipped_quantity", "outstanding_quantity", "released_good_quantity"):
        row[name] = str(row[name])
    return row


class CockpitService:
    async def read(self, query, user):
        if not {"mes:dashboard:view", "mes:work_order:list"}.issubset(user.permissions):
            raise AppException("查看交付驾驶舱需要工作台和生产工单查询权限", 403)
        now = utc_now()
        async with get_session_context() as session:
            result = await cockpit_repository.read(session, query, user, now)
        result["items"] = [decorate(row, now, query.soon_days) for row in result["items"]]
        return dict(**result, generated_at=now, soon_days=query.soon_days)


cockpit_service = CockpitService()
