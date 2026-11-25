"""只读试排快照。

资料投影遵循排程管理范围，任务和父工单分别校验。资源冲突投影是显式的内部
占用契约：同租户其他范围仅返回候选物理资源的时间/未知占用标记，不返回来源
工单、客户、人员或组织详情；不允许因为不可见而将资源判为空闲。
"""
from sqlalchemy import and_, exists, literal, or_, select, text,case,func

from app.auth.scope_filters import scoped_conditions
from app.modules.masterdata.models import MdParty, MdPerson
from .archive_models import MesEquipment, MesEquipmentProcess, MesProcess, MesProcessDependency
from .calendar_models import MesResourceCalendar, MesResourceCalendarPeriod, MesResourceCalendarException
from .models import (MesOperationExecution, MesProductionReport, MesWorkOrder,
                     MesWorkOrderOperation)
from .workforce_models import MesProductionPerson, MesPersonProcess
from .schedule_models import (MesOperationScheduleSetting, MesWorkOrderReadiness, MesWorkOrderInspectionSetting,
    MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment, MesOperationProductionPhase, MesWorkOrderFirstArticle)

PERMISSION = "mes:schedule:manage"


class TrialRepository:
    async def snapshot(self, session, scope, user, *, readonly=True):
        # 同一快照内多次读取保持一致；退出只读事务后才开始CPU求解。
        if readonly and session.bind.dialect.name == "postgresql":
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        orders = (await session.execute(select(MesWorkOrder).where(
            MesWorkOrder.id.in_(scope.work_order_ids), MesWorkOrder.org_id == scope.org_id,
            *scoped_conditions(MesWorkOrder, user, PERMISSION)))).scalars().all()
        ids = [o.id for o in orders]
        # 整单齐套仅投影完整性布尔值；未授权/未选的同项目货品不能被假设已完工。
        incomplete_projects=set((await session.execute(select(MesWorkOrder.production_order_id).where(
            MesWorkOrder.production_order_id.in_([o.production_order_id for o in orders if o.production_order_id]),
            MesWorkOrder.id.notin_(ids),MesWorkOrder.deleted_at.is_(None),MesWorkOrder.status_code!="cancelled"))).scalars().all())
        tasks = (await session.execute(select(MesWorkOrderOperation).where(
            MesWorkOrderOperation.work_order_id.in_(ids), MesWorkOrderOperation.org_id == scope.org_id,
            *scoped_conditions(MesWorkOrderOperation, user, PERMISSION))
            .order_by(MesWorkOrderOperation.work_order_id, MesWorkOrderOperation.sequence_no, MesWorkOrderOperation.id))).scalars().all()
        # 不可见工序不泄露内容，但必须拒绝把残缺路线当完整路线。
        task_ids = [t.id for t in tasks]
        configurations = {}
        for key, model, condition in (("settings", MesOperationScheduleSetting, MesOperationScheduleSetting.operation_id.in_(task_ids)),
                ("readiness", MesWorkOrderReadiness, MesWorkOrderReadiness.work_order_id.in_(ids)),
                ("inspection_settings", MesWorkOrderInspectionSetting, MesWorkOrderInspectionSetting.work_order_id.in_(ids))):
            configurations[key] = (await session.execute(select(model).where(condition, model.org_id == scope.org_id,
                *scoped_conditions(model, user, PERMISSION)))).scalars().all()
        hidden_route = bool((await session.execute(select(exists().where(
            MesWorkOrderOperation.work_order_id.in_(ids), MesWorkOrderOperation.deleted_at.is_(None),
            MesWorkOrderOperation.id.notin_(task_ids))))).scalar())
        facts = set()
        for entity in (MesOperationExecution, MesProductionReport):
            facts.update((await session.execute(select(entity.operation_id).where(
                entity.operation_id.in_(task_ids)))).scalars().all())
        phases=(await session.execute(select(MesOperationProductionPhase).where(MesOperationProductionPhase.operation_id.in_(task_ids),
            *scoped_conditions(MesOperationProductionPhase,user,PERMISSION)))).scalars().all()
        gates=(await session.execute(select(MesWorkOrderFirstArticle).where(MesWorkOrderFirstArticle.work_order_id.in_(ids),
            *scoped_conditions(MesWorkOrderFirstArticle,user,PERMISSION)))).scalars().all()
        execution_facts=(await session.execute(select(MesOperationExecution.operation_id,MesOperationExecution.production_phase_id,MesOperationExecution.tracked_out_at)
            .where(MesOperationExecution.operation_id.in_(task_ids)))).all()
        fixed_people=(await session.execute(select(MesSchedulePlanOperation.operation_id,MesProductionPerson.party_id)
            .join(MesSchedulePlan,MesSchedulePlan.id==MesSchedulePlanOperation.plan_id)
            .join(MesProductionPerson,MesProductionPerson.id==MesSchedulePlanOperation.production_person_id)
            .where(MesSchedulePlanOperation.operation_id.in_(task_ids),MesSchedulePlanOperation.deleted_at.is_(None),MesSchedulePlanOperation.is_active.is_(True),
                MesSchedulePlan.status_code=="applied",MesSchedulePlan.is_active.is_(True),MesSchedulePlan.deleted_at.is_(None)))).all()
        processes = (await session.execute(select(MesProcess).where(MesProcess.org_id == scope.org_id,
            MesProcess.is_active.is_(True), *scoped_conditions(MesProcess, user, PERMISSION)))).scalars().all()
        # 路线完整性契约：仅投影本次工序所属工艺的前置ID，不泄露其他档案内容。
        dependencies = (await session.execute(select(MesProcessDependency).where(
            MesProcessDependency.org_id == scope.org_id, MesProcessDependency.deleted_at.is_(None),
            MesProcessDependency.is_active.is_(True), MesProcessDependency.process_id.in_([t.process_id for t in tasks if t.process_id])))).scalars().all()
        equipment = (await session.execute(select(MesEquipment).where(MesEquipment.org_id == scope.org_id,
            MesEquipment.is_active.is_(True), *scoped_conditions(MesEquipment, user, PERMISSION)))).scalars().all()
        links = (await session.execute(select(MesEquipmentProcess).where(
            MesEquipmentProcess.org_id == scope.org_id, MesEquipmentProcess.equipment_id.in_([e.id for e in equipment]),
            MesEquipmentProcess.is_active.is_(True), *scoped_conditions(MesEquipmentProcess, user, PERMISSION)))).scalars().all()
        # 只取身份有效性和生产资源编号，不读取自然人姓名、联系方式或原始导入JSON。
        people = (await session.execute(select(MesProductionPerson, MdPerson.user_id)
            .join(MdPerson, and_(MdPerson.party_id == MesProductionPerson.party_id, MdPerson.deleted_at.is_(None)))
            .join(MdParty, and_(MdParty.id == MdPerson.party_id, MdParty.deleted_at.is_(None), MdParty.is_active.is_(True)))
            .where(MesProductionPerson.org_id == scope.org_id, MesProductionPerson.is_active.is_(True),
                *scoped_conditions(MesProductionPerson, user, PERMISSION)))).all()
        qualifications = (await session.execute(select(MesPersonProcess).where(
            MesPersonProcess.org_id == scope.org_id, MesPersonProcess.production_person_id.in_([p.id for p, _ in people]),
            MesPersonProcess.is_active.is_(True), *scoped_conditions(MesPersonProcess, user, PERMISSION),
            MesPersonProcess.valid_from < scope.end_at,
            or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to > scope.start_at)))).scalars().all()
        calendars = (await session.execute(select(MesResourceCalendar).where(MesResourceCalendar.org_id == scope.org_id,
            *scoped_conditions(MesResourceCalendar, user, PERMISSION)))).scalars().all()
        periods = (await session.execute(select(MesResourceCalendarPeriod).where(
            MesResourceCalendarPeriod.calendar_id.in_([c.id for c in calendars]), MesResourceCalendarPeriod.org_id == scope.org_id,
            MesResourceCalendarPeriod.deleted_at.is_(None),MesResourceCalendarPeriod.is_active.is_(True)))).scalars().all()
        # 已授权资源的完整可用性属于内部排程契约；不能因例外由另一人创建而漏掉停机/请假。
        # 原因正文不进入prepare响应、求解器或输入摘要，资源维护页面仍独立校验其记录范围。
        exceptions = (await session.execute(select(MesResourceCalendarException).where(
            MesResourceCalendarException.calendar_id.in_([c.id for c in calendars]),
            MesResourceCalendarException.org_id == scope.org_id,
            MesResourceCalendarException.deleted_at.is_(None),MesResourceCalendarException.is_active.is_(True)))).scalars().all()
        # 同一自然人的跨组织不可用投影，仅用于扣减可用时段，不暴露来源和原因。
        absences = (await session.execute(select(MesProductionPerson.party_id, MesResourceCalendarException.start_at,
            MesResourceCalendarException.end_at).join(MesResourceCalendar, MesResourceCalendar.production_person_id == MesProductionPerson.id)
            .join(MesResourceCalendarException, MesResourceCalendarException.calendar_id == MesResourceCalendar.id)
            .where(MesProductionPerson.party_id.in_([p.party_id for p, _ in people]), MesProductionPerson.deleted_at.is_(None),
                MesResourceCalendar.deleted_at.is_(None), MesResourceCalendar.is_active.is_(True),
                MesResourceCalendarException.deleted_at.is_(None), MesResourceCalendarException.is_active.is_(True),
                MesResourceCalendarException.exception_type_code == "unavailable",
                MesResourceCalendarException.start_at < scope.end_at, MesResourceCalendarException.end_at > scope.start_at))).all()
        reservations = await self.occupancy(session, scope, equipment, [u for _, u in people if u], [p.party_id for p, _ in people])
        unknown_actual_resources=(await session.execute(select(
            case((MesOperationExecution.status_code=="paused",None),else_=MesProductionPerson.party_id),
            func.coalesce(MesOperationExecution.equipment_id,MesWorkOrderOperation.equipment_id))
            .join(MesWorkOrderOperation,MesWorkOrderOperation.id==MesOperationExecution.operation_id)
            .outerjoin(MesProductionPerson,MesProductionPerson.id==MesOperationExecution.production_person_id)
            .where(MesOperationExecution.tracked_out_at.is_(None),MesWorkOrderOperation.work_order_id.notin_(scope.work_order_ids),
                or_(MesOperationExecution.segment_type_code.is_(None),MesOperationExecution.segment_type_code.notin_(["external_wait","external_return"])),
                or_(MesProductionPerson.party_id.in_([p.party_id for p,_ in people]),MesOperationExecution.equipment_id.in_([e.id for e in equipment]),MesWorkOrderOperation.equipment_id.in_([e.id for e in equipment]))))).all()
        phase_reservations = (await session.execute(select(MesProductionPerson.party_id, MesSchedulePlanSegment.equipment_id,
            MesSchedulePlanSegment.planned_start_at, MesSchedulePlanSegment.planned_end_at,
            MesSchedulePlanSegment.person_capacity_units_snapshot).select_from(MesSchedulePlanSegment)
            .join(MesSchedulePlanOperation, MesSchedulePlanOperation.id == MesSchedulePlanSegment.plan_operation_id)
            .join(MesSchedulePlan, MesSchedulePlan.id == MesSchedulePlanOperation.plan_id)
            .outerjoin(MesProductionPerson, MesProductionPerson.id == MesSchedulePlanSegment.production_person_id)
            .where(MesSchedulePlan.status_code == "applied", MesSchedulePlan.is_active.is_(True), MesSchedulePlan.deleted_at.is_(None),
                MesSchedulePlanOperation.is_active.is_(True), MesSchedulePlanOperation.deleted_at.is_(None),
                MesSchedulePlanSegment.is_active.is_(True), MesSchedulePlanSegment.deleted_at.is_(None),
                ~exists().where(MesOperationProductionPhase.operation_id==MesSchedulePlanOperation.operation_id,
                    MesOperationProductionPhase.production_phase_code==MesSchedulePlanSegment.production_phase_code,
                    MesOperationProductionPhase.deleted_at.is_(None),MesOperationProductionPhase.status_code=="completed"),
                MesSchedulePlanOperation.work_order_id.notin_(scope.work_order_ids),
                MesSchedulePlanSegment.planned_start_at < scope.end_at, MesSchedulePlanSegment.planned_end_at > scope.start_at,
                or_(MesProductionPerson.party_id.in_([p.party_id for p, _ in people]),
                    MesSchedulePlanSegment.equipment_id.in_([e.id for e in equipment]))))).all()
        return dict(orders=orders, tasks=tasks, hidden_route=hidden_route, facts=facts, processes=processes,
            phases=phases,gates=gates,execution_facts=execution_facts,fixed_people=dict(fixed_people),
            unknown_actual_resources=unknown_actual_resources,
            incomplete_projects=incomplete_projects,
            equipment=equipment, links=links, people=people, qualifications=qualifications, calendars=calendars,
            periods=periods, reservations=reservations, dependencies=dependencies, exceptions=exceptions, absences=absences,
            phase_reservations=phase_reservations, **configurations)

    async def occupancy(self, session, scope, equipment, user_ids, party_ids=()):
        task, order = MesWorkOrderOperation, MesWorkOrder
        equipment_ids = [e.id for e in equipment]
        # 状态未知、暂停及已开工没有可信释放时间，一律标为未知占用，由预检阻止。
        live_execution = exists().where(MesOperationExecution.operation_id == task.id,
            MesOperationExecution.tracked_out_at.is_(None))
        formally_planned = exists().where(MesSchedulePlanOperation.operation_id == task.id,
            MesSchedulePlanOperation.plan_id == MesSchedulePlan.id, MesSchedulePlan.status_code == "applied",
            MesSchedulePlan.is_active.is_(True), MesSchedulePlan.deleted_at.is_(None),
            MesSchedulePlanOperation.is_active.is_(True), MesSchedulePlanOperation.deleted_at.is_(None))
        statement = select(task.equipment_id, task.assigned_user_id, task.status_code,
            task.planned_start_at, task.planned_end_at, task.workstation_name_snapshot, live_execution, MesProductionPerson.party_id
        ).select_from(task).join(order, order.id == task.work_order_id).outerjoin(
            MesProductionPerson, MesProductionPerson.id == task.assigned_production_person_id,
        ).where(
            task.deleted_at.is_(None), order.deleted_at.is_(None),
            order.status_code.notin_(["completed", "cancelled"]),
            task.status_code.notin_(["completed", "cancelled"]), task.work_order_id.notin_(scope.work_order_ids),
            ~formally_planned,
            # 指定人选只限制下次排程；尚未安排时间、也未开工的任务并不占用此人的产能。
            ~and_(task.assigned_production_person_id.is_not(None), task.status_code.in_(["draft", "pending", "dispatched"]),
                task.planned_start_at.is_(None), task.planned_end_at.is_(None), ~live_execution),
            or_(task.equipment_id.in_(equipment_ids), task.assigned_user_id.in_(user_ids), MesProductionPerson.party_id.in_(party_ids),
                and_(task.org_id == scope.org_id, task.workstation_name_snapshot.in_([e.equipment_no for e in equipment])),
                and_(task.org_id == scope.org_id, task.planned_start_at.is_not(None),
                    task.equipment_id.is_(None), task.assigned_user_id.is_(None), task.assigned_production_person_id.is_(None)),
                and_(task.org_id == scope.org_id, task.status_code.in_(["in_progress", "paused", "waiting_quality"]))),
            or_(task.planned_start_at.is_(None), task.planned_end_at.is_(None),
                task.status_code.notin_(["draft", "pending", "dispatched"]),
                live_execution,
                and_(task.planned_start_at < scope.end_at, task.planned_end_at > scope.start_at)))
        rows = list((await session.execute(statement)).all())
        # 实际开工人员可能不同于派工人员；不能只依据assigned_user_id而漏掉正在占用的人。
        execution = MesOperationExecution
        actual = select(task.equipment_id, case((execution.status_code=="paused",None),else_=execution.worker_user_id), literal("in_progress"),
            literal(None), literal(None), task.workstation_name_snapshot, literal(True), literal(None)).join(
                execution, execution.operation_id == task.id).where(
            execution.tracked_out_at.is_(None), task.deleted_at.is_(None), task.work_order_id.notin_(scope.work_order_ids),
            execution.production_person_id.is_(None),
            or_(execution.segment_type_code.is_(None),execution.segment_type_code.notin_(["external_wait","external_return"])),
            or_(task.equipment_id.in_(equipment_ids), execution.worker_user_id.in_(user_ids),
                and_(task.org_id == scope.org_id, task.equipment_id.is_(None))))
        rows.extend((await session.execute(actual)).all())
        return rows


repository = TrialRepository()
