from sqlalchemy import or_, select, update

from .models import MesProductionReport, MesWorkOrder
from .process_change_models import MesWorkOrderProcessChange as Change


class ProcessChangeRepository:
    async def list(self, session, order):
        statement = select(Change).where(Change.work_order_id == order.id, Change.org_id == order.org_id)
        return (await session.execute(statement.order_by(Change.created_at.desc(), Change.id.desc()))).scalars().all()

    async def get(self, session, identifier, *, lock=False):
        statement = select(Change).where(Change.id == identifier).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    async def preserve_report_names(self, session, task):
        await session.execute(update(MesProductionReport).where(
            MesProductionReport.operation_id == task.id, MesProductionReport.org_id == task.org_id,
            MesProductionReport.operation_name_snapshot.is_(None),
        ).values(operation_name_snapshot=task.operation_name_snapshot))

    async def previous_standard_minutes(self, session, change):
        """查找同一道工序切回原工艺时可沿用的最近工时。"""
        configuration = Change.previous_configuration_snapshot
        minutes = configuration["standard_minutes_per_unit"].as_string()
        equipment = configuration["equipment_id"].as_string()
        statement = (
            select(minutes)
            .where(
                Change.org_id == change.org_id,
                Change.work_order_id == change.work_order_id,
                Change.operation_id == change.operation_id,
                Change.previous_process_id == change.new_process_id,
                Change.status_code == "applied",
                minutes.is_not(None),
                or_(equipment.is_(None), equipment == str(change.new_equipment_id)),
            )
            .order_by(Change.applied_at.desc(), Change.id.desc())
            .limit(1)
        )
        return (await session.execute(statement)).scalar_one_or_none()

    async def repair(self, session, change):
        statement = select(MesWorkOrder).where(MesWorkOrder.id == change.repair_order_id,
            MesWorkOrder.org_id == change.org_id, MesWorkOrder.source_work_order_id == change.work_order_id,
            MesWorkOrder.is_process_change_repair.is_(True), MesWorkOrder.deleted_at.is_(None))
        return (await session.execute(statement.with_for_update())).scalar_one_or_none()

    async def repair_has_returned(self, session, repair_id):
        reference = select(Change.id).where(Change.repair_order_id == repair_id, Change.status_code == "applied")
        return (await session.execute(select(reference.exists()))).scalar_one()


process_change_repository = ProcessChangeRepository()
