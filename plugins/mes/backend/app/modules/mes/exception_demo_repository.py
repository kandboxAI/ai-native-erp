"""显式异常演示数据的最小数据访问；不修改工单、人员、库存或权限。"""
from sqlalchemy import and_, func, or_, select, text
from app.modules.user_profile.models import SysUser
from .models import MesWorkOrder, MesWorkOrderOperation
from .exception_models import MesExceptionCase, MesExceptionEvent


class ExceptionDemoRepository:
    async def ready(self, session):
        columns=set((await session.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all())
        models=(MesExceptionCase,MesExceptionEvent)
        missing=[f"{model.__tablename__}.{column.name}" for model in models for column in model.__table__.columns if (model.__tablename__,column.name) not in columns]
        if missing: raise RuntimeError("异常表尚未迁移，未写入数据；请先审核并执行 MES 迁移。缺少："+"、".join(missing))

    async def orders(self, session, org_id=None, work_order_no=None):
        conditions=[MesWorkOrder.deleted_at.is_(None),MesWorkOrder.status_code!="cancelled"]
        if org_id: conditions.append(MesWorkOrder.org_id==org_id)
        if work_order_no: conditions.append(MesWorkOrder.work_order_no==work_order_no)
        else: conditions.append(or_(MesWorkOrder.work_order_no.like("MO-MES-DEMO-%"),MesWorkOrder.work_order_no.like("MO-DEMO-%")))
        return (await session.execute(select(MesWorkOrder).where(*conditions).order_by(MesWorkOrder.work_order_no,MesWorkOrder.id))).scalars().all()

    async def users(self, session, org_id):
        return (await session.execute(select(SysUser.id).where(SysUser.org_id==org_id,SysUser.is_active.is_(True),SysUser.deleted_at.is_(None))
            .order_by(SysUser.created_at,SysUser.id).limit(10))).scalars().all()

    async def operations(self, session, org_id, order_ids):
        result={}
        rows=(await session.execute(select(MesWorkOrderOperation.work_order_id,MesWorkOrderOperation.id).where(
            MesWorkOrderOperation.org_id==org_id,MesWorkOrderOperation.work_order_id.in_(order_ids),MesWorkOrderOperation.deleted_at.is_(None)
        ).order_by(MesWorkOrderOperation.sequence_no,MesWorkOrderOperation.id))).all()
        for order_id,identifier in rows: result.setdefault(order_id,identifier)
        return result

    async def existing(self, session, org_id, numbers):
        return {row.case_no:row for row in (await session.execute(select(MesExceptionCase).where(MesExceptionCase.org_id==org_id,
            MesExceptionCase.case_no.in_(numbers)))).scalars().all()}

    async def lock(self, session, schema, org_id):
        locked=(await session.execute(select(func.pg_try_advisory_xact_lock(func.hashtextextended(f"mes.exception-demo:{schema}:{org_id}",0))))).scalar_one()
        if not locked: raise RuntimeError("该租户组织的异常演示脚本正在执行，请稍后重试")

    async def counts(self, session, org_id, marker):
        condition=and_(MesExceptionCase.org_id==org_id,MesExceptionCase.flex_form["seed_key"].as_string()==marker)
        statuses=dict((await session.execute(select(MesExceptionCase.status_code,func.count()).where(condition)
            .group_by(MesExceptionCase.status_code))).all())
        identifiers=select(MesExceptionCase.id).where(condition)
        events=(await session.execute(select(func.count()).select_from(MesExceptionEvent).where(
            MesExceptionEvent.org_id==org_id,MesExceptionEvent.case_id.in_(identifiers)))).scalar_one()
        return dict(cases=sum(statuses.values()),events=events,statuses=statuses)

    @staticmethod
    def add(session,row): session.add(row)


exception_demo_repository=ExceptionDemoRepository()
