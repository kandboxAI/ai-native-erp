"""流程运行数据访问：实例、待办、候选人、审批记录、抄送。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, desc, exists, func, literal, or_, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission
from app.modules.todo.models import SysTodo, SysTodoAssignee
from app.modules.user_role.models import SysUserRole
from app.modules.workflow.models import (
    WfCcRecord,
    WfInstance,
    WfTask,
    WfTaskAction,
    WfTaskCandidate,
)

INSTANCE_RUNNING = "running"
TASK_PENDING = "pending"
TASK_COMPLETED = "completed"
TASK_CANCELLED = "cancelled"
VOTE_ACTIONS = ("approve", "reject")
APPROVAL_TODO_TYPE = "workflow.approval"


class WorkflowRuntimeRepository:
    def todo_sources(self, user):
        stmt = select(WfTask.id).join(WfInstance, WfInstance.id == WfTask.instance_id).where(
            *self._user_task_conditions(user.user_id, TASK_PENDING), WfInstance.status_code == INSTANCE_RUNNING)
        return stmt if "workflow_task:list" in user.permissions else stmt.where(False)

    async def pending_tasks_missing_todo(self, session: AsyncSession, user) -> list[WfTask]:
        if "workflow_task:list" not in user.permissions:
            return []

        assignment_exists = exists().where(
            SysTodoAssignee.todo_id == SysTodo.id,
            SysTodoAssignee.user_id == user.user_id,
        ).correlate(SysTodo)
        # Use the same indexed key as the writer and leave closed todos alone.
        todo_is_synced = exists().where(
            SysTodo.dedup_key == literal(f"{APPROVAL_TODO_TYPE}:") + cast(WfTask.id, String),
            or_(SysTodo.status_code != TASK_PENDING, assignment_exists),
        ).correlate(WfTask)
        stmt = (
            self.todo_sources(user)
            .with_only_columns(WfTask)
            .where(~todo_is_synced)
            .with_for_update(of=WfTask, skip_locked=True)
        )
        return list((await session.exec(stmt)).scalars().all())

    async def all_pending_todo_tasks(self, session):
        return list((await session.exec(select(WfTask).join(WfInstance, WfInstance.id == WfTask.instance_id)
            .where(WfTask.status_code == TASK_PENDING, WfInstance.status_code == INSTANCE_RUNNING))).scalars().all())

    def current_approver_condition(self, user_id: UUID):
        """候选快照不代替当前授权；撤权后待办列表和数量立即排除该用户。"""
        def holds(permission_key):
            return exists().where(
                SysUserRole.user_id == user_id,
                SysRole.id == SysUserRole.role_id,
                SysRole.is_active.is_(True),
                SysRole.deleted_at.is_(None),
                SysRolePermission.role_id == SysRole.id,
                SysPermission.id == SysRolePermission.permission_id,
                SysPermission.permission_key == permission_key,
                SysPermission.is_active.is_(True),
                SysPermission.deleted_at.is_(None),
            ).correlate(WfTask)

        return holds("workflow_task:complete") & or_(
            WfTask.assignee_type_code != "permission",
            holds(WfTask.assignee_value),
        )

    # ───────── 实例 ─────────
    async def get_instance(self, session: AsyncSession, instance_id: UUID, *, for_update: bool = False) -> WfInstance | None:
        if for_update:
            return await session.get(WfInstance, instance_id, with_for_update=True, populate_existing=True)
        return await session.get(WfInstance, instance_id)

    async def running_instance_for_business(
        self, session: AsyncSession, business_type_code: str, business_id: UUID, *, for_update: bool = False
    ) -> WfInstance | None:
        stmt = select(WfInstance).where(
            WfInstance.business_type_code == business_type_code,
            WfInstance.business_id == business_id,
            WfInstance.status_code == INSTANCE_RUNNING,
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(stmt)).scalars().first()

    async def instances_for_business(self, session: AsyncSession, business_type_code: str, business_id: UUID) -> list[WfInstance]:
        stmt = (
            select(WfInstance)
            .where(WfInstance.business_type_code == business_type_code, WfInstance.business_id == business_id)
            .order_by(WfInstance.started_at)
        )
        return list((await session.exec(stmt)).scalars().all())

    async def list_instances(
        self,
        session: AsyncSession,
        *,
        status_code: str | None,
        business_type_code: str | None,
        org_ids: list[UUID] | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WfInstance], int]:
        stmt = select(WfInstance)
        if status_code:
            stmt = stmt.where(WfInstance.status_code == status_code)
        if business_type_code:
            stmt = stmt.where(WfInstance.business_type_code == business_type_code)
        if org_ids is not None:
            stmt = stmt.where(WfInstance.org_id.in_(org_ids))
        total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
        rows = (
            await session.exec(stmt.order_by(desc(WfInstance.started_at)).offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return list(rows), total

    # ───────── 待办与候选人 ─────────
    async def get_task(self, session: AsyncSession, task_id: UUID, *, for_update: bool = False) -> WfTask | None:
        stmt = select(WfTask).where(WfTask.id == task_id)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(stmt)).scalars().first()

    async def tasks_for_instances(self, session: AsyncSession, instance_ids: list[UUID]) -> list[WfTask]:
        if not instance_ids:
            return []
        stmt = select(WfTask).where(WfTask.instance_id.in_(instance_ids)).order_by(WfTask.arrived_at)
        return list((await session.exec(stmt)).scalars().all())

    async def pending_tasks(self, session: AsyncSession, instance_id: UUID) -> list[WfTask]:
        stmt = (
            select(WfTask)
            .where(WfTask.instance_id == instance_id, WfTask.status_code == TASK_PENDING)
            .order_by(WfTask.arrived_at)
        )
        return list((await session.exec(stmt)).scalars().all())

    async def cancel_pending_tasks(self, session: AsyncSession, instance_id: UUID, user_id: UUID | None,
                                   *, keep_ids=()) -> None:
        stmt = update(WfTask).where(WfTask.instance_id == instance_id, WfTask.status_code == TASK_PENDING)
        if keep_ids:
            stmt = stmt.where(WfTask.id.not_in(keep_ids))
        await session.execute(stmt.values(status_code=TASK_CANCELLED, updated_at=utc_now(), updated_by=user_id))

    async def add_task(self, session: AsyncSession, task: WfTask, candidate_user_ids: list[UUID], user_id: UUID | None) -> WfTask:
        session.add(task)
        await session.flush()
        for candidate in candidate_user_ids:
            session.add(
                WfTaskCandidate(org_id=task.org_id, task_id=task.id, user_id=candidate, created_by=user_id, updated_by=user_id)
            )
        await session.flush()
        return task

    async def candidate_map(self, session: AsyncSession, task_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        if not task_ids:
            return {}
        stmt = (
            select(WfTaskCandidate.task_id, WfTaskCandidate.user_id)
            .where(WfTaskCandidate.task_id.in_(task_ids))
            .order_by(WfTaskCandidate.created_at)
        )
        result: dict[UUID, list[UUID]] = {task_id: [] for task_id in task_ids}
        for task_id, user_id in (await session.exec(stmt)).all():
            result.setdefault(task_id, []).append(user_id)
        return result

    async def candidates(self, session: AsyncSession, task_id: UUID) -> list[UUID]:
        return (await self.candidate_map(session, [task_id])).get(task_id, [])

    def _user_task_conditions(self, user_id: UUID, status_code: str | None):
        candidate = exists().where(WfTaskCandidate.task_id == WfTask.id, WfTaskCandidate.user_id == user_id)
        acted = exists().where(
            WfTaskAction.task_id == WfTask.id,
            WfTaskAction.actor_user_id == user_id,
            WfTaskAction.action_code.in_(VOTE_ACTIONS),
        )
        if status_code == TASK_PENDING:
            # 待我办理：我是候选人，且（会签时）我还没投票
            return [WfTask.status_code == TASK_PENDING, candidate, ~acted, self.current_approver_condition(user_id)]
        if status_code == TASK_COMPLETED:
            return [or_(WfTask.completed_by == user_id, acted)]
        return [or_(candidate & self.current_approver_condition(user_id), WfTask.completed_by == user_id, acted)]

    async def list_user_tasks(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        status_code: str | None,
        business_type_code: str | None,
        business_id: UUID | None,
        page: int,
        page_size: int,
        task_id: UUID | None = None,
    ) -> tuple[list[tuple[WfTask, WfInstance]], int]:
        stmt = (
            select(WfTask, WfInstance)
            .join(WfInstance, WfInstance.id == WfTask.instance_id)
            .where(*self._user_task_conditions(user_id, status_code))
        )
        if task_id:
            stmt = stmt.where(WfTask.id == task_id)
        if business_type_code:
            stmt = stmt.where(WfInstance.business_type_code == business_type_code)
        if business_id:
            stmt = stmt.where(WfInstance.business_id == business_id)
        total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
        rows = (
            await session.exec(stmt.order_by(desc(WfTask.arrived_at), desc(WfTask.id)).offset((page - 1) * page_size).limit(page_size))
        ).all()
        return [(row[0], row[1]) for row in rows], total

    def pending_instance_ids_for_user(self, user_id: UUID):
        """子查询：当前用户待办理（候选人且未投票）的运行中实例。"""
        acted = exists().where(
            WfTaskAction.task_id == WfTask.id,
            WfTaskAction.actor_user_id == user_id,
            WfTaskAction.action_code.in_(VOTE_ACTIONS),
        )
        return (
            select(WfTask.instance_id)
            .join(WfTaskCandidate, WfTaskCandidate.task_id == WfTask.id)
            .where(WfTask.status_code == TASK_PENDING, WfTaskCandidate.user_id == user_id, ~acted,
                   self.current_approver_condition(user_id))
        )

    # ───────── 审批记录 ─────────
    def add_action(
        self,
        session: AsyncSession,
        *,
        instance: WfInstance,
        task_id: UUID | None,
        action_code: str,
        actor_user_id: UUID,
        comment: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> WfTaskAction:
        row = WfTaskAction(
            org_id=instance.org_id,
            instance_id=instance.id,
            task_id=task_id,
            action_code=action_code,
            actor_user_id=actor_user_id,
            comment=comment,
            payload=payload or {},
            created_by=actor_user_id,
        )
        session.add(row)
        return row

    async def has_voted(self, session: AsyncSession, task_id: UUID, user_id: UUID) -> bool:
        stmt = select(WfTaskAction.id).where(
            WfTaskAction.task_id == task_id,
            WfTaskAction.actor_user_id == user_id,
            WfTaskAction.action_code.in_(VOTE_ACTIONS),
        )
        return (await session.exec(stmt)).first() is not None

    async def approved_user_ids(self, session: AsyncSession, task_id: UUID) -> set[UUID]:
        stmt = select(WfTaskAction.actor_user_id).where(WfTaskAction.task_id == task_id, WfTaskAction.action_code == "approve")
        return set((await session.exec(stmt)).scalars().all())

    async def approved_counts(self, session: AsyncSession, task_ids: list[UUID]) -> dict[UUID, int]:
        if not task_ids:
            return {}
        stmt = (
            select(WfTaskAction.task_id, func.count(func.distinct(WfTaskAction.actor_user_id)))
            .where(WfTaskAction.task_id.in_(task_ids), WfTaskAction.action_code == "approve")
            .group_by(WfTaskAction.task_id)
        )
        return {task_id: int(count) for task_id, count in (await session.exec(stmt)).all()}

    async def actions_for_instances(
        self, session: AsyncSession, instance_ids: list[UUID], action_codes: list[str] | None = None
    ) -> list[WfTaskAction]:
        if not instance_ids:
            return []
        stmt = select(WfTaskAction).where(WfTaskAction.instance_id.in_(instance_ids))
        if action_codes:
            stmt = stmt.where(WfTaskAction.action_code.in_(action_codes))
        return list((await session.exec(stmt.order_by(WfTaskAction.created_at))).scalars().all())

    async def latest_action(self, session: AsyncSession, instance_id: UUID, action_code: str) -> WfTaskAction | None:
        stmt = (
            select(WfTaskAction)
            .where(WfTaskAction.instance_id == instance_id, WfTaskAction.action_code == action_code)
            .order_by(desc(WfTaskAction.created_at))
            .limit(1)
        )
        return (await session.exec(stmt)).scalars().first()

    # ───────── 抄送 ─────────
    def add_cc(self, session: AsyncSession, row: WfCcRecord) -> None:
        session.add(row)

    async def get_cc(self, session: AsyncSession, cc_id: UUID) -> WfCcRecord | None:
        return await session.get(WfCcRecord, cc_id)

    async def list_cc(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        status_code: str | None,
        business_type_code: str | None,
        business_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WfCcRecord], int]:
        stmt = select(WfCcRecord).where(WfCcRecord.recipient_user_id == user_id)
        if status_code:
            stmt = stmt.where(WfCcRecord.status_code == status_code)
        if business_type_code:
            stmt = stmt.where(WfCcRecord.business_type_code == business_type_code)
        if business_id:
            stmt = stmt.where(WfCcRecord.business_id == business_id)
        total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
        rows = (
            await session.exec(stmt.order_by(desc(WfCcRecord.created_at)).offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return list(rows), total

    async def is_cc_recipient(self, session: AsyncSession, instance_ids: list[UUID], user_id: UUID) -> bool:
        if not instance_ids:
            return False
        stmt = select(WfCcRecord.id).where(WfCcRecord.instance_id.in_(instance_ids), WfCcRecord.recipient_user_id == user_id).limit(1)
        return (await session.exec(stmt)).first() is not None


runtime_repository = WorkflowRuntimeRepository()
