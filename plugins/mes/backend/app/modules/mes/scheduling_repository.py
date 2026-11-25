"""人工排程的任务筛选、设备负荷与日期交集；所有聚合继承排程数据范围。"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import String, and_, case, cast, func, literal, or_, select, union_all
from app.auth.scope_filters import scoped_conditions
from app.framework.db.models import utc_now
from .archive_models import MesEquipment, MesProcess, MesEquipmentProcess
from .models import MesWorkOrder, MesWorkOrderOperation, MesProductionOrder
from .schedule_models import MesSchedulePlan,MesSchedulePlanOperation,MesSchedulePlanSegment

TZ = ZoneInfo("Asia/Shanghai")


def midnight(day):
    return datetime.combine(day, time.min, TZ)


def schedule_statement(query, user):
    task, order, project = MesWorkOrderOperation, MesWorkOrder, MesProductionOrder
    conditions = [*scoped_conditions(task, user, "mes:schedule:list"), *scoped_conditions(order,user,"mes:schedule:list")]
    if query.keyword and query.keyword.strip():
        word = f"%{query.keyword.strip()}%"
        conditions.append(or_(order.work_order_no.ilike(word), task.operation_name_snapshot.ilike(word),
            project.production_order_no.ilike(word), project.project_name.ilike(word), order.product_item_no_snapshot.ilike(word)))
    if query.product_keyword and query.product_keyword.strip():
        word = f"%{query.product_keyword.strip()}%"
        conditions.append(or_(order.product_item_no_snapshot.ilike(word), order.product_item_name_snapshot.ilike(word)))
    if query.work_order_id: conditions.append(task.work_order_id == query.work_order_id)
    if query.org_id: conditions.append(task.org_id == query.org_id)
    if query.status_code: conditions.append(task.status_code == query.status_code)
    if query.priority_code: conditions.append(order.priority_code == query.priority_code)
    if query.process_id: conditions.append(task.process_id == query.process_id)
    if query.equipment_id: conditions.append(task.equipment_id == query.equipment_id)
    if query.work_center: conditions.append(task.work_center_name_snapshot.ilike(f"%{query.work_center.strip()}%"))
    if query.workstation is not None: conditions.append(func.trim(func.coalesce(task.workstation_name_snapshot, "")) == query.workstation.strip())
    if query.work_center_exact is not None: conditions.append(func.trim(func.coalesce(task.work_center_name_snapshot, "")) == query.work_center_exact.strip())
    if query.equipment_keyword and query.equipment_keyword.strip():
        word = f"%{query.equipment_keyword.strip()}%"
        ids = select(MesEquipment.id).where(MesEquipment.deleted_at.is_(None), or_(MesEquipment.equipment_no.ilike(word), MesEquipment.equipment_name.ilike(word)))
        conditions.append(or_(task.equipment_id.in_(ids), task.workstation_name_snapshot.ilike(word)))
    if query.unfinished_only:
        conditions.extend([task.status_code.notin_(["completed", "cancelled"]), order.status_code.notin_(["completed", "cancelled"])])
    if query.unstarted_only:
        conditions.extend([task.status_code.in_(["draft", "pending", "dispatched"]), order.status_code.in_(["draft", "released", "in_progress"])])
    if query.unassigned_only:
        conditions.extend([task.equipment_id.is_(None), func.trim(func.coalesce(task.workstation_name_snapshot, "")) == ""])
    if query.scheduled is not None: conditions.append(task.planned_start_at.is_not(None) if query.scheduled else task.planned_start_at.is_(None))
    if query.start_date: conditions.append(task.planned_end_at > midnight(query.start_date))
    if query.end_date: conditions.append(task.planned_start_at < midnight(query.end_date + timedelta(days=1)))
    if query.due_from: conditions.append(order.due_at >= midnight(query.due_from))
    if query.due_to: conditions.append(order.due_at < midnight(query.due_to + timedelta(days=1)))
    return select(task, order).join(order, order.id == task.work_order_id).outerjoin(project,
        and_(project.id == order.production_order_id, project.deleted_at.is_(None))).where(*conditions)


def work_order_schedule_queries(query, user):
    """先按命中工序筛选货品工单并分页，再读取这些工单的全部授权工序。"""
    from .schemas import ScheduleQuery
    task, order = MesWorkOrderOperation, MesWorkOrder
    matched = schedule_statement(query, user).with_only_columns(
        order.id.label("work_order_id"), order.work_order_no, order.due_at,
    ).distinct().subquery("matched_schedule_orders")
    count = select(func.count()).select_from(matched)
    page = select(matched).order_by(matched.c.due_at.asc().nulls_last(), matched.c.work_order_no,
        matched.c.work_order_id).offset((query.page - 1) * query.page_size).limit(query.page_size).subquery("schedule_order_page")
    # 不沿用工序状态/工艺/设备等筛选，避免路线被截断；重新应用两级范围及软删除条件。
    statement = schedule_statement(ScheduleQuery(org_id=query.org_id), user).join(
        page, page.c.work_order_id == order.id).order_by(page.c.due_at.asc().nulls_last(),
        page.c.work_order_no, order.id, task.sequence_no, task.id)
    return count, statement


def resource_key(equipment_id, org_id, center, station):
    return case((equipment_id.is_not(None), func.concat("equipment:", cast(org_id, String), ":", cast(equipment_id, String))), else_=func.concat("station:", cast(func.json_build_array(cast(org_id, String),
        func.trim(func.coalesce(center, "")), func.trim(func.coalesce(station, ""))), String)))


def resource_queries(query, user):
    task, equipment, process = MesWorkOrderOperation, MesEquipment, MesProcess
    plan,po,segment=MesSchedulePlan,MesSchedulePlanOperation,MesSchedulePlanSegment
    active=and_(plan.status_code=="applied",plan.is_active.is_(True),plan.deleted_at.is_(None),po.is_active.is_(True),po.deleted_at.is_(None))
    formal_exists=select(po.id).join(plan,plan.id==po.plan_id).where(po.operation_id==task.id,active).exists()
    manual=schedule_statement(query,user).with_only_columns(task.id,task.org_id,task.equipment_id,task.status_code,
        task.work_center_name_snapshot,task.workstation_name_snapshot,task.planned_start_at,task.planned_end_at).where(~formal_exists)
    # 正式自动计划按机器真实阶段聚合，不能把首件、剩余批量及其间等待的父工序总跨度算成连续占机。
    clean=query.model_copy(update={k:None for k in ("equipment_id","equipment_keyword","work_center","workstation","work_center_exact","process_id")}|{"unassigned_only":False})
    visible=schedule_statement(clean,user).with_only_columns(task.id).subquery("visible_stage_tasks")
    formal=select(task.id,task.org_id,segment.equipment_id,task.status_code,equipment.work_center_name,equipment.equipment_no,
        segment.planned_start_at,segment.planned_end_at).select_from(segment).join(po,po.id==segment.plan_operation_id).join(plan,plan.id==po.plan_id)
    formal=formal.join(task,task.id==po.operation_id).join(visible,visible.c.id==task.id).join(equipment,equipment.id==segment.equipment_id).where(
        active,segment.deleted_at.is_(None),segment.is_active.is_(True),segment.is_equipment_occupied.is_(True),equipment.deleted_at.is_(None),
        *scoped_conditions(po,user,"mes:schedule:list"),*scoped_conditions(segment,user,"mes:schedule:list"))
    if query.equipment_id:formal=formal.where(segment.equipment_id==query.equipment_id)
    if query.process_id:formal=formal.where(segment.process_id==query.process_id)
    if query.equipment_keyword:
        word=f"%{query.equipment_keyword.strip()}%";formal=formal.where(or_(equipment.equipment_no.ilike(word),equipment.equipment_name.ilike(word)))
    if query.work_center:formal=formal.where(equipment.work_center_name.ilike(f"%{query.work_center.strip()}%"))
    if query.workstation is not None:formal=formal.where(equipment.equipment_no==query.workstation.strip())
    if query.work_center_exact is not None:formal=formal.where(equipment.work_center_name==query.work_center_exact.strip())
    if query.unassigned_only:formal=formal.where(False)
    if query.start_date:formal=formal.where(segment.planned_end_at>midnight(query.start_date))
    if query.end_date:formal=formal.where(segment.planned_start_at<midnight(query.end_date+timedelta(days=1)))
    base=union_all(manual,formal).subquery("scheduled_tasks")
    key = resource_key(base.c.equipment_id, base.c.org_id, base.c.work_center_name_snapshot, base.c.workstation_name_snapshot)
    duration = case((and_(base.c.planned_start_at.is_not(None), base.c.planned_end_at.is_not(None)),
        func.extract("epoch", base.c.planned_end_at - base.c.planned_start_at) / 60), else_=0)
    grouped = select(key.label("resource_key"), base.c.org_id, base.c.equipment_id,
        func.max(base.c.work_center_name_snapshot).label("work_center_name"), func.max(base.c.workstation_name_snapshot).label("workstation_name"),
        func.count(func.distinct(base.c.id)).label("task_count"), func.count(func.distinct(case((base.c.planned_start_at.is_not(None), base.c.id)))).label("scheduled_count"),
        func.sum(duration).label("planned_minutes")).group_by(key, base.c.org_id, base.c.equipment_id).cte("resource_totals")
    station_no = func.coalesce(grouped.c.workstation_name, "")
    assigned = select(grouped.c.resource_key, grouped.c.org_id, grouped.c.equipment_id,
        func.coalesce(equipment.equipment_no, station_no).label("equipment_no"),
        func.coalesce(equipment.equipment_name, case((func.trim(station_no) == "", "未分配设备"), else_=station_no)).label("equipment_name"),
        equipment.process_id, process.process_name, func.coalesce(equipment.is_active, True).label("is_active"),
        grouped.c.work_center_name, grouped.c.workstation_name, grouped.c.task_count, grouped.c.scheduled_count, grouped.c.planned_minutes,
        case((grouped.c.equipment_id.is_not(None), "equipment"), (func.trim(station_no) == "", "unassigned"), else_="station").label("kind")
    ).select_from(grouped).outerjoin(equipment, and_(equipment.id == grouped.c.equipment_id, equipment.org_id == grouped.c.org_id,
        equipment.deleted_at.is_(None))).outerjoin(process, and_(process.id == equipment.process_id, process.deleted_at.is_(None)))
    idle_conditions = [*scoped_conditions(equipment, user, "mes:schedule:list"), equipment.is_active.is_(True),
        ~select(grouped.c.equipment_id).where(grouped.c.equipment_id == equipment.id).exists()]
    if query.org_id: idle_conditions.append(equipment.org_id == query.org_id)
    if query.equipment_id: idle_conditions.append(equipment.id == query.equipment_id)
    if query.process_id:
        from .archive_repository import equipment_process_condition
        idle_conditions.append(equipment_process_condition(equipment, query.process_id))
    if query.work_center: idle_conditions.append(equipment.work_center_name.ilike(f"%{query.work_center.strip()}%"))
    if query.equipment_keyword:
        word = f"%{query.equipment_keyword.strip()}%"
        idle_conditions.append(or_(equipment.equipment_no.ilike(word), equipment.equipment_name.ilike(word)))
    if query.unassigned_only or query.workstation is not None: idle_conditions.append(literal(False))
    idle = select(func.concat("equipment:", cast(equipment.org_id, String), ":", cast(equipment.id, String)).label("resource_key"), equipment.org_id, equipment.id.label("equipment_id"), equipment.equipment_no,
        equipment.equipment_name, equipment.process_id, process.process_name, equipment.is_active,
        equipment.work_center_name, equipment.equipment_no.label("workstation_name"), literal(0).label("task_count"),
        literal(0).label("scheduled_count"), literal(0).label("planned_minutes"), literal("equipment").label("kind")
    ).outerjoin(process, process.id == equipment.process_id).where(*idle_conditions)
    return base, union_all(assigned, idle).subquery("schedule_resources")


def daily_load_statement(base, keys, first, last):
    days = union_all(*[select(literal(midnight(first + timedelta(days=index))).label("day")) for index in range((last - first).days + 1)]).cte("schedule_days")
    day_end = days.c.day + timedelta(days=1)
    key = resource_key(base.c.equipment_id, base.c.org_id, base.c.work_center_name_snapshot, base.c.workstation_name_snapshot)
    minutes = func.extract("epoch", func.least(base.c.planned_end_at, day_end) - func.greatest(base.c.planned_start_at, days.c.day)) / 60
    return select(key.label("resource_key"), days.c.day, func.count(func.distinct(base.c.id)).label("task_count"), func.sum(minutes).label("planned_minutes")).select_from(
        base.join(days, and_(base.c.planned_start_at < day_end, base.c.planned_end_at > days.c.day))).where(key.in_(keys)).group_by(key, days.c.day)


class SchedulingRepository:
    async def projects(self, session, order_ids):
        if not order_ids: return {}
        rows = (await session.execute(select(MesWorkOrder.id, MesProductionOrder.project_name).outerjoin(MesProductionOrder,
            and_(MesProductionOrder.id == MesWorkOrder.production_order_id, MesProductionOrder.deleted_at.is_(None))).where(MesWorkOrder.id.in_(order_ids)))).all()
        return dict(rows)

    async def resources(self, session, query, user):
        base, resources = resource_queries(query, user)
        total = (await session.execute(select(func.count()).select_from(resources))).scalar_one()
        rows = (await session.execute(select(resources).order_by(resources.c.equipment_no, resources.c.org_id, resources.c.resource_key)
            .offset((query.page - 1) * query.page_size).limit(query.page_size))).mappings().all()
        items = [dict(row, daily_load=[]) for row in rows]
        equipment_ids = {row["equipment_id"] for row in items if row["equipment_id"]}
        if equipment_ids:
            bindings = (await session.execute(select(MesEquipmentProcess.equipment_id, MesProcess.process_name)
                .join(MesProcess, and_(MesProcess.id == MesEquipmentProcess.process_id, MesProcess.org_id == MesEquipmentProcess.org_id,
                    MesProcess.deleted_at.is_(None)))
                .join(MesEquipment, and_(MesEquipment.id == MesEquipmentProcess.equipment_id, MesEquipment.org_id == MesEquipmentProcess.org_id,
                    MesEquipment.deleted_at.is_(None)))
                .where(MesEquipmentProcess.equipment_id.in_(equipment_ids), MesEquipmentProcess.deleted_at.is_(None))
                .order_by(MesProcess.process_no, MesProcess.id))).all()
            names = {}
            for equipment_id, name in bindings:
                names.setdefault(equipment_id, []).append(name)
            for row in items:
                if row["equipment_id"] in names:
                    row["process_name"] = "、".join(dict.fromkeys(filter(None, [row["process_name"], *names[row["equipment_id"]]])))
        first = query.window_start or utc_now().astimezone(TZ).date() - timedelta(days=1)
        last = query.window_end or first + timedelta(days=7)
        if items:
            statement = daily_load_statement(base, [row["resource_key"] for row in items], first, last)
            loads = (await session.execute(statement)).mappings().all()
            by_key = {row["resource_key"]: row for row in items}
            for load in loads:
                by_key[load["resource_key"]]["daily_load"].append(dict(day=load["day"].astimezone(TZ).date().isoformat(),
                    task_count=load["task_count"], planned_minutes=float(load["planned_minutes"] or 0)))
        for row in items: row["planned_minutes"] = float(row["planned_minutes"] or 0)
        return dict(items=items, total=total, page=query.page, page_size=query.page_size, window_start=first, window_end=last)


scheduling_repository = SchedulingRepository()
