"""生产管理查询：工序计划、工艺模板和返工报工处理；只操作当前租户。"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, or_, select

from .models import (
    MesProcessTemplate, MesProcessTemplateOperation, MesProductionReport,
    MesReworkAssignment, MesWorkOrder, MesWorkOrderOperation,
)
from .repository import _org_conditions
from .scheduling_repository import schedule_statement, work_order_schedule_queries
from .archive_models import MesEquipment


class ProductionRepository:
    @staticmethod
    async def page(session, statement, query, *order):
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.exec(statement.order_by(*order).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

    async def schedules(self, session, query, user):
        if query.group_by_work_order:
            count, statement = work_order_schedule_queries(query, user)
            total = (await session.execute(count)).scalar_one()
            return (await session.exec(statement)).all(), total
        statement = schedule_statement(query, user)
        return await self.page(session, statement, query, MesWorkOrderOperation.planned_start_at.nulls_last(), MesWorkOrder.work_order_no, MesWorkOrderOperation.sequence_no, MesWorkOrderOperation.id)

    async def schedule_parents(self, session, ids, user):
        statement = select(MesWorkOrderOperation.id, MesWorkOrderOperation.work_order_id).join(MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).where(
            MesWorkOrderOperation.id.in_(ids), *_org_conditions(MesWorkOrderOperation, user, "mes:schedule:manage"), MesWorkOrder.deleted_at.is_(None))
        return dict((await session.execute(statement)).all())

    async def lock_workstations(self, session, keys):
        # Transaction-scoped advisory locks serialize different orders using the same named station.
        for key in sorted(set(keys)):
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))

    async def lock_schedule_equipment(self, session, requests):
        from sqlalchemy import and_
        requests = [(org_id, identifier) for org_id, identifier in requests if identifier]
        if requests:
            conditions = or_(*(and_(MesEquipment.org_id == org_id, MesEquipment.id == identifier) for org_id, identifier in requests))
            # FOR SHARE keeps activation/process metadata stable while allowing concurrent readers.
            await session.execute(select(MesEquipment.id).where(conditions, MesEquipment.deleted_at.is_(None))
                .order_by(MesEquipment.id).with_for_update(read=True))

    async def station_conflict(self, session, task, start, end, excluded):
        from sqlalchemy import and_
        same_station = and_(func.trim(func.coalesce(MesWorkOrderOperation.work_center_name_snapshot, "")) == (task.work_center_name_snapshot or "").strip(),
            func.trim(func.coalesce(MesWorkOrderOperation.workstation_name_snapshot, "")) == (task.workstation_name_snapshot or "").strip())
        match = or_(MesWorkOrderOperation.equipment_id == task.equipment_id, same_station) if getattr(task, "equipment_id", None) else same_station
        statement = select(exists(select(MesWorkOrderOperation.id).join(MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).where(
            MesWorkOrderOperation.org_id == task.org_id,
            match,
            MesWorkOrderOperation.id.notin_(excluded), MesWorkOrderOperation.deleted_at.is_(None), MesWorkOrder.deleted_at.is_(None),
            MesWorkOrderOperation.status_code.notin_(["completed", "cancelled"]), MesWorkOrder.status_code.notin_(["completed", "cancelled"]),
            MesWorkOrderOperation.planned_start_at < end, MesWorkOrderOperation.planned_end_at > start,
        )))
        # Intentionally returns only existence, never another user's order or personnel.
        return (await session.execute(statement)).scalar_one()

    async def templates(self, session, query, user, permission="mes:process_template:list"):
        conditions = [*_org_conditions(MesProcessTemplate, user, permission)]
        if query.org_id:
            conditions.append(MesProcessTemplate.org_id == query.org_id)
        if query.product_item_id:
            conditions.append(or_(MesProcessTemplate.product_item_id == query.product_item_id, MesProcessTemplate.product_item_id.is_(None)))
        if query.is_active is not None:
            conditions.append(MesProcessTemplate.is_active == query.is_active)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(MesProcessTemplate.template_no.ilike(word), MesProcessTemplate.template_name.ilike(word)))
        rows, total = await self.page(session, select(MesProcessTemplate).where(*conditions), query, MesProcessTemplate.updated_at.desc(), MesProcessTemplate.id)
        return [row[0] for row in rows], total

    async def template(self, session, template_id, user, permission="mes:process_template:list", *, lock=False):
        statement = select(MesProcessTemplate).where(MesProcessTemplate.id == template_id, *_org_conditions(MesProcessTemplate, user, permission)).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def template_operations(self, session, template_id):
        return (await session.execute(select(MesProcessTemplateOperation).where(MesProcessTemplateOperation.template_id == template_id,
            MesProcessTemplateOperation.deleted_at.is_(None)).order_by(MesProcessTemplateOperation.sequence_no))).scalars().all()

    async def template_no_exists(self, session, org_id, number, exclude=None):
        conditions = [MesProcessTemplate.org_id == org_id, MesProcessTemplate.template_no == number, MesProcessTemplate.deleted_at.is_(None)]
        if exclude:
            conditions.append(MesProcessTemplate.id != exclude)
        return bool((await session.execute(select(exists(select(MesProcessTemplate.id).where(*conditions))))).scalar_one())

    def rework_statement(self, user):
        return select(MesProductionReport, MesWorkOrderOperation, MesWorkOrder).join(MesWorkOrderOperation, MesWorkOrderOperation.id == MesProductionReport.operation_id).join(
            MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).where(
            *_org_conditions(MesProductionReport, user, "mes:production_report:list"),
            MesWorkOrderOperation.deleted_at.is_(None), MesWorkOrder.deleted_at.is_(None),
            MesProductionReport.rework_quantity > 0, MesProductionReport.status_code != "reversed")

    async def rework_report(self, session, report_id, user):
        return (await session.execute(self.rework_statement(user).where(MesProductionReport.id == report_id))).first()

    def assignments_statement(self, report_ids):
        return select(MesReworkAssignment.report_id, MesWorkOrder).join(MesWorkOrder, MesWorkOrder.id == MesReworkAssignment.work_order_id).where(
            MesReworkAssignment.report_id.in_(report_ids), MesWorkOrder.deleted_at.is_(None), MesWorkOrder.status_code != "cancelled")

    async def allocated_quantity(self, session, report_id):
        rows = (await session.execute(self.assignments_statement([report_id]))).all()
        return sum((row[1].planned_quantity for row in rows), 0)

    async def reworks(self, session, query, user):
        allocated = select(func.coalesce(func.sum(MesWorkOrder.planned_quantity), 0)).join(MesReworkAssignment, MesWorkOrder.id == MesReworkAssignment.work_order_id).where(
            MesReworkAssignment.report_id == MesProductionReport.id, MesWorkOrder.deleted_at.is_(None), MesWorkOrder.status_code != "cancelled").correlate(MesProductionReport).scalar_subquery()
        statement = self.rework_statement(user)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            statement = statement.where(or_(MesProductionReport.report_no.ilike(word), MesWorkOrder.work_order_no.ilike(word), MesWorkOrder.product_item_name_snapshot.ilike(word), MesWorkOrderOperation.operation_name_snapshot.ilike(word)))
        if query.allocation == "pending": statement = statement.where(allocated == 0)
        if query.allocation == "partial": statement = statement.where(allocated > 0, allocated < MesProductionReport.rework_quantity)
        if query.allocation == "allocated": statement = statement.where(allocated >= MesProductionReport.rework_quantity)
        rows, total = await self.page(session, statement, query, MesProductionReport.reported_at.desc(), MesProductionReport.id)
        links = (await session.execute(self.assignments_statement([row[0].id for row in rows]))).all() if rows else []
        # Associated order details are separately scope-filtered; amounts can be returned as aggregates only.
        visible = (await session.execute(select(MesWorkOrder.id).where(*_org_conditions(MesWorkOrder, user, "mes:work_order:list"),
            MesWorkOrder.id.in_([row[1].id for row in links])))).scalars().all() if links and "mes:work_order:list" in user.permissions else []
        return rows, links, set(visible), total


production_repository = ProductionRepository()
