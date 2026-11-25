"""已授权工单内的首件/剩余批量及物理资源实际占用投影；不发布其他工单内容。"""
from sqlalchemy import and_, func, or_, select
from .models import MesOperationExecution,MesProductionReport,MesWorkOrderOperation
from .schedule_models import (MesOperationProductionPhase,MesWorkOrderFirstArticle,MesSchedulePlanOperation,
    MesSchedulePlan,MesSchedulePlanSegment,MesWorkOrderReadiness,MesOperationScheduleSetting)
from .workforce_models import MesProductionPerson,MesPersonProcess
from .calendar_models import MesResourceCalendar,MesResourceCalendarPeriod,MesResourceCalendarException
from .archive_models import MesEquipment,MesEquipmentProcess,MesProcess
from app.auth.scope_filters import scoped_conditions
from app.modules.masterdata.models import MdPerson,MdParty


class ExecutionRepository:
    async def process(self,session,identifier,org_id):
        return (await session.execute(select(MesProcess).where(MesProcess.id==identifier,MesProcess.org_id==org_id,
            MesProcess.deleted_at.is_(None),MesProcess.is_active.is_(True)))).scalars().first()

    async def can_inspect_operations(self,session,ids,user):
        # 返工会重开此前的工序，必须拥有全部受影响工序的质量范围，不能借当前可见工序越权。
        return set((await session.execute(select(MesWorkOrderOperation.id).where(MesWorkOrderOperation.id.in_(ids),
            *scoped_conditions(MesWorkOrderOperation,user,"mes:quality:inspect")))).scalars().all())==set(ids)

    async def rework_options(self,session,task,user):
        return (await session.execute(select(MesWorkOrderOperation.id,MesWorkOrderOperation.operation_name_snapshot)
            .where(MesWorkOrderOperation.work_order_id==task.work_order_id,MesWorkOrderOperation.sequence_no<=task.sequence_no,
                *scoped_conditions(MesWorkOrderOperation,user,"mes:quality:inspect"))
            .order_by(MesWorkOrderOperation.sequence_no))).all()

    async def phases(self,session,task_id):
        return (await session.execute(select(MesOperationProductionPhase,MesSchedulePlanOperation,MesSchedulePlan)
            .join(MesSchedulePlanOperation,MesSchedulePlanOperation.id==MesOperationProductionPhase.plan_operation_id)
            .join(MesSchedulePlan,MesSchedulePlan.id==MesSchedulePlanOperation.plan_id)
            .where(MesOperationProductionPhase.operation_id==task_id,MesOperationProductionPhase.deleted_at.is_(None),
                MesSchedulePlanOperation.is_active.is_(True),MesSchedulePlanOperation.deleted_at.is_(None),
                MesSchedulePlan.status_code=="applied",MesSchedulePlan.is_active.is_(True),MesSchedulePlan.deleted_at.is_(None))
            .order_by(MesOperationProductionPhase.production_phase_code))).all()

    async def order_phases(self,session,order_id):
        return (await session.execute(select(MesOperationProductionPhase,MesWorkOrderOperation)
            .join(MesWorkOrderOperation,MesWorkOrderOperation.id==MesOperationProductionPhase.operation_id)
            .where(MesOperationProductionPhase.work_order_id==order_id,MesOperationProductionPhase.deleted_at.is_(None),
                MesWorkOrderOperation.deleted_at.is_(None)).order_by(MesWorkOrderOperation.sequence_no))).all()

    async def gate(self,session,order_id):
        return (await session.execute(select(MesWorkOrderFirstArticle).where(MesWorkOrderFirstArticle.work_order_id==order_id,
            MesWorkOrderFirstArticle.deleted_at.is_(None)).with_for_update())).scalars().first()

    async def readiness(self,session,order_id):
        return (await session.execute(select(MesWorkOrderReadiness).where(MesWorkOrderReadiness.work_order_id==order_id,
            MesWorkOrderReadiness.deleted_at.is_(None),MesWorkOrderReadiness.is_active.is_(True)))).scalars().all()

    async def totals(self,session,phase_id):
        row=(await session.execute(select(func.coalesce(func.sum(MesProductionReport.good_quantity),0),
            func.coalesce(func.sum(MesProductionReport.scrap_quantity),0),func.coalesce(func.sum(MesProductionReport.rework_quantity),0))
            .join(MesOperationExecution,MesOperationExecution.id==MesProductionReport.execution_id)
            .where(MesOperationExecution.production_phase_id==phase_id,MesProductionReport.status_code=="posted"))).one()
        return tuple(row)

    async def report_phase(self,session,execution_id):
        return (await session.execute(select(MesOperationProductionPhase,MesOperationExecution)
            .join(MesOperationExecution,MesOperationExecution.production_phase_id==MesOperationProductionPhase.id)
            .where(MesOperationExecution.id==execution_id,MesOperationProductionPhase.deleted_at.is_(None)))).first()

    async def last_execution(self,session,phase_id):
        return (await session.execute(select(MesOperationExecution).where(MesOperationExecution.production_phase_id==phase_id,
            MesOperationExecution.tracked_out_at.is_not(None)).order_by(MesOperationExecution.tracked_out_at.desc(),MesOperationExecution.id.desc()).limit(1))).scalars().first()

    async def setting(self,session,task_id):
        return (await session.execute(select(MesOperationScheduleSetting).where(MesOperationScheduleSetting.operation_id==task_id,
            MesOperationScheduleSetting.deleted_at.is_(None)))).scalars().first()

    async def phase_segments(self,session,phase):
        return (await session.execute(select(MesSchedulePlanSegment).where(MesSchedulePlanSegment.plan_operation_id==phase.plan_operation_id,
            MesSchedulePlanSegment.production_phase_code==phase.production_phase_code,
            MesSchedulePlanSegment.deleted_at.is_(None)).order_by(MesSchedulePlanSegment.sequence_no))).scalars().all()

    async def person(self,session,identifier,org_id):
        return (await session.execute(select(MesProductionPerson,MdPerson.user_id)
            .join(MdPerson,MdPerson.party_id==MesProductionPerson.party_id).join(MdParty,MdParty.id==MdPerson.party_id)
            .where(MesProductionPerson.id==identifier,MesProductionPerson.org_id==org_id,MesProductionPerson.deleted_at.is_(None),
                MesProductionPerson.is_active.is_(True),MdPerson.deleted_at.is_(None),MdParty.deleted_at.is_(None),MdParty.is_active.is_(True)))).first()

    async def qualified(self,session,person,process_id,at):
        return (await session.execute(select(MesPersonProcess.id).where(MesPersonProcess.production_person_id==person.id,
            MesPersonProcess.org_id==person.org_id,MesPersonProcess.process_id==process_id,MesPersonProcess.is_active.is_(True),
            MesPersonProcess.deleted_at.is_(None),MesPersonProcess.valid_from<=at,
            or_(MesPersonProcess.valid_to.is_(None),MesPersonProcess.valid_to>at)))).first() is not None

    async def calendars(self,session,person,equipment_id):
        return (await session.execute(select(MesResourceCalendar).where(MesResourceCalendar.org_id==person.org_id,
            or_(MesResourceCalendar.production_person_id==person.id,MesResourceCalendar.equipment_id==equipment_id if equipment_id else False),
            MesResourceCalendar.is_active.is_(True),MesResourceCalendar.deleted_at.is_(None)))).scalars().all()

    async def calendar_rows(self,session,ids):
        result=[]
        for model in (MesResourceCalendarPeriod,MesResourceCalendarException):
            result.append((await session.execute(select(model).where(model.calendar_id.in_(ids),model.deleted_at.is_(None),model.is_active.is_(True)))).scalars().all())
        return result

    async def person_absences(self,session,party_id,at):
        return (await session.execute(select(MesResourceCalendarException.start_at,MesResourceCalendarException.end_at)
            .join(MesResourceCalendar,MesResourceCalendar.id==MesResourceCalendarException.calendar_id)
            .join(MesProductionPerson,MesProductionPerson.id==MesResourceCalendar.production_person_id)
            .where(MesProductionPerson.party_id==party_id,MesProductionPerson.deleted_at.is_(None),
                MesResourceCalendar.deleted_at.is_(None),MesResourceCalendar.is_active.is_(True),
                MesResourceCalendarException.deleted_at.is_(None),MesResourceCalendarException.is_active.is_(True),
                MesResourceCalendarException.exception_type_code=="unavailable",
                MesResourceCalendarException.start_at<=at,MesResourceCalendarException.end_at>at))).all()

    async def actual_occupancy(self,session,person,equipment_id,exclude_execution=None):
        p=MesProductionPerson
        return (await session.execute(select(MesOperationExecution,MesWorkOrderOperation,MesOperationScheduleSetting,p.party_id)
            .join(MesWorkOrderOperation,MesWorkOrderOperation.id==MesOperationExecution.operation_id)
            .outerjoin(p,p.id==MesOperationExecution.production_person_id)
            .outerjoin(MesOperationScheduleSetting,and_(MesOperationScheduleSetting.operation_id==MesOperationExecution.operation_id,
                MesOperationScheduleSetting.deleted_at.is_(None)))
            .where(MesOperationExecution.tracked_out_at.is_(None),MesOperationExecution.id!=exclude_execution if exclude_execution else True,
                or_(MesOperationExecution.segment_type_code.is_(None),MesOperationExecution.segment_type_code.notin_(["external_wait","external_return"])),
                or_(p.party_id==person.party_id,and_(MesOperationExecution.production_person_id.is_(None),MesOperationExecution.worker_user_id.in_(
                    select(MdPerson.user_id).where(MdPerson.party_id==person.party_id,MdPerson.user_id.is_not(None)))),
                    MesOperationExecution.equipment_id==equipment_id if equipment_id else False,
                    MesWorkOrderOperation.equipment_id==equipment_id if equipment_id else False)))).all()

    async def equipment(self,session,identifier,org_id,process_id):
        return (await session.execute(select(MesEquipment).where(MesEquipment.id==identifier,MesEquipment.org_id==org_id,
            MesEquipment.is_active.is_(True),MesEquipment.deleted_at.is_(None),select(MesEquipmentProcess.id).where(
                MesEquipmentProcess.equipment_id==MesEquipment.id,MesEquipmentProcess.process_id==process_id,
                MesEquipmentProcess.org_id==org_id,MesEquipmentProcess.is_active.is_(True),MesEquipmentProcess.deleted_at.is_(None)).exists()))).scalars().first()

    async def manual_plan_conflict(self,session,task,change):
        active=and_(MesSchedulePlan.status_code=="applied",MesSchedulePlan.is_active.is_(True),MesSchedulePlan.deleted_at.is_(None),
            MesSchedulePlanOperation.is_active.is_(True),MesSchedulePlanOperation.deleted_at.is_(None))
        owned=(await session.execute(select(MesSchedulePlanOperation.id).join(MesSchedulePlan,MesSchedulePlan.id==MesSchedulePlanOperation.plan_id)
            .where(MesSchedulePlanOperation.operation_id==task.id,active))).first()
        if owned:return "该工序已应用自动排程，请通过排程方案重排，不能用人工总跨度覆盖阶段安排"
        if not change.planned_start_at or not change.planned_end_at:return None
        equipment=change.equipment_id if "equipment_id" in change.model_fields_set else task.equipment_id
        parties = self.manual_person_parties(task)
        people = select(MesProductionPerson.id).where(MesProductionPerson.party_id.in_(parties))
        match=or_(MesSchedulePlanSegment.equipment_id==equipment if equipment else False,MesSchedulePlanSegment.production_person_id.in_(people))
        busy=(await session.execute(select(MesSchedulePlanSegment.id)
            .join(MesSchedulePlanOperation,MesSchedulePlanOperation.id==MesSchedulePlanSegment.plan_operation_id)
            .join(MesSchedulePlan,MesSchedulePlan.id==MesSchedulePlanOperation.plan_id)
            .where(active,match,MesSchedulePlanSegment.deleted_at.is_(None),MesSchedulePlanSegment.is_active.is_(True),
                MesSchedulePlanSegment.planned_start_at<change.planned_end_at,MesSchedulePlanSegment.planned_end_at>change.planned_start_at))).first()
        return "人工计划与已应用自动方案的人机占用冲突，请调整时间或重新排程" if busy else None

    @staticmethod
    def manual_person_parties(task):
        if assigned := getattr(task, "assigned_production_person_id", None):
            return select(MesProductionPerson.party_id).where(MesProductionPerson.id == assigned)
        return select(MdPerson.party_id).where(
            MdPerson.user_id == task.assigned_user_id if task.assigned_user_id else False,
            MdPerson.deleted_at.is_(None),
        )

    async def manual_resources(self,session,task,change):
        people=(await session.execute(self.manual_person_parties(task))).scalars().all()
        equipment=change.equipment_id if "equipment_id" in change.model_fields_set else task.equipment_id
        return people,[equipment] if equipment else []

    def add(self,session,row):session.add(row)


repository=ExecutionRepository()
