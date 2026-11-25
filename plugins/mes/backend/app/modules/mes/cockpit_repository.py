"""交付只读投影：先圈定授权工单，再按父工单聚合，避免工序/出货联乘。"""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from app.auth.scope_filters import scoped_conditions
from app.framework.db.models import utc_now
from .exception_models import MesExceptionCase
from .models import MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesProductionReport, MesProductionReportChange
from .delivery_models import MesShipment, MesShipmentLine

TZ = ZoneInfo("Asia/Shanghai")


def midnight(day):
    return datetime.combine(day, time.min, TZ).astimezone(UTC)


def count_if(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def cockpit_dataset(query, user, now=None):
    now = now or utc_now()
    order, project, task = MesWorkOrder, MesProductionOrder, MesWorkOrderOperation
    conditions = [*scoped_conditions(order, user, "mes:dashboard:view"),
                  *scoped_conditions(order, user, "mes:work_order:list"), order.status_code != "cancelled"]
    if query.org_id: conditions.append(order.org_id == query.org_id)
    if query.due_from: conditions.append(order.due_at >= midnight(query.due_from))
    if query.due_to: conditions.append(order.due_at < midnight(query.due_to + timedelta(days=1)))
    if query.keyword and query.keyword.strip():
        word = f"%{query.keyword.strip()}%"
        conditions.append(or_(order.work_order_no.ilike(word), order.product_item_no_snapshot.ilike(word),
            order.product_item_name_snapshot.ilike(word), project.production_order_no.ilike(word), project.project_name.ilike(word)))
    if query.customer and query.customer.strip():
        word = f"%{query.customer.strip()}%"
        conditions.append(or_(project.customer_no_snapshot.ilike(word), project.customer_name_snapshot.ilike(word)))
    base = select(order.id, order.org_id, order.work_order_no, order.status_code, order.priority_code, order.due_at,
        order.planned_quantity, order.unit_code, order.product_item_no_snapshot.label("product_item_no"),
        order.product_item_name_snapshot.label("product_item_name"), project.production_order_no, project.project_name,
        project.customer_no_snapshot.label("customer_no"), project.customer_name_snapshot.label("customer_name")
    ).outerjoin(project, and_(project.id == order.production_order_id, project.org_id == order.org_id,
        project.deleted_at.is_(None))).where(*conditions).cte("cockpit_orders")
    tasks = select(task.id, task.org_id, task.work_order_id, task.status_code, task.sequence_no, task.good_quantity,
        task.is_quality_required, task.planned_start_at, task.planned_end_at, task.operation_name_snapshot,
        task.workstation_name_snapshot).join(base, and_(base.c.id == task.work_order_id, base.c.org_id == task.org_id)
    ).where(task.deleted_at.is_(None)).cte("cockpit_tasks")
    tc = tasks.c
    totals = select(tc.work_order_id, func.count().label("operation_count"),
        count_if(tc.status_code == "completed").label("completed_operation_count"),
        count_if(tc.status_code == "waiting_quality").label("waiting_quality_count"),
        count_if(and_(tc.status_code.in_(["draft", "pending", "dispatched"]), tc.planned_start_at.is_(None))).label("unplanned_count"),
        count_if(tc.status_code.in_(["paused", "cancelled"])).label("blocked_operation_count"),
        func.max(case((tc.status_code.notin_(["completed", "cancelled"]), tc.planned_end_at))).label("latest_planned_end_at")
    ).group_by(tc.work_order_id).cte("cockpit_operation_totals")
    ranked = select(tc.work_order_id, tc.operation_name_snapshot, tc.workstation_name_snapshot, tc.status_code, tc.good_quantity,
        tc.is_quality_required, tc.planned_end_at,
        func.row_number().over(partition_by=tc.work_order_id, order_by=(tc.sequence_no.desc(), tc.id.desc())).label("position")
    ).cte("cockpit_last_ranked")
    last = select(ranked).where(ranked.c.position == 1).cte("cockpit_last")
    current_ranked = select(tc.work_order_id, tc.operation_name_snapshot, tc.workstation_name_snapshot, tc.status_code, tc.planned_end_at,
        func.row_number().over(partition_by=tc.work_order_id, order_by=(tc.sequence_no, tc.id)).label("position")
    ).where(tc.status_code.notin_(["completed", "cancelled"])).cte("cockpit_current_ranked")
    current = select(current_ranked).where(current_ranked.c.position == 1).cte("cockpit_current")
    # 只发布已授权父工单的履约数量，不发布出货单号、金额、人员或其他工单的事实。
    shipment = select(MesShipmentLine.work_order_id, func.sum(MesShipmentLine.quantity).label("shipped_quantity")
    ).join(base, and_(base.c.id == MesShipmentLine.work_order_id, base.c.org_id == MesShipmentLine.org_id)).join(
        MesShipment, and_(MesShipment.id == MesShipmentLine.shipment_id, MesShipment.org_id == base.c.org_id)
    ).where(MesShipment.status_code == "posted").group_by(MesShipmentLine.work_order_id).cte("cockpit_shipments")
    changes = select(tc.work_order_id, func.count().label("pending_change_count")).join(
        MesProductionReport, MesProductionReport.operation_id == tc.id).join(
        MesProductionReportChange, and_(MesProductionReportChange.report_id == MesProductionReport.id, MesProductionReportChange.org_id == tc.org_id)
    ).where(MesProductionReportChange.status_code.in_(["draft", "submitted"])).group_by(tc.work_order_id).cte("cockpit_changes")
    exceptions = select(MesExceptionCase.work_order_id, func.count().label("open_exception_count"),
        count_if(MesExceptionCase.due_at < now).label("overdue_exception_count")
    ).join(base, and_(base.c.id == MesExceptionCase.work_order_id, base.c.org_id == MesExceptionCase.org_id)).where(
        MesExceptionCase.deleted_at.is_(None), MesExceptionCase.status_code != "closed"
    ).group_by(MesExceptionCase.work_order_id).cte("cockpit_exceptions")
    shipped = func.coalesce(shipment.c.shipped_quantity, 0)
    outstanding = case((base.c.planned_quantity > shipped, base.c.planned_quantity - shipped), else_=0)
    eligible = and_(base.c.status_code.in_(["released", "in_progress", "completed"]),
        last.c.status_code.in_(["pending", "dispatched", "completed"]),
        or_(last.c.is_quality_required.is_(False), last.c.status_code == "completed"))
    return select(base, shipped.label("shipped_quantity"), outstanding.label("outstanding_quantity"),
        case((eligible, last.c.good_quantity), else_=0).label("released_good_quantity"),
        *[func.coalesce(getattr(totals.c, name), 0).label(name) for name in (
            "operation_count", "completed_operation_count", "waiting_quality_count", "unplanned_count", "blocked_operation_count")],
        totals.c.latest_planned_end_at, func.coalesce(changes.c.pending_change_count, 0).label("pending_change_count"),
        func.coalesce(exceptions.c.open_exception_count, 0).label("open_exception_count"),
        func.coalesce(exceptions.c.overdue_exception_count, 0).label("overdue_exception_count"),
        current.c.operation_name_snapshot.label("current_operation_name"), current.c.status_code.label("current_operation_status"),
        current.c.workstation_name_snapshot.label("current_workstation"), current.c.planned_end_at.label("current_planned_end_at")
    ).select_from(base).outerjoin(totals, totals.c.work_order_id == base.c.id).outerjoin(last, last.c.work_order_id == base.c.id
    ).outerjoin(current, current.c.work_order_id == base.c.id).outerjoin(shipment, shipment.c.work_order_id == base.c.id
    ).outerjoin(changes, changes.c.work_order_id == base.c.id).outerjoin(exceptions, exceptions.c.work_order_id == base.c.id).cte("cockpit_dataset")


def focus_conditions(data, now, soon_days):
    row = data.c
    open_ = row.outstanding_quantity > 0
    cutoff = midnight(now.astimezone(TZ).date() + timedelta(days=soon_days))
    return {
        "all": True, "outstanding": open_, "delivered": ~open_,
        "overdue": and_(open_, row.due_at < now),
        "due_soon": and_(open_, row.due_at >= now, row.due_at < cutoff),
        "waiting_quality": and_(open_, row.waiting_quality_count > 0),
        "unplanned": and_(open_, row.unplanned_count > 0),
        "released_output": and_(open_, row.released_good_quantity > row.shipped_quantity, row.pending_change_count == 0),
        "no_due": and_(open_, row.due_at.is_(None)),
        "exceptions": row.open_exception_count > 0,
        "overdue_exceptions": row.overdue_exception_count > 0,
        "blocked": and_(open_, or_(row.status_code.in_(["draft", "paused"]), row.pending_change_count > 0,
            row.blocked_operation_count > 0, row.operation_count == 0, row.waiting_quality_count > 0, row.unplanned_count > 0, row.open_exception_count > 0,
            and_(row.current_planned_end_at.is_not(None), row.current_planned_end_at < now),
            row.latest_planned_end_at > row.due_at)),
    }


class CockpitRepository:
    async def read(self, session, query, user, now):
        data = cockpit_dataset(query, user, now)
        conditions = focus_conditions(data, now, query.soon_days)
        today = now.astimezone(TZ).date()
        days = [today + timedelta(days=index) for index in range(query.soon_days)]
        summary = dict((await session.execute(select(func.count().label("total"),
            *[count_if(condition).label(key) for key, condition in conditions.items() if key != "all"],
            *[count_if(and_(conditions["outstanding"], data.c.due_at >= midnight(day),
                data.c.due_at < midnight(day + timedelta(days=1)))).label(f"day_{index}") for index, day in enumerate(days)]
        ).select_from(data))).mappings().one())
        total = summary["total"] if query.focus == "all" else summary[query.focus]
        rows = (await session.execute(select(data).where(conditions[query.focus]).order_by(
            case((conditions["overdue"], 0), (conditions["due_soon"], 1), (conditions["outstanding"], 2), else_=3),
            data.c.due_at.asc().nulls_last(), data.c.work_order_no, data.c.id
        ).offset((query.page - 1) * query.page_size).limit(query.page_size))).mappings().all()
        buckets = [dict(day=day.isoformat(), order_count=summary.pop(f"day_{index}")) for index, day in enumerate(days)]
        return dict(items=[dict(row) for row in rows], total=total, summary=summary, due_buckets=buckets,
            page=query.page, page_size=query.page_size)


cockpit_repository = CockpitRepository()
