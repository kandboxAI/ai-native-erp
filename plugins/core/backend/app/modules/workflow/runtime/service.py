from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.workflow.definition.repository import repository as definition_repository
from app.modules.workflow.integration.registry import WorkflowHookContext, dispatch_hook, get_business_adapter
from app.modules.workflow.models import WfCcRecord, WfDefinition, WfDefinitionVersion, WfInstance, WfTask
from app.modules.workflow.notification import build_workflow_event_payload, emit_workflow_event, send_notification
from app.modules.workflow.runtime.assignee_resolver import (
    user_display_names,
    assignee_spec_for_task,
    can_act_on_task,
    resolve_assignee_user_ids,
    search_selectable_users,
    validate_selectable_user_ids,
    validate_workflow_approver_user_ids,
)
from app.modules.workflow.runtime.repository import INSTANCE_RUNNING, TASK_PENDING, runtime_repository
from app.modules.workflow.spiff_runner import (
    AssigneeSpec,
    ReadyUserTask,
    complete_user_task,
    create_workflow,
    deserialize_workflow,
    extract_user_task_assignees,
    get_ready_user_tasks,
    get_task_data,
    serialize_workflow,
    workflow_is_completed,
    workflow_is_rejected,
)

STARTER_CHOICES_VARIABLE = "__workflow_starter_choices"
TASK_REDIRECT_URL = "/pages/todo/index"
RESULT_LABELS = {"completed": "已通过", "rejected": "已驳回"}
OUTCOME_APPROVED = "approved"  # 字典 wf_task_outcome
OUTCOME_REJECTED = "rejected"


def business_label(business_type_code: str) -> str:
    adapter = get_business_adapter(business_type_code)
    return adapter.label if adapter else business_type_code


def workflow_definition_missing_message(business_type_code: str) -> str:
    return (
        f"当前租户未配置已启用的「{business_type_code and business_label(business_type_code)}」审批流程，"
        "请先在「流程定义」中配置并发布后再提交。"
    )


def _parse_choices(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): [str(v) for v in values] for key, values in raw.items() if isinstance(values, list)}


