from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import scoped_conditions
from app.framework.db.models import utc_now
from app.modules.masterdata.models import MdParty, MdPerson
from app.modules.user_profile.models import SysUser, SysUserOrg
from app.modules.user_profile.public import user_name_matching_ids

from .models import (
    MesExecutionEvent,
    MesOperationExecution,
    MesOperationMaterialRequirement,
    MesProductionReport,
    MesWorkOrder,
    MesWorkOrderOperation,
    MesProductionOrder,
    MesWorkOrderEvent,
)
from .schemas import MesWorkOrderListQuery, ProductionReportListQuery, ProductionTaskListQuery
from .order_status import ORDER_STATUS_LABELS
from .schedule_models import MesOperationProductionPhase, MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment, MesWorkOrderFirstArticle
from .workforce_models import MesPersonProcess, MesProductionPerson


MES_TASK_PERMISSION = "mes:production_report:create"
MES_MANAGE_PERMISSION = "mes:operation_task:manage"


def _org_conditions(model, user: AuthenticatedUser, permission: str = MES_TASK_PERMISSION) -> list:
    return scoped_conditions(model, user, permission)


class MesRepository:
    @staticmethod
    def _production_people():
        return (
            select(MesProductionPerson.id, MesProductionPerson.org_id, MesProductionPerson.person_no, MdPerson.full_name)
            .select_from(MesProductionPerson)
            .join(MdPerson, MdPerson.party_id == MesProductionPerson.party_id)
            .join(MdParty, MdParty.id == MdPerson.party_id)
            .where(MesProductionPerson.deleted_at.is_(None), MdPerson.deleted_at.is_(None), MdParty.deleted_at.is_(None))
        )

    @staticmethod
    def _has_account(org_id, user_id=None):
        membership = select(SysUserOrg.id).where(
            SysUserOrg.user_id == SysUser.id, SysUserOrg.org_id == org_id,
        ).correlate(SysUser, MesWorkOrderOperation).exists()
        return exists(select(SysUser.id).where(
            SysUser.id == MdPerson.user_id, SysUser.id == user_id if user_id is not None else True,
            SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
            or_(SysUser.org_id == org_id, SysUser.org_access_mode_code == "all", membership),
        ).correlate(MdPerson, MesWorkOrderOperation))

    @staticmethod
    def _applied_assignment(task, field):
        phase, op, plan, segment, gate = (
            MesOperationProductionPhase, MesSchedulePlanOperation, MesSchedulePlan,
            MesSchedulePlanSegment, MesWorkOrderFirstArticle,
        )
        return (
            select(field).select_from(phase)
            .join(op, op.id == phase.plan_operation_id)
            .join(plan, plan.id == op.plan_id)
            .outerjoin(gate, and_(gate.work_order_id == phase.work_order_id, gate.deleted_at.is_(None)))
            .outerjoin(segment, and_(
                segment.plan_operation_id == op.id, segment.production_phase_code == phase.production_phase_code,
                segment.org_id == phase.org_id,
                segment.is_independent_inspection.is_(False), segment.deleted_at.is_(None),
            ))
            .where(
                phase.operation_id == task.id, phase.org_id == task.org_id, phase.deleted_at.is_(None),
                op.org_id == phase.org_id, op.is_active.is_(True), op.deleted_at.is_(None),
                plan.org_id == phase.org_id, plan.status_code == "applied", plan.is_active.is_(True), plan.deleted_at.is_(None),
                or_(phase.production_phase_code == "first", gate.status_code == "released"),
            )
            .order_by(phase.production_phase_code.desc(), segment.sequence_no, segment.id)
            .limit(1).correlate(MesWorkOrderOperation).scalar_subquery()
        )

    async def applied_assignments(self, session, task_ids):
        if not task_ids:
            return {}
        task = MesWorkOrderOperation
        rows = (await session.execute(select(
            task.id, self._applied_assignment(task, MesSchedulePlanSegment.production_person_id).label("person_id"),
            self._applied_assignment(task, MesSchedulePlan.id).label("plan_id"),
        ).where(task.id.in_(task_ids)))).all()
        return {row.id: row for row in rows if row.plan_id}

    def _person_with_account(self, org_id, person_id, user_id=None):
        return self._production_people().where(
            MesProductionPerson.id == person_id,
            MesProductionPerson.org_id == org_id,
            MesProductionPerson.is_active.is_(True), MdParty.is_active.is_(True),
            self._has_account(org_id, user_id),
        ).correlate(MesWorkOrderOperation)

    async def can_report_as_person(self, session, org_id, person_id, user_id):
        return bool((await session.execute(select(self._person_with_account(org_id, person_id, user_id).exists()))).scalar_one())

    async def production_person_names(self, session, identifiers):
        if not identifiers:
            return {}
        rows = (await session.execute(self._production_people().where(MesProductionPerson.id.in_(identifiers)))).all()
        return {row.id: row for row in rows}

    async def production_dispatch_options(self, session, task, keyword="", limit=50, person_id=None):
        if not task.process_id:
            return []
        qualification = exists(select(MesPersonProcess.id).where(
            MesPersonProcess.production_person_id == MesProductionPerson.id,
            MesPersonProcess.org_id == task.org_id, MesPersonProcess.process_id == task.process_id,
            MesPersonProcess.deleted_at.is_(None), MesPersonProcess.is_active.is_(True),
            or_(MesPersonProcess.valid_to.is_(None), MesPersonProcess.valid_to > utc_now()),
        ))
        statement = self._production_people().add_columns(self._has_account(task.org_id).label("has_account")).where(
            MesProductionPerson.org_id == task.org_id, MesProductionPerson.is_active.is_(True),
            MdParty.is_active.is_(True), qualification,
        )
        if person_id:
            statement = statement.where(MesProductionPerson.id == person_id)
        if keyword.strip():
            pattern = f"%{keyword.strip()}%"
            statement = statement.where(or_(MdPerson.full_name.ilike(pattern), MesProductionPerson.person_no.ilike(pattern)))
        rows = (await session.execute(statement.order_by(MesProductionPerson.person_no, MesProductionPerson.id).limit(limit))).all()
        return [dict(id=row.id, full_name=row.full_name, person_no=row.person_no, has_account=row.has_account) for row in rows]

    def work_order_conditions(self, query, user):
        conditions = [*_org_conditions(MesWorkOrder, user, "mes:work_order:list")]
        for name in ["priority_code", "production_order_id", "order_type_code", "processing_type_code", "created_by"]:
            if value := getattr(query, name, None):
                conditions.append(getattr(MesWorkOrder, name) == value)
        if query.overdue_only:
            conditions.extend([MesWorkOrder.due_at < utc_now(), MesWorkOrder.status_code.notin_(["completed", "cancelled"])])
        if query.repair_source_only:
            conditions.append(MesWorkOrder.status_code.notin_(["draft", "cancelled"]))
        for column, start, end in [(MesWorkOrder.created_at, query.created_from, query.created_to), (MesWorkOrder.due_at, query.due_from, query.due_to)]:
            if start:
                conditions.append(column >= datetime.combine(start, time.min, ZoneInfo("Asia/Shanghai")))
            if end:
                conditions.append(column < datetime.combine(end + timedelta(days=1), time.min, ZoneInfo("Asia/Shanghai")))
        configured = exists(select(MesWorkOrderOperation.id).where(MesWorkOrderOperation.work_order_id == MesWorkOrder.id, MesWorkOrderOperation.deleted_at.is_(None)))
        if query.status_code in {"unconfigured", "ready"}:
            conditions.extend([MesWorkOrder.status_code == "draft", configured if query.status_code == "ready" else ~configured])
        elif query.status_code == "ordered":
            conditions.append(MesWorkOrder.status_code.in_(["released", "in_progress"]))
        elif query.status_code == "unfinished":
            conditions.append(MesWorkOrder.status_code.notin_(["completed", "cancelled"]))
        elif query.status_code:
            conditions.append(MesWorkOrder.status_code == query.status_code)
        if query.configuration:
            conditions.append(configured if query.configuration == "configured" else ~configured)
        if query.customer:
            pattern = f"%{query.customer.strip()}%"
            conditions.append(MesWorkOrder.production_order_id.in_(select(MesProductionOrder.id).where(
                MesProductionOrder.deleted_at.is_(None), or_(MesProductionOrder.customer_no_snapshot.ilike(pattern), MesProductionOrder.customer_name_snapshot.ilike(pattern)))))
        if query.creator:
            conditions.append(MesWorkOrder.created_by.in_(user_name_matching_ids(query.creator)))
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(or_(MesWorkOrder.work_order_no.ilike(pattern), MesWorkOrder.product_item_no_snapshot.ilike(pattern), MesWorkOrder.product_item_name_snapshot.ilike(pattern),
                MesWorkOrder.production_order_id.in_(select(MesProductionOrder.id).where(MesProductionOrder.deleted_at.is_(None), or_(MesProductionOrder.production_order_no.ilike(pattern), MesProductionOrder.project_name.ilike(pattern))))))
        return conditions

    async def is_active_assignee(self, session: AsyncSession, user_id: UUID, org_id: UUID) -> bool:
        """Read-only contract: active tenant-user ID and organization membership.

        Does not return identity/contact fields or write user-owned data.
        """
        membership = exists(select(SysUserOrg.id).where(
            SysUserOrg.user_id == SysUser.id, SysUserOrg.org_id == org_id,
        ))
        statement = select(SysUser.id).where(
            SysUser.id == user_id, SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
            or_(SysUser.org_id == org_id, SysUser.org_access_mode_code == "all", membership),
        )
        return (await session.exec(statement)).scalars().first() is not None

    async def list_tasks(
        self,
        session: AsyncSession,
        query: ProductionTaskListQuery,
        user: AuthenticatedUser,
        *,
        manager: bool = False,
    ):
        conditions = [
            MesWorkOrderOperation.deleted_at.is_(None),
            MesWorkOrder.deleted_at.is_(None),
            *_org_conditions(MesWorkOrderOperation, user,
                (MES_MANAGE_PERMISSION if MES_MANAGE_PERMISSION in user.permissions else "mes:operation_task:list")
                if manager else MES_TASK_PERMISSION),
        ]
        if not manager:
            task = MesWorkOrderOperation
            conditions.append(MesWorkOrder.status_code != "draft")
            scheduled_person = self._applied_assignment(task, MesSchedulePlanSegment.production_person_id)
            effective_person = func.coalesce(task.assigned_production_person_id, scheduled_person)
            conditions.append(
                or_(
                    and_(effective_person.is_(None), or_(
                        task.assigned_user_id == user.user_id,
                        task.assigned_user_id.is_(None),
                    )),
                    self._person_with_account(task.org_id, effective_person, user.user_id).exists(),
                    and_(effective_person.is_not(None), ~self._person_with_account(task.org_id, effective_person).exists())
                    if MES_MANAGE_PERMISSION in user.permissions else False,
                )
            )
        if query.status_code:
            conditions.append(MesWorkOrderOperation.status_code == query.status_code)
        if query.keyword:
            keyword = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    MesWorkOrder.work_order_no.ilike(keyword),
                    MesWorkOrderOperation.operation_no.ilike(keyword),
                    MesWorkOrderOperation.operation_name_snapshot.ilike(keyword),
                    MesWorkOrder.product_item_no_snapshot.ilike(keyword),
                    MesWorkOrder.product_item_name_snapshot.ilike(keyword),
                )
            )
        base = select(MesWorkOrderOperation, MesWorkOrder).join(
            MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id
        ).where(*conditions)
        total = int(
            (
                await session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
            or 0
        )
        rows = (
            await session.exec(
                base.order_by(
                    MesWorkOrderOperation.priority_code,
                    MesWorkOrderOperation.due_at.nulls_last(),
                    MesWorkOrderOperation.sequence_no,
                )
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return [(row[0], row[1]) for row in rows], total

    async def list_work_orders(self, session: AsyncSession, query: MesWorkOrderListQuery, user: AuthenticatedUser):
        base = select(MesWorkOrder).where(*self.work_order_conditions(query, user))
        total = int(
            (
                await session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
            or 0
        )
        rows = (
            await session.exec(
                base.order_by(MesWorkOrder.updated_at.desc(), MesWorkOrder.created_at.desc())
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).scalars().all()
        return rows, total

    async def get_work_order(self, session: AsyncSession, work_order_id: UUID, user: AuthenticatedUser, *, permission="mes:work_order:list", for_update=False):
        conditions = [
            MesWorkOrder.id == work_order_id,
            MesWorkOrder.deleted_at.is_(None),
            *_org_conditions(MesWorkOrder, user, permission),
        ]
        statement = select(MesWorkOrder).where(*conditions).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).scalars().first()

    async def projects(self, session, ids):
        if not ids: return {}
        rows = (await session.exec(select(MesProductionOrder).where(MesProductionOrder.id.in_(ids), MesProductionOrder.deleted_at.is_(None)))).scalars().all()
        return {row.id: row for row in rows}

    async def get_project(self, session, project_id, user, permission, *, for_update=False):
        statement = select(MesProductionOrder).where(MesProductionOrder.id == project_id, *_org_conditions(MesProductionOrder, user, permission))
        if for_update: statement = statement.with_for_update()
        return (await session.exec(statement)).scalars().first()

    async def list_projects(self, session, query, user):
        business_status = query.status_code in ORDER_STATUS_LABELS
        matching = select(MesWorkOrder.production_order_id).where(*self.work_order_conditions(
            query.model_copy(update={"status_code": None}) if business_status else query, user))
        base = select(MesProductionOrder).where(*_org_conditions(MesProductionOrder, user, "mes:work_order:list"), MesProductionOrder.id.in_(matching))
        if business_status:
            base = base.where(self.project_status_expression(user) == query.status_code)
        total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        projects = (await session.exec(base.order_by(MesProductionOrder.updated_at.desc(), MesProductionOrder.id).offset((query.page - 1) * query.page_size).limit(query.page_size))).scalars().all()
        orders = (await session.exec(select(MesWorkOrder).where(*_org_conditions(MesWorkOrder, user, "mes:work_order:list"), MesWorkOrder.production_order_id.in_([row.id for row in projects])))).scalars().all() if projects else []
        return projects, orders, total

    @staticmethod
    def project_status_expression(user):
        def has(*conditions):
            return exists(select(MesWorkOrder.id).where(
                MesWorkOrder.production_order_id == MesProductionOrder.id,
                *_org_conditions(MesWorkOrder, user, "mes:work_order:list"), *conditions,
            ).correlate(MesProductionOrder))
        configured = exists(select(MesWorkOrderOperation.id).where(
            MesWorkOrderOperation.work_order_id == MesWorkOrder.id, MesWorkOrderOperation.deleted_at.is_(None),
        ).correlate(MesWorkOrder))
        return case(
            (has(MesWorkOrder.status_code.in_(["released", "in_progress"])), "ordered"),
            (has(MesWorkOrder.status_code == "paused"), "paused"),
            (has(MesWorkOrder.status_code == "draft", ~configured), "unconfigured"),
            (has(MesWorkOrder.status_code == "draft"), "ready"),
            (has(MesWorkOrder.status_code == "completed"), "completed"),
            else_="cancelled",
        )

    async def project_orders_for_placement(self, session, project_id, user):
        base = [MesWorkOrder.production_order_id == project_id,
                MesWorkOrder.status_code == "draft", MesWorkOrder.deleted_at.is_(None)]
        scope = _org_conditions(MesWorkOrder, user, "mes:work_order:manage")
        # Authorization-only existence check: never expose any hidden child's fields or count.
        blocked = (await session.execute(select(exists(select(MesWorkOrder.id).where(*base, ~and_(*scope)))))).scalar_one()
        if blocked:
            return None
        return (await session.exec(select(MesWorkOrder).where(*base, *scope)
            .order_by(MesWorkOrder.id).with_for_update())).scalars().all()

    async def history_exists(self, session, work_order_id):
        operations = select(MesWorkOrderOperation.id).where(MesWorkOrderOperation.work_order_id == work_order_id)
        return bool((await session.execute(select(or_(
            exists(select(MesOperationExecution.id).where(MesOperationExecution.operation_id.in_(operations))),
            exists(select(MesProductionReport.id).where(MesProductionReport.operation_id.in_(operations))),
        )))).scalar_one())

    async def open_executions_exist(self, session, work_order_id):
        return bool((await session.execute(select(exists(select(MesOperationExecution.id).join(MesWorkOrderOperation, MesWorkOrderOperation.id == MesOperationExecution.operation_id).where(
            MesWorkOrderOperation.work_order_id == work_order_id, MesOperationExecution.status_code.in_(["in_progress", "paused"]),
        ))))).scalar_one())

    async def order_events(self, session, work_order_id):
        return (await session.exec(select(MesWorkOrderEvent).where(MesWorkOrderEvent.work_order_id == work_order_id).order_by(MesWorkOrderEvent.created_at, MesWorkOrderEvent.id))).scalars().all()

    async def repair_exists(self, session, work_order_id):
        return bool((await session.execute(select(exists(select(MesWorkOrder.id).where(MesWorkOrder.source_work_order_id == work_order_id, MesWorkOrder.deleted_at.is_(None)))))).scalar_one())

    async def work_order_operations(self, session: AsyncSession, work_order_id: UUID):
        return await self.operations_for_orders(session, [work_order_id])

    async def operations_for_orders(self, session: AsyncSession, work_order_ids):
        if not work_order_ids:
            return []
        return (
            await session.exec(
                select(MesWorkOrderOperation)
                .where(
                    MesWorkOrderOperation.work_order_id.in_(work_order_ids),
                    MesWorkOrderOperation.deleted_at.is_(None),
                )
                .order_by(MesWorkOrderOperation.sequence_no)
            )
        ).scalars().all()

    async def execution_summaries(self, session, operation_ids):
        if not operation_ids:
            return {}
        rows = (await session.execute(select(
            MesOperationExecution.operation_id,
            func.min(MesOperationExecution.tracked_in_at).label("started_at"),
            func.max(MesOperationExecution.tracked_out_at).label("finished_at"),
        ).where(MesOperationExecution.operation_id.in_(operation_ids))
          .group_by(MesOperationExecution.operation_id))).all()
        return {row.operation_id: row for row in rows}

    async def executions(self, session, operation_id):
        return (await session.exec(select(MesOperationExecution).where(
            MesOperationExecution.operation_id == operation_id,
        ).order_by(MesOperationExecution.tracked_in_at, MesOperationExecution.id))).scalars().all()

    async def work_order_no_exists(self, session, org_id, work_order_no):
        return (await session.execute(select(MesWorkOrder.id).where(
            MesWorkOrder.org_id == org_id, MesWorkOrder.work_order_no == work_order_no,
            MesWorkOrder.deleted_at.is_(None),
        ).limit(1))).scalar_one_or_none() is not None

    async def list_reports(self, session: AsyncSession, query: ProductionReportListQuery, user: AuthenticatedUser):
        conditions = [
            *_org_conditions(MesProductionReport, user, "mes:production_report:list"),
            MesWorkOrderOperation.deleted_at.is_(None),
            MesWorkOrder.deleted_at.is_(None),
        ]
        if query.status_code:
            conditions.append(MesProductionReport.status_code == query.status_code)
        if query.operation_id:
            conditions.append(MesProductionReport.operation_id == query.operation_id)
        if query.work_order_id:
            conditions.append(MesWorkOrder.id == query.work_order_id)
        conditions.extend([MesProductionReport.org_id == MesWorkOrder.org_id,
            MesWorkOrderOperation.org_id == MesWorkOrder.org_id])
        if query.keyword:
            keyword = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    MesProductionReport.report_no.ilike(keyword),
                    MesWorkOrder.work_order_no.ilike(keyword),
                    MesWorkOrderOperation.operation_no.ilike(keyword),
                    MesWorkOrderOperation.operation_name_snapshot.ilike(keyword),
                )
            )
        base = (
            select(MesProductionReport, MesWorkOrderOperation, MesWorkOrder)
            .join(MesWorkOrderOperation, MesWorkOrderOperation.id == MesProductionReport.operation_id)
            .join(MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id)
            .where(*conditions)
        )
        total = int(
            (
                await session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
            or 0
        )
        rows = (
            await session.exec(
                base.order_by(MesProductionReport.reported_at.desc())
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return [(row[0], row[1], row[2]) for row in rows], total

    async def get_task(
        self,
        session: AsyncSession,
        task_id: UUID,
        user: AuthenticatedUser,
        *,
        for_update: bool = False,
        permission: str = MES_TASK_PERMISSION,
    ):
        conditions = [
            MesWorkOrderOperation.id == task_id,
            MesWorkOrderOperation.deleted_at.is_(None),
            MesWorkOrder.deleted_at.is_(None),
            *_org_conditions(MesWorkOrder if permission == "mes:work_order:list" else MesWorkOrderOperation, user, permission),
        ]
        statement = select(MesWorkOrderOperation, MesWorkOrder).join(
            MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id
        ).where(*conditions)
        if for_update:
            # Serialize all production writes on the parent before locking a task.
            parent_id = select(MesWorkOrderOperation.work_order_id).where(*conditions).join(MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id).scalar_subquery()
            await session.execute(select(MesWorkOrder.id).where(MesWorkOrder.id == parent_id).with_for_update())
            statement = statement.with_for_update(of=MesWorkOrderOperation).execution_options(populate_existing=True)
        row = (await session.exec(statement)).first()
        return None if row is None else (row[0], row[1])

    async def current_execution(self, session: AsyncSession, operation_id: UUID, *, for_update: bool = False):
        statement = select(MesOperationExecution).where(
            MesOperationExecution.operation_id == operation_id,
            MesOperationExecution.status_code.in_(["in_progress", "paused"]),
        ).order_by(MesOperationExecution.created_at.desc())
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).scalars().first()

    async def materials(self, session: AsyncSession, operation_id: UUID):
        return (
            await session.exec(
                select(MesOperationMaterialRequirement)
                .where(
                    MesOperationMaterialRequirement.operation_id == operation_id,
                    MesOperationMaterialRequirement.deleted_at.is_(None),
                )
                .order_by(MesOperationMaterialRequirement.created_at)
            )
        ).scalars().all()

    async def events(self, session: AsyncSession, operation_id: UUID):
        return (
            await session.exec(
                select(MesExecutionEvent)
                .where(MesExecutionEvent.operation_id == operation_id)
                .order_by(MesExecutionEvent.created_at)
            )
        ).scalars().all()

    async def find_report_by_idempotency(self, session: AsyncSession, user_id: UUID, key: str):
        return (
            await session.exec(
                select(MesProductionReport).where(
                    MesProductionReport.created_by == user_id,
                    MesProductionReport.idempotency_key == key,
                )
            )
        ).scalars().first()

    @staticmethod
    def add(session: AsyncSession, row) -> None:
        session.add(row)


repository = MesRepository()
