from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import accessible_org_ids, has_all_organization_access
from app.core.exceptions import AppException
from app.framework.datetime_local import parse_datetime_input
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.workflow.design_models import (
    ApprovalNode,
    ConditionExpression,
    ExclusiveGatewayNode,
    ParallelGatewayNode,
    FlowNodeV3,
    normalize_flow_design,
)
from app.modules.workflow.integration.registry import get_business_adapter
from app.modules.workflow.models import WfDefinitionVersion, WfInstance, WfTask, WfTaskAction
from app.modules.workflow.runtime.assignee_resolver import (
    assignee_label,
    can_act_on_task,
    resolve_assignee_user_ids,
    user_display_names,
)
from app.modules.workflow.runtime.repository import TASK_PENDING, runtime_repository
from app.modules.workflow.runtime.service import STARTER_CHOICES_VARIABLE, workflow_runtime_service
from app.modules.workflow.spiff_runner import (
    AssigneeSpec,
    BpmnValidationError,
    deserialize_workflow,
    extract_user_task_assignees,
)
from app.modules.workflow.task.business_detail import load_business_avatar, load_business_summary, load_workflow_business_detail
from app.modules.workflow.business_types import list_workflow_business_types
from app.modules.workflow.task.schemas import (
    WorkflowCcListQuery,
    WorkflowSupervisionListItem,
    WorkflowSupervisionListQuery,
    WorkflowTaskListItem,
    WorkflowTaskListQuery,
    WorkflowTimelineItem,
    WorkflowTimelineResult,
)

SUPERVISE_PERMISSION = "workflow_task:supervise"
OUTCOME_LABELS = {"approved": "同意", "rejected": "驳回", "returned": "退回"}
DYNAMIC_ASSIGNEE_TYPES = {"starter_select"}


def _page(items: list, total: int, params) -> dict:
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