class WorkflowRuntimeService:
    async def definition_options(self, session, *, business_type_code, org_id):
        return await definition_repository.published_definition_options(session,
            business_type_code=business_type_code, org_id=org_id)

    async def get_active_definition(
        self, session: AsyncSession, business_type_code: str, org_id: UUID, *, definition_id: UUID | None = None
    ) -> tuple[WfDefinition, WfDefinitionVersion]:
        found = await definition_repository.find_active_definition(
            session, business_type_code=business_type_code, org_id=org_id, definition_id=definition_id
        )
        if found is None:
            raise AppException(workflow_definition_missing_message(business_type_code), status_code=400)
        return found

    # ───────── 发起人选择 ─────────
    @staticmethod
    def starter_selection_specs(version: WfDefinitionVersion) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for task in extract_user_task_assignees(version.bpmn_xml or ""):
            for assignee_type, assignee_value in task.assignees:
                if assignee_type == "starter_select" and assignee_value not in seen:
                    seen.add(assignee_value)
                    specs.append({"key": assignee_value, "name": task.task_name or "审批人", "kind": "approval", "multiple": True})
            for cc in task.cc:
                if cc.cc_type == "starter_select" and cc.cc_value not in seen:
                    seen.add(cc.cc_value)
                    specs.append({"key": cc.cc_value, "name": cc.node_name or "抄送人", "kind": "cc", "multiple": True})
        return specs

    async def _validate_starter_choices(
        self,
        session: AsyncSession,
        *,
        version: WfDefinitionVersion,
        org_id: UUID,
        starter_choices: dict[str, list[UUID]] | None,
    ) -> dict[str, list[str]]:
        provided = starter_choices or {}
        normalized: dict[str, list[str]] = {}
        for requirement in self.starter_selection_specs(version):
            selected = list(dict.fromkeys(provided.get(requirement["key"], [])))
            if not selected:
                raise AppException(f"请由发起人选择「{requirement['name']}」", status_code=400)
            valid = await validate_selectable_user_ids(session, user_ids=selected, org_id=org_id)
            if len(valid) != len(selected):
                raise AppException(f"「{requirement['name']}」包含已停用或无当前租户权限的人员", status_code=400)
            if requirement["kind"] == "approval":
                approvers = await validate_workflow_approver_user_ids(session, user_ids=valid)
                if len(approvers) != len(valid):
                    raise AppException(f"「{requirement['name']}」包含没有审批办理权限的人员", status_code=400)
            normalized[requirement["key"]] = [str(user_id) for user_id in valid]
        return normalized

    # ───────── 候选人解析 ─────────
    async def _resolve_user_ids(
        self,
        session: AsyncSession,
        *,
        instance: WfInstance,
        assignee_type: str,
        assignee_value: str | None,
        runtime_data: dict[str, Any] | None,
    ) -> list[UUID]:
        user_ids = await resolve_assignee_user_ids(
            session,
            assignee_type=assignee_type,
            assignee_value=assignee_value,
            org_id=instance.org_id,
            business_type_code=instance.business_type_code,
            business_id=instance.business_id,
            starter_user_id=instance.started_by,
            starter_choices=_parse_choices((runtime_data or {}).get(STARTER_CHOICES_VARIABLE)),
        )
        return await validate_selectable_user_ids(session, user_ids=list(dict.fromkeys(user_ids)), org_id=instance.org_id)

    async def _create_cc_records_for_task(
        self,
        session: AsyncSession,
        *,
        instance: WfInstance,
        task: WfTask,
        spec: AssigneeSpec,
        user_id: UUID | None,
        trigger: str,
        runtime_data: dict[str, Any] | None = None,
    ) -> list[UUID]:
        recipient_ids: list[UUID] = []
        for cc in (item for item in spec.cc if item.trigger == trigger):
            user_ids = await self._resolve_user_ids(
                session, instance=instance, assignee_type=cc.cc_type, assignee_value=cc.cc_value, runtime_data=runtime_data
            )
            if not user_ids:
                raise AppException(f"抄送节点「{cc.node_name or task.task_name}」没有可用接收人", status_code=400)
            for recipient in user_ids:
                if recipient in recipient_ids:
                    continue
                recipient_ids.append(recipient)
                runtime_repository.add_cc(
                    session,
                    WfCcRecord(
                        org_id=instance.org_id,
                        instance_id=instance.id,
                        task_id=task.id,
                        task_key=cc.node_key or task.task_key,
                        business_type_code=instance.business_type_code,
                        business_id=instance.business_id,
                        cc_type_code=cc.cc_type,
                        recipient_user_id=recipient,
                        status_code="unread",
                        payload={
                            "trigger": trigger,
                            "cc_value": cc.cc_value,
                            "task_name": cc.node_name or task.task_name,
                            "source_task_key": task.task_key,
                        },
                        created_by=user_id,
                        updated_by=user_id,
                    ),
                )
        if recipient_ids:
            await emit_workflow_event(
                session,
                event_type="wf.cc.sent",
                payload=build_workflow_event_payload(
                    event_type="wf.cc.sent",
                    instance_id=instance.id,
                    business_type_code=instance.business_type_code,
                    business_id=instance.business_id,
                    org_id=instance.org_id,
                    task_id=task.id,
                    task_key=task.task_key,
                    task_name=task.task_name,
                    actor_user_id=user_id,
                    recipient_user_ids=recipient_ids,
                    extra={"trigger": trigger},
                ),
            )
        return recipient_ids

    async def _create_tasks_for_ready(
        self,
        session: AsyncSession,
        *,
        instance: WfInstance,
        version: WfDefinitionVersion,
        ready_tasks: list[ReadyUserTask],
        user_id: UUID | None,
    ) -> list[WfTask]:
        specs = extract_user_task_assignees(version.bpmn_xml or "")
        created: list[WfTask] = []
        for ready in ready_tasks:
            spec = assignee_spec_for_task(specs, ready.task_key)
            if spec is None:
                raise AppException(f"BPMN 缺少节点 {ready.task_key} 的审批人配置", status_code=500)
            task_name = spec.task_name or ready.task_name or ready.task_key
            candidate_ids: list[UUID] = []
            for source_type, source_value in spec.assignees:
                source_ids = await self._resolve_user_ids(
                    session, instance=instance, assignee_type=source_type, assignee_value=source_value, runtime_data=ready.data
                )
                if not source_ids:
                    raise AppException(f"审批节点「{task_name}」的审批对象 {source_type}:{source_value} 没有可用审批人", status_code=400)
                candidate_ids.extend(source_ids)
            candidate_ids = list(dict.fromkeys(candidate_ids))
            actionable_ids = await validate_workflow_approver_user_ids(session, user_ids=candidate_ids)
            if not actionable_ids:
                raise AppException(f"审批节点「{task_name}」没有拥有办理权限（workflow_task:complete）的审批人", status_code=400)
            task = WfTask(
                org_id=instance.org_id,
                instance_id=instance.id,
                task_key=ready.task_key,
                task_name=task_name[:128],
                spiff_task_no=str(ready.spiff_task_no),
                assignee_type_code=spec.assignee_type,
                assignee_value=(spec.assignee_value or "")[:256] or None,
                approval_mode_code=spec.approval_mode,
                status_code=TASK_PENDING,
                arrived_at=utc_now(),
                created_by=user_id,
                updated_by=user_id,
                flex_form={"assignees": [list(item) for item in spec.assignees]} if len(spec.assignees) > 1 else {},
            )
            await runtime_repository.add_task(session, task, actionable_ids, user_id)
            from app.modules.workflow.todo_service import sync_task
            await sync_task(session, task, user_id)
            created.append(task)
            cc_ids = await self._create_cc_records_for_task(
                session, instance=instance, task=task, spec=spec, user_id=user_id, trigger="task_arrived", runtime_data=ready.data
            )
            applicant_name = (await user_display_names(session, {instance.started_by})).get(instance.started_by, "")
            from app.modules.workflow.todo_service import task_targets
            await send_notification(
                session,
                scene_key="workflow.task.pending",
                actors={"approver": actionable_ids},
                business_type_code=instance.business_type_code,
                business_id=instance.business_id,
                org_id=instance.org_id,
                event_key=f"workflow.task.pending:{task.id}",
                source_module_code="workflow",
                created_by=user_id,
                payload={
                    "instance_id": str(instance.id),
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "task_name": task.task_name,
                    "task_title": task.task_name,
                    "business_name": business_label(instance.business_type_code),
                    "applicant_name": applicant_name,
                    "redirect_url": TASK_REDIRECT_URL,
                    "targets": task_targets(task.id),
                },
            )
            await emit_workflow_event(
                session,
                event_type="wf.task.created",
                payload=build_workflow_event_payload(
                    event_type="wf.task.created",
                    instance_id=instance.id,
                    business_type_code=instance.business_type_code,
                    business_id=instance.business_id,
                    org_id=instance.org_id,
                    task_id=task.id,
                    task_key=task.task_key,
                    task_name=task.task_name,
                    actor_user_id=user_id,
                    recipient_user_ids=actionable_ids,
                    extra={
                        "business_label": business_label(instance.business_type_code),
                        "cc_recipient_user_ids": [str(i) for i in cc_ids],
                        "started_by": str(instance.started_by),
                    },
                ),
            )
        return created

    async def _sync_runtime_state(
        self, session: AsyncSession, *, instance: WfInstance, version: WfDefinitionVersion, workflow, user_id: UUID | None
    ) -> list[WfTask]:
        instance.workflow_state_snapshot = serialize_workflow(workflow)
        ready = get_ready_user_tasks(workflow)
        instance.bpmn_activity_no = ready[0].task_key if ready else None
        instance.updated_at = utc_now()
        instance.updated_by = user_id
        session.add(instance)
        await session.flush()
        ready_ids = {str(item.spiff_task_no) for item in ready}
        pending = await runtime_repository.pending_tasks(session, instance.id)
        kept = [task for task in pending if str(task.spiff_task_no) in ready_ids]
        await runtime_repository.cancel_pending_tasks(session, instance.id, user_id, keep_ids=[task.id for task in kept])
        from app.modules.workflow.todo_service import sync_instance
        await sync_instance(session, instance.id, user_id)
        existing = {str(task.spiff_task_no) for task in kept}
        new_ready = [item for item in ready if str(item.spiff_task_no) not in existing]
        if not new_ready:
            return []
        return await self._create_tasks_for_ready(session, instance=instance, version=version, ready_tasks=new_ready, user_id=user_id)

    async def _finalize_instance(
        self,
        session: AsyncSession,
        *,
        instance: WfInstance,
        workflow,
        current_user: AuthenticatedUser | None,
        comment: str | None,
        forced_status: str | None = None,
    ) -> WfInstance:
        final_status = forced_status or ("rejected" if workflow_is_rejected(workflow) else "completed")
        now = utc_now()
        instance.workflow_state_snapshot = serialize_workflow(workflow)
        instance.status_code = final_status
        instance.ended_at = now
        instance.bpmn_activity_no = None
        instance.updated_at = now
        instance.updated_by = current_user.user_id if current_user else None
        await runtime_repository.cancel_pending_tasks(session, instance.id, instance.updated_by)
        from app.modules.workflow.todo_service import sync_instance
        await sync_instance(session, instance.id, instance.updated_by)
        session.add(instance)
        await emit_workflow_event(
            session,
            event_type=f"wf.instance.{final_status}",
            payload=build_workflow_event_payload(
                event_type=f"wf.instance.{final_status}",
                instance_id=instance.id,
                business_type_code=instance.business_type_code,
                business_id=instance.business_id,
                org_id=instance.org_id,
                actor_user_id=instance.updated_by,
                recipient_user_ids=[instance.started_by],
                extra={"status_code": final_status, "comment": comment},
            ),
        )
        adapter = get_business_adapter(instance.business_type_code)
        if not (adapter and adapter.notifies_result):
            label = business_label(instance.business_type_code)
            await send_notification(
                session,
                scene_key="workflow.instance.completed",
                actors={"applicant": [instance.started_by]},
                business_type_code=instance.business_type_code,
                business_id=instance.business_id,
                org_id=instance.org_id,
                event_key=f"workflow.instance.completed:{instance.id}",
                source_module_code="workflow",
                created_by=instance.updated_by,
                payload={
                    "title": f"{label}{RESULT_LABELS.get(final_status, '')}",
                    "content": f"您提交的{label}{RESULT_LABELS.get(final_status, '')}" + (f"：{comment}" if comment else ""),
                    "status_code": final_status,
                },
            )
        await dispatch_hook(
            instance.business_type_code,
            final_status,
            WorkflowHookContext(
                session=session,
                instance_id=instance.id,
                business_type_code=instance.business_type_code,
                business_id=instance.business_id,
                org_id=instance.org_id,
                status_code=final_status,
                current_user=current_user,
                comment=comment,
            ),
        )
        return instance

    # ───────── 发起 ─────────
    async def _start_in_session(
        self,
        session: AsyncSession,
        *,
        business_type_code: str,
        business_id: UUID,
        org_id: UUID | None,
        variables: dict[str, Any] | None,
        starter_choices: dict[str, list[UUID]] | None,
        current_user: AuthenticatedUser,
        start_comment: str | None = None,
        previous_instance_id: UUID | None = None,
        definition_id: UUID | None = None,
    ) -> WfInstance:
        if await runtime_repository.running_instance_for_business(session, business_type_code, business_id) is not None:
            raise AppException("该业务单已有进行中的流程", status_code=409)
        org_id = org_id or current_user.org_id
        if org_id is None:
            raise AppException("请指定流程所属组织", status_code=400)
        definition, version = await self.get_active_definition(session, business_type_code, org_id, definition_id=definition_id)
        normalized_choices = await self._validate_starter_choices(
            session, version=version, org_id=org_id, starter_choices=starter_choices
        )
        bootstrap_variables = {**(variables or {}), STARTER_CHOICES_VARIABLE: normalized_choices}
        workflow, _ = create_workflow(
            version.bpmn_xml or "", process_id=version.bpmn_process_no, bootstrap_variables=bootstrap_variables
        )
        now = utc_now()
        instance = WfInstance(
            org_id=org_id,
            definition_id=definition.id,
            version_id=version.id,
            business_type_code=business_type_code,
            business_id=business_id,
            status_code=INSTANCE_RUNNING,
            workflow_state_snapshot={},
            started_by=current_user.user_id,
            started_at=now,
            created_by=current_user.user_id,
            updated_by=current_user.user_id,
        )
        session.add(instance)
        await session.flush()
        runtime_repository.add_action(
            session,
            instance=instance,
            task_id=None,
            action_code="submit",
            actor_user_id=current_user.user_id,
            comment=start_comment,
            payload={
                "resubmit": previous_instance_id is not None,
                "previous_instance_id": str(previous_instance_id) if previous_instance_id else None,
            },
        )
        await self._sync_runtime_state(session, instance=instance, version=version, workflow=workflow, user_id=current_user.user_id)
        await dispatch_hook(
            business_type_code,
            "started",
            WorkflowHookContext(
                session=session,
                instance_id=instance.id,
                business_type_code=business_type_code,
                business_id=business_id,
                org_id=org_id,
                status_code=INSTANCE_RUNNING,
                current_user=current_user,
            ),
        )
        return instance

    async def start(
        self,
        *,
        business_type_code: str,
        business_id: UUID,
        org_id: UUID | None,
        variables: dict[str, Any] | None,
        starter_choices: dict[str, list[UUID]] | None = None,
        current_user: AuthenticatedUser,
        session: AsyncSession | None = None,
        start_comment: str | None = None,
        previous_instance_id: UUID | None = None,
        definition_id: UUID | None = None,
    ) -> WfInstance:
        """启动流程。传入 session 时与业务单同事务提交，失败则一并回滚。"""
        kwargs = dict(
            business_type_code=business_type_code,
            business_id=business_id,
            org_id=org_id,
            variables=variables,
            starter_choices=starter_choices,
            current_user=current_user,
            start_comment=start_comment,
            previous_instance_id=previous_instance_id,
            definition_id=definition_id,
        )
        if session is not None:
            return await self._start_in_session(session, **kwargs)
        async with get_session_context() as owned_session:
            instance = await self._start_in_session(owned_session, **kwargs)
            await owned_session.commit()
            await owned_session.refresh(instance)
            return instance

    async def start_requirements(self, *, business_type_code: str, org_id: UUID, definition_id: UUID | None = None) -> dict[str, Any]:
        async with get_session_context() as session:
            definition, version = await self.get_active_definition(session, business_type_code, org_id, definition_id=definition_id)
            return {
                "definition_id": str(definition.id),
                "version_id": str(version.id),
                "selection_nodes": self.starter_selection_specs(version),
            }

    async def starter_candidates(self, *, keyword: str | None, org_id: UUID | None, limit: int) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            rows = await search_selectable_users(session, keyword=keyword, org_id=org_id, limit=limit)
            return [{"id": str(row.id), "display_name": row.display_name} for row in rows]

    async def get_by_business(self, *, business_type_code: str, business_id: UUID) -> dict[str, Any] | None:
        async with get_session_context() as session:
            instances = await runtime_repository.instances_for_business(session, business_type_code, business_id)
            if not instances:
                return None
            instance = instances[-1]
            pending = await runtime_repository.pending_tasks(session, instance.id)
            candidates = await runtime_repository.candidate_map(session, [task.id for task in pending])
            return {"instance": instance, "pending_tasks": pending, "candidates": candidates}

    # ───────── 办理 ─────────
    async def _load_task_for_action(
        self, session: AsyncSession, task_id: UUID, current_user: AuthenticatedUser
    ) -> tuple[WfTask, WfInstance, WfDefinitionVersion, Any, list[UUID]]:
        task = await runtime_repository.get_task(session, task_id)
        if task is None:
            raise AppException("待办任务不存在", status_code=404)
        # 并行审批共享一份运行快照，先锁实例，再锁具体审批任务。
        instance = await runtime_repository.get_instance(session, task.instance_id, for_update=True)
        if instance is None:
            raise AppException("流程实例不存在", status_code=404)
        if instance.status_code != INSTANCE_RUNNING:
            raise AppException("流程已结束，无法继续办理", status_code=409)
        task = await runtime_repository.get_task(session, task_id, for_update=True)
        if task is None:
            raise AppException("待办任务不存在", status_code=404)
        candidates = await runtime_repository.candidates(session, task.id)
        if not can_act_on_task(current_user.permissions, current_user.user_id, task.status_code, set(candidates),
                               assignee_type_code=task.assignee_type_code, assignee_value=task.assignee_value):
            raise AppException("无权办理该任务", status_code=403)
        if await runtime_repository.has_voted(session, task.id, current_user.user_id):
            raise AppException("您已经办理过该审批节点，请勿重复提交", status_code=409)
        version = await definition_repository.get_version(session, instance.version_id)
        workflow = deserialize_workflow(
            version.bpmn_xml or "", instance.workflow_state_snapshot or {}, process_id=version.bpmn_process_no
        )
        # 业务可在任何投票落库前收紧办理边界；未注册此事件的业务保持原行为。
        await dispatch_hook(instance.business_type_code, "before_action", WorkflowHookContext(
            session=session, instance_id=instance.id, business_type_code=instance.business_type_code,
            business_id=instance.business_id, org_id=instance.org_id, status_code=instance.status_code,
            current_user=current_user,
        ))
        return task, instance, version, workflow, candidates

    async def advance_task(self, *, task_id: UUID, comment: str | None, current_user: AuthenticatedUser) -> dict[str, Any]:
        """同意。会签（all）需全部候选人同意后才推进。"""
        async with get_session_context() as session:
            task, instance, version, workflow, candidates = await self._load_task_for_action(session, task_id, current_user)
            runtime_repository.add_action(
                session,
                instance=instance,
                task_id=task.id,
                action_code="approve",
                actor_user_id=current_user.user_id,
                comment=comment,
                payload={"task_key": task.task_key, "approval_mode_code": task.approval_mode_code},
            )
            await session.flush()
            if task.approval_mode_code == "all":
                approved = await runtime_repository.approved_user_ids(session, task.id)
                if not set(candidates).issubset(approved):
                    task.updated_at = utc_now()
                    task.updated_by = current_user.user_id
                    session.add(task)
                    from app.modules.workflow.todo_service import sync_instance
                    await sync_instance(session, instance.id, current_user.user_id)
                    await session.commit()
                    return {
                        "task_id": str(task.id),
                        "instance_id": str(instance.id),
                        "instance_status_code": instance.status_code,
                        "outcome_code": "pending",
                        "approval_mode_code": "all",
                        "approved_count": len(approved & set(candidates)),
                        "required_count": len(candidates),
                    }

            spiff_no = UUID(str(task.spiff_task_no))
            runtime_data = get_task_data(workflow, spiff_no)
            complete_user_task(workflow, spiff_no, variables={"outcome": "approve"})
            now = utc_now()
            task.status_code = "completed"
            task.outcome_code = OUTCOME_APPROVED
            task.comment = comment
            task.completed_at = now
            task.completed_by = current_user.user_id
            task.assignee_user_id = current_user.user_id
            task.updated_at = now
            task.updated_by = current_user.user_id
            session.add(task)

            spec = assignee_spec_for_task(extract_user_task_assignees(version.bpmn_xml or ""), task.task_key)
            if spec is not None:
                await self._create_cc_records_for_task(
                    session, instance=instance, task=task, spec=spec, user_id=current_user.user_id,
                    trigger="task_completed", runtime_data=runtime_data,
                )
            await emit_workflow_event(
                session,
                event_type="wf.task.completed",
                payload=build_workflow_event_payload(
                    event_type="wf.task.completed",
                    instance_id=instance.id,
                    business_type_code=instance.business_type_code,
                    business_id=instance.business_id,
                    org_id=instance.org_id,
                    task_id=task.id,
                    task_key=task.task_key,
                    task_name=task.task_name,
                    actor_user_id=current_user.user_id,
                    extra={"outcome_code": OUTCOME_APPROVED, "comment": comment},
                ),
            )
            if workflow_is_completed(workflow) or workflow_is_rejected(workflow):
                await self._finalize_instance(session, instance=instance, workflow=workflow, current_user=current_user, comment=comment)
            else:
                await self._sync_runtime_state(session, instance=instance, version=version, workflow=workflow, user_id=current_user.user_id)
                await dispatch_hook(
                    instance.business_type_code,
                    "task_completed",
                    WorkflowHookContext(
                        session=session,
                        instance_id=instance.id,
                        business_type_code=instance.business_type_code,
                        business_id=instance.business_id,
                        org_id=instance.org_id,
                        status_code=INSTANCE_RUNNING,
                        current_user=current_user,
                        comment=comment,
                        payload={"outcome_code": OUTCOME_APPROVED, "task_key": task.task_key, "task_name": task.task_name},
                    ),
                )
            await session.commit()
            return {
                "task_id": str(task.id),
                "instance_id": str(instance.id),
                "instance_status_code": instance.status_code,
                "outcome_code": OUTCOME_APPROVED,
            }

    async def reject_instance(self, *, task_id: UUID, comment: str | None, current_user: AuthenticatedUser) -> dict[str, Any]:
        """驳回：结束流程，业务单回到可修改状态，修改后可重新发起。"""
        async with get_session_context() as session:
            task, instance, _version, workflow, _ = await self._load_task_for_action(session, task_id, current_user)
            now = utc_now()
            task.status_code = "completed"
            task.outcome_code = OUTCOME_REJECTED
            task.comment = comment
            task.completed_at = now
            task.completed_by = current_user.user_id
            task.assignee_user_id = current_user.user_id
            task.updated_at = now
            task.updated_by = current_user.user_id
            session.add(task)
            reject_action = runtime_repository.add_action(
                session,
                instance=instance,
                task_id=task.id,
                action_code="reject",
                actor_user_id=current_user.user_id,
                comment=comment,
                payload={"task_key": task.task_key, "approval_mode_code": task.approval_mode_code},
            )
            await emit_workflow_event(
                session,
                event_type="wf.task.rejected",
                payload=build_workflow_event_payload(
                    event_type="wf.task.rejected",
                    instance_id=instance.id,
                    business_type_code=instance.business_type_code,
                    business_id=instance.business_id,
                    org_id=instance.org_id,
                    task_id=task.id,
                    task_key=task.task_key,
                    task_name=task.task_name,
                    actor_user_id=current_user.user_id,
                    extra={"outcome_code": OUTCOME_REJECTED, "comment": comment},
                ),
            )
            await self._finalize_instance(
                session, instance=instance, workflow=workflow, current_user=current_user, comment=comment, forced_status="rejected"
            )
            # 驳回钩子也会更新原单据；记录钩子完成后的时刻，重新发起时要求原单据在此之后再次保存
            reject_action.payload = {**(reject_action.payload or {}), "edit_required_after": utc_now().isoformat()}
            session.add(reject_action)
            await session.commit()
            return {
                "task_id": str(task.id),
                "instance_id": str(instance.id),
                "instance_status_code": instance.status_code,
                "outcome_code": OUTCOME_REJECTED,
            }

    async def cancel_by_business(
        self,
        *,
        business_type_code: str,
        business_id: UUID,
        current_user: AuthenticatedUser,
        session: AsyncSession | None = None,
    ) -> bool:
        """撤销进行中的流程（发起人撤回）。"""
        if session is None:
            async with get_session_context() as owned:
                result = await self.cancel_by_business(
                    business_type_code=business_type_code, business_id=business_id, current_user=current_user, session=owned
                )
                await owned.commit()
                return result
        instance = await runtime_repository.running_instance_for_business(session, business_type_code, business_id, for_update=True)
        if instance is None:
            return False
        now = utc_now()
        instance.status_code = "cancelled"
        instance.ended_at = now
        instance.bpmn_activity_no = None
        instance.updated_at = now
        instance.updated_by = current_user.user_id
        session.add(instance)
        await runtime_repository.cancel_pending_tasks(session, instance.id, current_user.user_id)
        from app.modules.workflow.todo_service import sync_instance
        await sync_instance(session, instance.id, current_user.user_id)
        runtime_repository.add_action(
            session, instance=instance, task_id=None, action_code="withdraw", actor_user_id=current_user.user_id
        )
        await dispatch_hook(
            business_type_code,
            "cancelled",
            WorkflowHookContext(
                session=session,
                instance_id=instance.id,
                business_type_code=business_type_code,
                business_id=business_id,
                org_id=instance.org_id,
                status_code="cancelled",
                current_user=current_user,
            ),
        )
        await emit_workflow_event(
            session,
            event_type="wf.instance.cancelled",
            payload=build_workflow_event_payload(
                event_type="wf.instance.cancelled",
                instance_id=instance.id,
                business_type_code=instance.business_type_code,
                business_id=instance.business_id,
                org_id=instance.org_id,
                actor_user_id=current_user.user_id,
                extra={"status_code": "cancelled"},
            ),
        )
        return True


workflow_runtime_service = WorkflowRuntimeService()
