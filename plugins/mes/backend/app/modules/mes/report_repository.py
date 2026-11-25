"""报工详情、冻结检查及变更申请持久化；范围以报工/申请自身的动作人计算。"""
from sqlalchemy import exists, func, or_, select

from .models import MesProductionReport, MesProductionReportChange, MesWorkOrder, MesWorkOrderOperation, MesOperationExecution
from .repository import _org_conditions


class ReportRepository:
    def report_query(self, report_id, user=None, permission="mes:production_report:list"):
        conditions = [MesProductionReport.id == report_id, MesWorkOrder.deleted_at.is_(None), MesWorkOrderOperation.deleted_at.is_(None)]
        if user is not None:
            conditions.extend(_org_conditions(MesProductionReport, user, permission))
        return select(MesProductionReport, MesWorkOrderOperation, MesWorkOrder).join(MesWorkOrderOperation, MesWorkOrderOperation.id == MesProductionReport.operation_id).join(
            MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).where(*conditions)

    async def report(self, session, report_id, user=None, permission="mes:production_report:list", *, lock=False):
        statement = self.report_query(report_id, user, permission)
        if lock:
            parent = (await session.execute(statement)).first()
            if parent is None: return None
            # Every production writer locks the parent first, including workflow callbacks.
            await session.execute(select(MesWorkOrder.id).where(MesWorkOrder.id == parent[2].id).with_for_update())
            statement = statement.with_for_update(of=(MesProductionReport, MesWorkOrderOperation)).execution_options(populate_existing=True)
        return (await session.execute(statement)).first()

    async def pending_for_order(self, session, order_id):
        statement = select(exists(select(MesProductionReportChange.id).join(MesProductionReport, MesProductionReport.id == MesProductionReportChange.report_id).join(
            MesWorkOrderOperation, MesWorkOrderOperation.id == MesProductionReport.operation_id).where(
            MesWorkOrderOperation.work_order_id == order_id, MesProductionReportChange.status_code.in_(["draft", "submitted"]))))
        return bool((await session.execute(statement)).scalar_one())

    async def downstream_history(self, session, task):
        later = select(MesWorkOrderOperation.id).where(MesWorkOrderOperation.work_order_id == task.work_order_id, MesWorkOrderOperation.sequence_no > task.sequence_no)
        return bool((await session.execute(select(or_(
            exists(select(MesOperationExecution.id).where(MesOperationExecution.operation_id.in_(later))),
            exists(select(MesProductionReport.id).where(MesProductionReport.operation_id.in_(later))),
        )))).scalar_one())

    async def execution(self, session, execution_id):
        if not execution_id: return None
        return (await session.execute(select(MesOperationExecution).where(MesOperationExecution.id == execution_id).with_for_update())).scalars().first()

    async def change(self, session, change_id, user=None, permission="mes:production_report:change", *, lock=False):
        conditions = [MesProductionReportChange.id == change_id]
        if user: conditions.extend(_org_conditions(MesProductionReportChange, user, permission))
        statement = select(MesProductionReportChange).where(*conditions).execution_options(populate_existing=True)
        if lock: statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def by_idempotency(self, session, user_id, key):
        return (await session.execute(select(MesProductionReportChange).where(MesProductionReportChange.created_by == user_id,
            MesProductionReportChange.idempotency_key == key))).scalars().first()

    async def changes(self, session, query, user):
        conditions = [*_org_conditions(MesProductionReportChange, user, "mes:production_report:change:list")]
        if query.status_code: conditions.append(MesProductionReportChange.status_code == query.status_code)
        if query.report_id: conditions.append(MesProductionReportChange.report_id == query.report_id)
        if query.keyword: conditions.append(MesProductionReport.report_no.ilike(f"%{query.keyword.strip()}%"))
        statement = select(MesProductionReportChange, MesProductionReport.report_no).join(MesProductionReport, MesProductionReport.id == MesProductionReportChange.report_id).where(*conditions)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(MesProductionReportChange.created_at.desc(), MesProductionReportChange.id).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total


report_repository = ReportRepository()