class WorkflowTaskService:
    async def business_types(self) -> list[dict[str, str]]:
        async with get_session_context() as session:
            return await list_workflow_business_types(session)

    # ───────── 权限辅助 ─────────
    @staticmethod
    def can_supervise(current_user: AuthenticatedUser, instance: WfInstance) -> bool:
        """可查看全部审批（监督）：有 workflow_task:supervise 且可访问实例所属组织。"""
        if SUPERVISE_PERMISSION not in current_user.permissions:
            return False
        if has_all_organization_access(current_user, SUPERVISE_PERMISSION):
            return True
        return instance.org_id in set(accessible_org_ids(current_user))

    async def _participation(
        self, session: AsyncSession, current_user: AuthenticatedUser, instances: list[WfInstance]
    ) -> tuple[list[WfTask], dict[UUID, list[UUID]], bool]:
        instance_ids = [row.id for row in instances]
        tasks = await runtime_repository.tasks_for_instances(session, instance_ids)
        candidates = await runtime_repository.candidate_map(session, [task.id for task in tasks])
        user_id = current_user.user_id
        participant = any(row.started_by == user_id for row in instances) or any(
            task.completed_by == user_id or user_id in candidates.get(task.id, []) for task in tasks
        )
        return tasks, candidates, participant

    # ───────── 驳回后重新发起 ─────────
    async def _rejection_edit_baseline(self, session: AsyncSession, latest: WfInstance | None) -> datetime | None:
        if latest is None or latest.status_code != "rejected":
            return None
        action = await runtime_repository.latest_action(session, latest.id, "reject")
        raw = (action.payload or {}).get("edit_required_after") if action is not None else None
        return parse_datetime_input(raw) if isinstance(raw, str) else (latest.ended_at or latest.updated_at)

    async def _business_record(self, session: AsyncSession, business_type_code: str, business_id: UUID) -> Any | None:
        adapter = get_business_adapter(business_type_code)
        if adapter is None or adapter.record_model is None:
            return None
        return await session.get(adapter.record_model, business_id)

    @staticmethod
    def _edited_after_rejection(record: Any | None, rejected_at: datetime | None) -> bool:
        if record is None or rejected_at is None:
            return False
        updated_at = getattr(record, "updated_at", None)
        return bool(updated_at and updated_at > rejected_at)

    @staticmethod
    def _runtime_variables(version: WfDefinitionVersion, instance: WfInstance) -> dict[str, Any]:
        if not isinstance(instance.workflow_state_snapshot, dict) or not instance.workflow_state_snapshot:
            return {}
        try:
            workflow = deserialize_workflow(
                version.bpmn_xml or "", instance.workflow_state_snapshot, process_id=version.bpmn_process_no
            )
        except Exception:  # noqa: BLE001 旧快照无法解析时只影响展示
            return {}
        variables: dict[str, Any] = {}
        for task in workflow.get_tasks_iterator():
            if isinstance(getattr(task, "data", None), dict):
                variables.update(task.data)
        return variables

    async def add_comment(
        self, business_type_code: str, business_id: UUID, comment: str, current_user: AuthenticatedUser
    ) -> WorkflowTimelineResult:
        comment = comment.strip()
        if not comment:
            raise AppException("评论内容不能为空", status_code=400)
        async with get_session_context() as session:
            instances = await runtime_repository.instances_for_business(session, business_type_code, business_id)
            if not instances:
                raise AppException("审批记录不存在", status_code=404)
            tasks, _, participant = await self._participation(session, current_user, instances)
            if not participant:
                raise AppException("仅发起人和审批参与人可以评论", status_code=403)
            latest = instances[-1]
            pending = next((t for t in tasks if t.instance_id == latest.id and t.status_code == TASK_PENDING), None)
            runtime_repository.add_action(
                session,
                instance=latest,
                task_id=pending.id if pending else None,
                action_code="comment",
                actor_user_id=current_user.user_id,
                comment=comment,
            )
            await session.commit()
        return await self.timeline_for_business(business_type_code, business_id, current_user)

    async def resubmit(
        self,
        business_type_code: str,
        business_id: UUID,
        comment: str,
        current_user: AuthenticatedUser,
        selected_starter_choices: dict[str, list[UUID]] | None = None,
    ) -> WorkflowTimelineResult:
        adapter = get_business_adapter(business_type_code)
        if adapter and not adapter.may_start(current_user):
            raise AppException(f"缺少权限：{adapter.start_permission}", status_code=403)
        comment = comment.strip()
        if not comment:
            raise AppException("请填写重新发起说明", status_code=400)
        async with get_session_context() as session:
            instances = await runtime_repository.instances_for_business(session, business_type_code, business_id)
            if not instances:
                raise AppException("审批记录不存在", status_code=404)
            latest = instances[-1]
            if latest.status_code != "rejected":
                raise AppException("只有已驳回的审批可以重新发起", status_code=409)
            if latest.started_by != current_user.user_id:
                raise AppException("只有原发起人可以重新发起审批", status_code=403)
            record = await self._business_record(session, business_type_code, business_id)
            rejected_at = await self._rejection_edit_baseline(session, latest)
            if record is not None and not self._edited_after_rejection(record, rejected_at):
                raise AppException("请先编辑并保存被驳回的原单据，再重新发起审批", status_code=409)
            version = await session.get(WfDefinitionVersion, latest.version_id)
            variables = self._runtime_variables(version, latest) if version else {}
            variables.pop("outcome", None)
            starter_choices: dict[str, list[UUID]] = {}
            raw_choices = variables.pop(STARTER_CHOICES_VARIABLE, {})
            for key, values in (raw_choices.items() if isinstance(raw_choices, dict) else []):
                parsed: list[UUID] = []
                for value in values if isinstance(values, list) else []:
                    try:
                        parsed.append(UUID(str(value)))
                    except ValueError:
                        continue
                starter_choices[str(key)] = parsed
            if selected_starter_choices is not None:
                starter_choices.update(selected_starter_choices)
            adapter = get_business_adapter(business_type_code)
            if adapter and adapter.variables:
                variables.update(await adapter.variables(session, business_id))
            org_id = latest.org_id
            previous_instance_id = latest.id

        await workflow_runtime_service.start(
            business_type_code=business_type_code,
            business_id=business_id,
            org_id=org_id,
            variables=variables,
            starter_choices=starter_choices,
            current_user=current_user,
            start_comment=comment,
            previous_instance_id=previous_instance_id,
        )
        return await self.timeline_for_business(business_type_code, business_id, current_user)

    # ───────── 待办 ─────────
    async def _task_items(
        self, session: AsyncSession, rows: list[tuple[WfTask, WfInstance]], current_user: AuthenticatedUser
    ) -> list[WorkflowTaskListItem]:
        task_ids = [task.id for task, _ in rows]
        candidates = await runtime_repository.candidate_map(session, task_ids)
        approved = await runtime_repository.approved_counts(session, task_ids)
        names = await user_display_names(session, {uid for ids in candidates.values() for uid in ids})
        items: list[WorkflowTaskListItem] = []
        for task, instance in rows:
            task_candidates = candidates.get(task.id, [])
            from app.modules.workflow.analysis_service import visible_analysis
            analysis = await visible_analysis(session, instance, current_user)
            can_read_analysis = analysis.pop("_analysis_access",False)
            adapter = get_business_adapter(instance.business_type_code)
            can_direct = bool(adapter and adapter.allow_quick_approve and instance.status_code == "running"
                and can_read_analysis
                and can_act_on_task(current_user.permissions,current_user.user_id,task.status_code,set(task_candidates),
                    assignee_type_code=task.assignee_type_code,assignee_value=task.assignee_value))
            if can_direct and await runtime_repository.has_voted(session,task.id,current_user.user_id):
                can_direct = False

            items.append(
                WorkflowTaskListItem(
                    business_avatar_url=await load_business_avatar(
                        session, current_user=current_user, business_type_code=instance.business_type_code, business_id=instance.business_id,
                    ),
                    id=task.id,
                    instance_id=task.instance_id,
                    business_type_code=instance.business_type_code,
                    business_id=instance.business_id,
                    task_key=task.task_key,
                    task_name=task.task_name,
                    assignee_type_code=task.assignee_type_code,
                    assignee_value=task.assignee_value,
                    approval_mode_code=task.approval_mode_code,
                    required_count=max(len(task_candidates), 1) if task.approval_mode_code == "all" else 1,
                    approved_count=approved.get(task.id, 0),
                    status_code=task.status_code,
                    outcome_code=task.outcome_code,
                    arrived_at=task.arrived_at,
                    completed_at=task.completed_at,
                    instance_status_code=instance.status_code,
                    business_summary=await load_business_summary(
                        session, current_user=current_user, business_type_code=instance.business_type_code, business_id=instance.business_id
                    ),
                    candidate_names=[names.get(uid, str(uid)) for uid in task_candidates],
                    can_direct_approve=can_direct,
                    **analysis,
                )
            )
        return items

    async def todo_item(self, session, task_id, current_user):
        if "workflow_task:list" not in current_user.permissions:
            return None
        task = await runtime_repository.get_task(session, task_id)
        if task is None:
            return None
        rows, _ = await runtime_repository.list_user_tasks(
            session, user_id=current_user.user_id, status_code="pending",
            business_type_code=None, business_id=None, page=1, page_size=1, task_id=task_id,
        )
        if not rows:
            return None
        item = (await self._task_items(session, rows, current_user))[0]
        from app.modules.workflow.todo_service import task_targets
        actions = [{"key": "approve", "label": "直接通过", "confirm": True}] if item.can_direct_approve else []
        if item.can_direct_approve and item.ai_analysis_status_code == "failed":
            actions.append({"key": "retry_analysis", "label": "重新分析", "confirm": True})
        summary = item.task_name
        adapter = get_business_adapter(item.business_type_code)
        if adapter and adapter.todo_summary:
            if not adapter.detail_access or await adapter.detail_access(session, item.business_id, current_user):
                summary = await adapter.todo_summary(session, item.business_id) or summary
        return {"title": item.business_summary or item.task_name, "summary": summary,
                "targets": task_targets(task.id), "avatar_url": item.business_avatar_url,
                "ai_analysis": item.ai_analysis, "ai_analysis_status_code": item.ai_analysis_status_code,
                "actions": actions}

    async def retry_analysis(self, task_id: UUID, current_user: AuthenticatedUser) -> dict:
        from app.modules.workflow import analysis_repository, analysis_service
        async with get_session_context() as session:
            task = await runtime_repository.get_task(session, task_id)
            if task is None:
                raise AppException("待办不存在", 404)
            # 同一申请的各节点共用分析；锁住实例后复核，避免重复加入队列。
            instance = await analysis_repository.locked_instance(session, task.instance_id)
            item = await self.todo_item(session, task_id, current_user)
            if not instance or not item or "retry_analysis" not in {a["key"] for a in item["actions"]}:
                raise AppException("当前不能重新分析，请刷新待办后重试", 409)
            await analysis_service.queue_after_commit(session, instance.id)
            instance.updated_by = current_user.user_id
            await session.commit()
            return {"ai_analysis_status_code": "pending"}

    async def list_tasks(self, params: WorkflowTaskListQuery, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            rows, total = await runtime_repository.list_user_tasks(
                session,
                user_id=current_user.user_id,
                status_code=params.status_code,
                business_type_code=params.business_type_code,
                business_id=params.business_id,
                page=params.page,
                page_size=params.page_size,
            )
            items = await self._task_items(session, rows, current_user)
            return _page([item.model_dump(mode="json") for item in items], total, params)

    async def pending_for_business(
        self, *, business_type_code: str, business_id: UUID, current_user: AuthenticatedUser
    ) -> dict | None:
        async with get_session_context() as session:
            rows, _ = await runtime_repository.list_user_tasks(
                session,
                user_id=current_user.user_id,
                status_code=TASK_PENDING,
                business_type_code=business_type_code,
                business_id=business_id,
                page=1,
                page_size=1,
            )
            if not rows or "workflow_task:complete" not in current_user.permissions:
                return None
            return (await self._task_items(session, rows, current_user))[0].model_dump(mode="json")

    async def _visible_task(self, session: AsyncSession, task_id: UUID, current_user: AuthenticatedUser) -> tuple[WfTask, WfInstance, list[UUID]]:
        task = await runtime_repository.get_task(session, task_id)
        if task is None:
            raise AppException("待办不存在", status_code=404)
        instance = await runtime_repository.get_instance(session, task.instance_id)
        if instance is None:
            raise AppException("流程实例不存在", status_code=404)
        candidates = await runtime_repository.candidates(session, task.id)
        visible = (
            current_user.user_id in candidates
            or task.completed_by == current_user.user_id
            or await runtime_repository.has_voted(session, task.id, current_user.user_id)
            or self.can_supervise(current_user, instance)
        )
        if not visible:
            raise AppException("无权查看该待办", status_code=403)
        return task, instance, candidates

    async def detail(self, task_id: UUID, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            task, instance, candidates = await self._visible_task(session, task_id, current_user)
            item = (await self._task_items(session, [(task, instance)], current_user))[0]
            timeline = await self.build_timeline(session, instances=await runtime_repository.instances_for_business(
                session, instance.business_type_code, instance.business_id
            ))
            business_detail = await load_workflow_business_detail(session,current_user=current_user,
                business_type_code=instance.business_type_code,business_id=instance.business_id)
            if item.ai_analysis:
                business_detail = {**business_detail,"fields":[*business_detail.get("fields",[]),
                    {"label":"AI分析（仅供参考）","value":item.ai_analysis}]}
            return {
                **item.model_dump(mode="json"),
                "comment": task.comment,
                "can_act": can_act_on_task(current_user.permissions, current_user.user_id, task.status_code, set(candidates),
                                           assignee_type_code=task.assignee_type_code, assignee_value=task.assignee_value)
                and not await runtime_repository.has_voted(session, task.id, current_user.user_id),
                "business_detail": business_detail,
                "timeline": [entry.model_dump(mode="json") for entry in timeline],
            }

    async def complete(self, task_id: UUID, comment: str | None, current_user: AuthenticatedUser) -> dict:
        return await workflow_runtime_service.advance_task(task_id=task_id, comment=comment, current_user=current_user)

    async def reject(self, task_id: UUID, comment: str | None, current_user: AuthenticatedUser) -> dict:
        return await workflow_runtime_service.reject_instance(task_id=task_id, comment=comment, current_user=current_user)

    # ───────── 抄送 ─────────
    def _cc_item(self, row, summary: str | None) -> dict:
        payload = row.payload or {}
        return {
            "id": str(row.id),
            "instance_id": str(row.instance_id),
            "task_id": str(row.task_id) if row.task_id else None,
            "task_key": row.task_key,
            "task_name": payload.get("task_name"),
            "cc_type_code": row.cc_type_code,
            "business_type_code": row.business_type_code,
            "business_id": str(row.business_id),
            "business_summary": summary,
            "status_code": row.status_code,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "read_at": row.read_at.isoformat() if row.read_at else None,
        }

    async def list_cc_records(self, params: WorkflowCcListQuery, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            rows, total = await runtime_repository.list_cc(
                session,
                user_id=current_user.user_id,
                status_code=params.status_code,
                business_type_code=params.business_type_code,
                business_id=params.business_id,
                page=params.page,
                page_size=params.page_size,
            )
            items = [
                self._cc_item(
                    row,
                    await load_business_summary(session, current_user=current_user, business_type_code=row.business_type_code, business_id=row.business_id),
                )
                for row in rows
            ]
            return _page(items, total, params)

    async def _own_cc(self, session: AsyncSession, cc_id: UUID, current_user: AuthenticatedUser):
        row = await runtime_repository.get_cc(session, cc_id)
        if row is None:
            raise AppException("抄送记录不存在", status_code=404)
        if row.recipient_user_id != current_user.user_id:
            raise AppException("无权查看该抄送记录", status_code=403)
        return row

    async def mark_cc_read(self, cc_id: UUID, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await self._own_cc(session, cc_id, current_user)
            if row.status_code != "read":
                now = utc_now()
                row.status_code = "read"
                row.read_at = now
                row.updated_at = now
                row.updated_by = current_user.user_id
                session.add(row)
                await session.commit()
            return {"id": str(row.id), "status_code": row.status_code}

    async def cc_detail(self, cc_id: UUID, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await self._own_cc(session, cc_id, current_user)
            instance = await runtime_repository.get_instance(session, row.instance_id)
            if instance is None:
                raise AppException("流程实例不存在", status_code=404)
            summary = await load_business_summary(session, current_user=current_user, business_type_code=row.business_type_code, business_id=row.business_id)
            timeline = await self.build_timeline(
                session, instances=await runtime_repository.instances_for_business(session, row.business_type_code, row.business_id)
            )
            return {
                **self._cc_item(row, summary),
                "instance_status_code": instance.status_code,
                "business_detail": await load_workflow_business_detail(
                    session, current_user=current_user, business_type_code=row.business_type_code, business_id=row.business_id
                ),
                "timeline": [entry.model_dump(mode="json") for entry in timeline],
            }

    # ───────── 监督（查看全部审批） ─────────
    async def list_supervision_records(self, params: WorkflowSupervisionListQuery, current_user: AuthenticatedUser) -> dict:
        org_ids = None if has_all_organization_access(current_user, SUPERVISE_PERMISSION) else accessible_org_ids(current_user)
        async with get_session_context() as session:
            instances, total = await runtime_repository.list_instances(
                session,
                status_code=params.status_code,
                business_type_code=params.business_type_code,
                org_ids=org_ids,
                page=params.page,
                page_size=params.page_size,
            )
            pending: dict[UUID, WfTask] = {}
            for instance in instances:
                tasks = await runtime_repository.pending_tasks(session, instance.id)
                if tasks:
                    pending[instance.id] = tasks[0]
            candidates = await runtime_repository.candidate_map(session, [task.id for task in pending.values()])
            names = await user_display_names(session, {uid for ids in candidates.values() for uid in ids})
            items = []
            for instance in instances:
                task = pending.get(instance.id)
                items.append(
                    WorkflowSupervisionListItem(
                        instance_id=instance.id,
                        business_type_code=instance.business_type_code,
                        business_id=instance.business_id,
                        org_id=instance.org_id,
                        instance_status_code=instance.status_code,
                        task_name=task.task_name if task else None,
                        task_key=task.task_key if task else None,
                        approver_names=[names.get(uid, str(uid)) for uid in (candidates.get(task.id, []) if task else [])],
                        business_summary=await load_business_summary(
                            session, current_user=current_user, business_type_code=instance.business_type_code, business_id=instance.business_id
                        ),
                        started_at=instance.started_at,
                    ).model_dump(mode="json")
                )
            return _page(items, total, params)

    async def supervision_detail(self, instance_id: UUID, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            instance = await runtime_repository.get_instance(session, instance_id)
            if instance is None:
                raise AppException("审批实例不存在", status_code=404)
            if not self.can_supervise(current_user, instance):
                raise AppException("无权查看该组织的审批", status_code=403)
            pending = await runtime_repository.pending_tasks(session, instance.id)
            task = pending[0] if pending else None
            timeline = await self.build_timeline(
                session,
                instances=await runtime_repository.instances_for_business(session, instance.business_type_code, instance.business_id),
            )
            return {
                "instance_id": str(instance.id),
                "task_key": task.task_key if task else None,
                "task_name": task.task_name if task else None,
                "business_type_code": instance.business_type_code,
                "business_id": str(instance.business_id),
                "instance_status_code": instance.status_code,
                "business_summary": await load_business_summary(
                    session, current_user=current_user, business_type_code=instance.business_type_code, business_id=instance.business_id
                ),
                "business_detail": await load_workflow_business_detail(
                    session, current_user=current_user, business_type_code=instance.business_type_code, business_id=instance.business_id
                ),
                "timeline": [entry.model_dump(mode="json") for entry in timeline],
                "started_at": instance.started_at.isoformat() if instance.started_at else None,
            }

    # ───────── 审批进度 ─────────
    def _planned_specs(self, version: WfDefinitionVersion, tasks: list[WfTask], variables: dict[str, Any]) -> list[AssigneeSpec]:
        """按流程变量推算本次实例将经过的审批节点（含未到达的节点）。"""
        snapshot = version.spiff_spec_snapshot if isinstance(version.spiff_spec_snapshot, dict) else {}
        raw_design = snapshot.get("design")
        task_keys = {task.task_key for task in tasks}
        if not isinstance(raw_design, dict):
            try:
                specs = extract_user_task_assignees(version.bpmn_xml or "")
            except BpmnValidationError:
                return []
            return specs if "exclusiveGateway" not in (version.bpmn_xml or "") else [s for s in specs if s.task_key in task_keys]
        try:
            design = normalize_flow_design(raw_design)
        except ValidationError:
            return []

        def collect(nodes: list[FlowNodeV3], prefix: str = "") -> list[AssigneeSpec]:
            specs: list[AssigneeSpec] = []
            for node in nodes:
                if isinstance(node, ApprovalNode):
                    specs.append(
                        AssigneeSpec(
                            task_key=f"{prefix}{node.id}",
                            task_name=node.name,
                            assignee_type=node.assignee.type,
                            assignee_value=node.assignee.value or "",
                            approval_mode=node.approval_mode,
                            assignees=tuple((item.type, item.value or "") for item in node.assignees),
                            cc=[],
                        )
                    )
                elif isinstance(node, ExclusiveGatewayNode):
                    branch = self._select_branch(node, variables=variables, task_keys=task_keys, prefix=prefix)
                    if branch is None:
                        return specs
                    specs.extend(collect(branch.nodes, prefix=f"{prefix}{branch.id}__"))
                elif isinstance(node, ParallelGatewayNode):
                    for branch in node.branches:
                        specs.extend(collect(branch.nodes, prefix=f"{prefix}{branch.id}__"))
            return specs

        return collect(design.nodes)

    @staticmethod
    def _condition_matches(expression: ConditionExpression, variables: dict[str, Any]) -> bool | None:
        if expression.field not in variables:
            return None
        left, right = variables.get(expression.field), expression.value
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            try:
                left = float(left)
            except (TypeError, ValueError):
                return None
        ops = {
            "eq": lambda a, b: a == b,
            "ne": lambda a, b: a != b,
            "gt": lambda a, b: a > b,
            "gte": lambda a, b: a >= b,
            "lt": lambda a, b: a < b,
            "lte": lambda a, b: a <= b,
        }
        try:
            return ops[expression.operator](left, right)
        except TypeError:
            return None

    def _select_branch(self, gateway: ExclusiveGatewayNode, *, variables: dict[str, Any], task_keys: set[str], prefix: str):
        reached = next(
            (b for b in gateway.branches if any(key.startswith(f"{prefix}{b.id}__") for key in task_keys)), None
        )
        if reached is not None:
            return reached
        for branch in gateway.branches:
            if branch.id != gateway.default_branch_id and branch.condition is not None:
                matched = self._condition_matches(branch.condition, variables)
                if matched is None:
                    return None
                if matched:
                    return branch
        return next((b for b in gateway.branches if b.id == gateway.default_branch_id), None)

    async def _planned_assignee_names(
        self, session: AsyncSession, instance: WfInstance, spec: AssigneeSpec
    ) -> tuple[str, list[str]]:
        labels: list[str] = []
        user_ids: list[UUID] = []
        for item_type, value in spec.assignees:
            labels.append(
                await assignee_label(session, assignee_type=item_type, assignee_value=value, business_type_code=instance.business_type_code)
            )
            if item_type in DYNAMIC_ASSIGNEE_TYPES:
                continue
            try:
                user_ids.extend(
                    await resolve_assignee_user_ids(
                        session,
                        assignee_type=item_type,
                        assignee_value=value,
                        org_id=instance.org_id,
                        business_type_code=instance.business_type_code,
                        business_id=instance.business_id,
                        starter_user_id=instance.started_by,
                    )
                )
            except AppException:
                continue
        names = await user_display_names(session, set(user_ids))
        return "、".join(labels), list(dict.fromkeys(names[uid] for uid in user_ids if uid in names))

    async def build_timeline(self, session: AsyncSession, *, instances: list[WfInstance]) -> list[WorkflowTimelineItem]:
        instance_ids = [row.id for row in instances]
        tasks = await runtime_repository.tasks_for_instances(session, instance_ids)
        candidates = await runtime_repository.candidate_map(session, [task.id for task in tasks])
        approved = await runtime_repository.approved_counts(session, [task.id for task in tasks])
        actions: list[WfTaskAction] = await runtime_repository.actions_for_instances(
            session, instance_ids, ["submit", "comment", "withdraw"]
        )
        user_ids = {row.started_by for row in instances}
        user_ids |= {task.completed_by for task in tasks if task.completed_by}
        user_ids |= {uid for ids in candidates.values() for uid in ids}
        user_ids |= {action.actor_user_id for action in actions}
        names = await user_display_names(session, user_ids)
        status_by_instance = {row.id: row.status_code for row in instances}
        items: list[WorkflowTimelineItem] = []

        for action in actions:
            if action.action_code == "submit":
                resubmit = bool((action.payload or {}).get("resubmit"))
                code, label = ("resubmit", "重新发起审批") if resubmit else ("submit", "提交审批")
            elif action.action_code == "withdraw":
                code, label = "withdraw", "撤回申请"
            else:
                code, label = "comment", "发表评论"
            items.append(
                WorkflowTimelineItem(
                    occurred_at=action.created_at,
                    action_code=code,
                    action_label=label,
                    actor_name=names.get(action.actor_user_id),
                    comment=action.comment,
                    instance_id=str(action.instance_id),
                    instance_status_code=status_by_instance.get(action.instance_id),
                )
            )

        for instance in instances:
            instance_tasks = [task for task in tasks if task.instance_id == instance.id]
            version = await session.get(WfDefinitionVersion, instance.version_id)
            planned = (
                self._planned_specs(version, instance_tasks, self._runtime_variables(version, instance))
                if version and instance.status_code == "running"
                else []
            )
            reached_keys = {task.task_key for task in instance_tasks}
            for task in instance_tasks:
                task_candidates = candidates.get(task.id, [])
                label = await assignee_label(
                    session,
                    assignee_type=task.assignee_type_code,
                    assignee_value=task.assignee_value,
                    business_type_code=instance.business_type_code,
                )
                if task.status_code == "completed":
                    code = task.outcome_code or "approved"
                    action_label, occurred_at, actor = OUTCOME_LABELS.get(code, code), task.completed_at, names.get(task.completed_by)
                elif task.status_code == TASK_PENDING:
                    code, action_label, occurred_at, actor = "pending", "待办理", task.arrived_at, None
                else:
                    code, action_label, occurred_at, actor = "cancelled", "已取消", task.arrived_at, None
                items.append(
                    WorkflowTimelineItem(
                        occurred_at=occurred_at,
                        action_code=code,
                        action_label=action_label,
                        actor_name=actor,
                        comment=task.comment,
                        task_name=task.task_name,
                        task_key=task.task_key,
                        assignee_label=label,
                        assignee_names=[names.get(uid, str(uid)) for uid in task_candidates],
                        approval_mode_code=task.approval_mode_code,
                        approved_count=approved.get(task.id, 0),
                        required_count=max(len(task_candidates), 1) if task.approval_mode_code == "all" else 1,
                        instance_id=str(instance.id),
                        instance_status_code=instance.status_code,
                    )
                )
            for spec in planned:
                if spec.task_key in reached_keys:
                    continue
                label, planned_names = await self._planned_assignee_names(session, instance, spec)
                items.append(
                    WorkflowTimelineItem(
                        action_code="not_started",
                        action_label="未到达",
                        task_name=spec.task_name or spec.task_key,
                        task_key=spec.task_key,
                        assignee_label=label,
                        assignee_names=planned_names,
                        approval_mode_code=spec.approval_mode,
                        instance_id=str(instance.id),
                        instance_status_code=instance.status_code,
                    )
                )
        items.sort(key=lambda item: item.occurred_at.timestamp() if item.occurred_at else float("inf"))
        return items

    async def timeline_for_business(
        self, business_type_code: str, business_id: UUID, current_user: AuthenticatedUser
    ) -> WorkflowTimelineResult:
        async with get_session_context() as session:
            instances = await runtime_repository.instances_for_business(session, business_type_code, business_id)
            _, _, participant = await self._participation(session, current_user, instances)
            if instances and not participant:
                can_view = await runtime_repository.is_cc_recipient(
                    session, [row.id for row in instances], current_user.user_id
                ) or self.can_supervise(current_user, instances[-1])
                if not can_view:
                    raise AppException("无权查看该审批进度", status_code=403)
            items = await self.build_timeline(session, instances=instances)
            latest = instances[-1] if instances else None
            resubmit_owner = bool(latest and latest.status_code == "rejected" and latest.started_by == current_user.user_id)
            record = await self._business_record(session, business_type_code, business_id) if resubmit_owner else None
            rejected_at = await self._rejection_edit_baseline(session, latest)
            edited = self._edited_after_rejection(record, rejected_at)
            adapter = get_business_adapter(business_type_code)
            may_start = not adapter or adapter.may_start(current_user)
            return WorkflowTimelineResult(
                business_type_code=business_type_code,
                business_id=business_id,
                items=items,
                latest_instance_status_code=latest.status_code if latest else None,
                org_id=latest.org_id if latest else None,
                can_comment=bool(instances and participant),
                can_resubmit=bool(resubmit_owner and edited and may_start),
                requires_edit_before_resubmit=bool(resubmit_owner and not edited),
                edit_saved_after_rejection=edited,
            )


workflow_task_service = WorkflowTaskService()
