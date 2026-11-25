from sqlalchemy import select, func, or_
from app.auth.scope_filters import scoped_conditions
from .models import MesWorkOrder, MesWorkOrderOperation, MesOperationExecution
from .quality_models import MesQualityInspection
from .schedule_models import MesOperationProductionPhase


class QualityRepository:
    async def tasks(self, session, query, user):
        conditions = [*scoped_conditions(MesWorkOrderOperation, user, "mes:quality:list"),
            MesWorkOrder.deleted_at.is_(None), or_(MesWorkOrderOperation.is_quality_required.is_(True),select(MesOperationProductionPhase.id).where(
                MesOperationProductionPhase.operation_id==MesWorkOrderOperation.id,MesOperationProductionPhase.deleted_at.is_(None),
                MesOperationProductionPhase.status_code=="waiting_quality").exists())]
        if query.status_code:
            conditions.append(MesWorkOrderOperation.status_code == query.status_code)
        if query.keyword and query.keyword.strip():
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(MesWorkOrder.work_order_no.ilike(word), MesWorkOrder.product_item_name_snapshot.ilike(word),
                MesWorkOrder.product_item_no_snapshot.ilike(word), MesWorkOrderOperation.operation_name_snapshot.ilike(word)))
        statement = select(MesWorkOrderOperation, MesWorkOrder).join(MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).where(*conditions)
        total = (await session.exec(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.exec(statement.order_by(MesWorkOrderOperation.updated_at.desc(), MesWorkOrderOperation.id)
            .offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

    async def by_key(self, session, user_id, key):
        return (await session.exec(select(MesQualityInspection).where(MesQualityInspection.created_by == user_id,
            MesQualityInspection.idempotency_key == key))).scalars().one_or_none()

    async def history(self, session, operation_id):
        return (await session.exec(select(MesQualityInspection).where(MesQualityInspection.operation_id == operation_id)
            .order_by(MesQualityInspection.created_at.desc(), MesQualityInspection.id.desc()).limit(100))).scalars().all()

    async def last_execution(self, session, operation_id):
        return (await session.exec(select(MesOperationExecution).where(MesOperationExecution.operation_id == operation_id,
            MesOperationExecution.status_code == "completed", MesOperationExecution.tracked_out_at.is_not(None))
            .order_by(MesOperationExecution.tracked_out_at.desc(), MesOperationExecution.id.desc()).limit(1))).scalars().first()

    def add(self, session, row):
        session.add(row)


quality_repository = QualityRepository()
