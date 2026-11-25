from sqlalchemy import and_, func, or_, select
from app.auth.scope_filters import scoped_conditions
from .models import MesWorkOrder, MesWorkOrderOperation
from .schedule_models import (MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment,
    MesOperationScheduleSetting, MesWorkOrderReadiness, MesWorkOrderInspectionSetting,
    MesOperationProductionPhase, MesWorkOrderFirstArticle)
from .workforce_models import MesProductionPerson
from .archive_models import MesEquipment


class PlanRepository:
    async def lock_resources(self,session,party_ids,equipment_ids):
        # 同一自然人可能跨组织任职；组织锁不足以保护其两机容量，使用一致的物理资源锁序。
        from sqlalchemy import func,select
        keys={f"mes.resource.person:{p}" for p in party_ids if p}|{f"mes.resource.equipment:{e}" for e in equipment_ids if e}
        for key in sorted(keys):await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key,0))))

    async def lock_orders(self, session, ids, user, permission):
        return (await session.execute(select(MesWorkOrder).where(MesWorkOrder.id.in_(ids),
            *scoped_conditions(MesWorkOrder, user, permission)).order_by(MesWorkOrder.id).with_for_update())).scalars().all()

    async def lock_tasks(self, session, ids, user, permission):
        return (await session.execute(select(MesWorkOrderOperation).where(MesWorkOrderOperation.work_order_id.in_(ids),
            *scoped_conditions(MesWorkOrderOperation, user, permission)).order_by(MesWorkOrderOperation.work_order_id,
                MesWorkOrderOperation.sequence_no, MesWorkOrderOperation.id).with_for_update())).scalars().all()

    async def get(self, session, identifier, user, permission, lock=False):
        statement = select(MesSchedulePlan).where(MesSchedulePlan.id == identifier,
            *scoped_conditions(MesSchedulePlan, user, permission))
        if lock: statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def page(self, session, query, user):
        conditions = scoped_conditions(MesSchedulePlan, user, "mes:schedule:list")
        if query.org_id: conditions.append(MesSchedulePlan.org_id == query.org_id)
        if query.status_code: conditions.append(MesSchedulePlan.status_code == query.status_code)
        if query.keyword:
            word=f"%{query.keyword.strip()}%"
            conditions.append(or_(MesSchedulePlan.plan_no.ilike(word), MesSchedulePlan.plan_name.ilike(word)))
        statement=select(MesSchedulePlan).where(*conditions)
        count=(await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows=(await session.execute(statement.order_by(MesSchedulePlan.created_at.desc(),MesSchedulePlan.id)
            .offset((query.page-1)*query.page_size).limit(query.page_size))).scalars().all()
        return rows,count

    async def operations(self, session, plan, user, permission):
        return (await session.execute(select(MesSchedulePlanOperation,MesWorkOrderOperation,MesWorkOrder)
            .join(MesWorkOrderOperation,MesWorkOrderOperation.id==MesSchedulePlanOperation.operation_id)
            .join(MesWorkOrder,MesWorkOrder.id==MesSchedulePlanOperation.work_order_id)
            .where(MesSchedulePlanOperation.plan_id==plan.id,MesSchedulePlanOperation.org_id==plan.org_id,
                *scoped_conditions(MesSchedulePlanOperation,user,permission),
                *scoped_conditions(MesWorkOrderOperation,user,permission),*scoped_conditions(MesWorkOrder,user,permission))
            .order_by(MesWorkOrder.work_order_no,MesWorkOrderOperation.sequence_no))).all()

    async def operation_count(self,session,plan):
        return (await session.execute(select(func.count()).select_from(MesSchedulePlanOperation)
            .where(MesSchedulePlanOperation.plan_id==plan.id,MesSchedulePlanOperation.deleted_at.is_(None)))).scalar_one()

    async def segments(self, session, operation_ids):
        # 仅在公开动作已完整校验父方案及所有工序权限后调用，按真实FK限定，不扩大源业务范围。
        return (await session.execute(select(MesSchedulePlanSegment).where(
            MesSchedulePlanSegment.plan_operation_id.in_(operation_ids),MesSchedulePlanSegment.deleted_at.is_(None))
            .order_by(MesSchedulePlanSegment.planned_start_at,MesSchedulePlanSegment.sequence_no))).scalars().all()

    async def source_extension(self, session, model, field, identifier, user, lock=False):
        statement=select(model).where(getattr(model,field)==identifier,*scoped_conditions(model,user,"mes:schedule:manage"))
        if lock: statement=statement.with_for_update()
        return (await session.execute(statement)).scalars().all()

    async def equipment_names(self, session, org_id, equipment_ids):
        if not equipment_ids:
            return {}
        rows = (await session.execute(select(MesEquipment.id, MesEquipment.equipment_name).where(
            MesEquipment.org_id == org_id, MesEquipment.id.in_(equipment_ids), MesEquipment.deleted_at.is_(None),
        ))).all()
        return dict(rows)

    async def resource_mapping(self, session, org_id, party_ids, equipment_ids):
        people=(await session.execute(select(MesProductionPerson).where(MesProductionPerson.org_id==org_id,
            MesProductionPerson.party_id.in_(party_ids),MesProductionPerson.deleted_at.is_(None),MesProductionPerson.is_active.is_(True)))).scalars().all()
        equipment=(await session.execute(select(MesEquipment).where(MesEquipment.org_id==org_id,
            MesEquipment.id.in_(equipment_ids),MesEquipment.deleted_at.is_(None),MesEquipment.is_active.is_(True)))).scalars().all()
        return {str(p.party_id):p for p in people},{str(e.id):e for e in equipment}

    async def active_source_plans(self,session,operation_ids):
        return (await session.execute(select(MesSchedulePlanOperation,MesSchedulePlan)
            .join(MesSchedulePlan,MesSchedulePlan.id==MesSchedulePlanOperation.plan_id)
            .where(MesSchedulePlanOperation.operation_id.in_(operation_ids),MesSchedulePlanOperation.is_active.is_(True),
                MesSchedulePlanOperation.deleted_at.is_(None),MesSchedulePlan.status_code=="applied",
                MesSchedulePlan.is_active.is_(True),MesSchedulePlan.deleted_at.is_(None))
            .order_by(MesSchedulePlanOperation.id).with_for_update())).all()

    async def active_plan_operation_count(self,session,plan_id):
        return (await session.execute(select(func.count()).select_from(MesSchedulePlanOperation).where(
            MesSchedulePlanOperation.plan_id==plan_id,MesSchedulePlanOperation.is_active.is_(True),MesSchedulePlanOperation.deleted_at.is_(None)))).scalar_one()

    async def phases(self,session,operation_ids):
        return (await session.execute(select(MesOperationProductionPhase).where(
            MesOperationProductionPhase.operation_id.in_(operation_ids),MesOperationProductionPhase.deleted_at.is_(None))
            .order_by(MesOperationProductionPhase.operation_id,MesOperationProductionPhase.production_phase_code).with_for_update())).scalars().all()

    async def first_articles(self,session,order_ids):
        return (await session.execute(select(MesWorkOrderFirstArticle).where(MesWorkOrderFirstArticle.work_order_id.in_(order_ids),
            MesWorkOrderFirstArticle.deleted_at.is_(None)).with_for_update())).scalars().all()

    async def readiness(self,session,order_ids,user,permission):
        return (await session.execute(select(MesWorkOrderReadiness).where(MesWorkOrderReadiness.work_order_id.in_(order_ids),
            *scoped_conditions(MesWorkOrderReadiness,user,permission)))).scalars().all()

    def add(self,session,row):session.add(row)


repository=PlanRepository()
