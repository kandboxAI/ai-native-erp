from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context
from app.modules.permission.models import SysPermission

from ..bpmn_compiler import compile_flow_design
from ..business_types import assert_valid_workflow_business_type, list_workflow_business_types
from ..condition_fields import condition_field_items, validate_design_conditions, validation_variables_for
from ..design_models import (
    ASSIGNEE_TYPE_LABELS,
    default_designs,
    ApprovalNode,
    AssigneeConfig,
    FlowDesign,
    FlowDesignV3,
    normalize_flow_design,
)
from ..integration.registry import get_business_adapter
from ..runtime.assignee_resolver import (
    resolve_assignee_user_ids,
    search_selectable_users,
    user_display_names,
    validate_selectable_user_ids,
    validate_workflow_approver_user_ids,
)
from ..schemas import (
    VersionPublishBody,
    VersionSaveDesignBody,
    VersionUploadBody,
    WorkflowDefinitionDetailItem,
    WorkflowDefinitionItem,
    WorkflowDefinitionListQuery,
    WorkflowDefinitionVersionItem,
)
from ..spiff_runner import BpmnValidationError, extract_user_task_assignees, validate_bpmn
from .repository import DESIGNER_SOURCES, repository, version_item

DESIGNER_SOURCE = "designer_v3"


def _design_snapshot(design: FlowDesignV3) -> dict:
    return {"source": DESIGNER_SOURCE, "design": design.model_dump(mode="json")}


def compile_and_validate(design: FlowDesign | dict, business_type_code: str):
    design = normalize_flow_design(design)
    validate_design_conditions(design, business_type_code)
    bpmn_process_no, bpmn_xml = compile_flow_design(design)
    meta = validate_bpmn(
        bpmn_xml,
        process_id=bpmn_process_no,
        validation_variables=validation_variables_for(business_type_code),
    )
    return design, bpmn_process_no, bpmn_xml, meta


def validate_assignee_config(bpmn_xml: str, business_type_code: str) -> None:
    """发布前校验：业务负责人须已由业务模块登记。"""
    adapter = get_business_adapter(business_type_code)
    for task in extract_user_task_assignees(bpmn_xml):
        items = [*task.assignees, *((cc.cc_type, cc.cc_value) for cc in task.cc)]
        for item_type, value in items:
            if item_type == "business_owner" and (adapter is None or value not in adapter.business_owners):
                raise AppException(
                    f"节点「{task.task_name or task.task_key}」的业务负责人「{value}」未在业务类型「{business_type_code}」中登记",
                    status_code=400,
                )


def _user_tasks_payload(meta) -> list[dict]:
    return [
        {
            "task_key": t.task_key,
            "task_name": t.task_name,
            "assignee_type_code": t.assignee_type,
            "assignee_value": t.assignee_value,
        }
        for t in meta.user_tasks
    ]


class WorkflowDefinitionService(CrudService):
    async def list_business_types(self) -> list[dict[str, str]]:
        async with self.session_getter() as session:
            return await list_workflow_business_types(session)

    async def create(self, payload: dict, current_user: AuthenticatedUser):
        definition_no = (payload.get("definition_no") or "").strip()
        if not definition_no:
            raise AppException("请提供流程编号", status_code=400)
        payload = {**payload, "definition_no": definition_no, "is_active": False}
        payload["org_id"] = resolve_write_org_id(current_user, payload.get("org_id"), "workflow_definition:create")
        async with self.session_getter() as session:
            await assert_valid_workflow_business_type(session, payload.get("business_type_code"))
            await repository.assert_org_exists(session, payload.get("org_id"))
            item = await repository.create(session, payload, current_user)
            entity = await repository.get_entity(session, item.id)
            return await repository.to_item(session, entity)

    async def update(self, item_id: str, payload: dict, current_user: AuthenticatedUser):
        payload = dict(payload)
        payload.pop("definition_no", None)
        async with self.session_getter() as session:
            if payload.get("business_type_code") is not None:
                await assert_valid_workflow_business_type(session, payload["business_type_code"])
            if payload.get("org_id") is not None:
                await repository.assert_org_exists(session, payload["org_id"])
            entity = await repository.get_entity(session, UUID(item_id))
            next_active = payload.get("is_active", entity.is_active)
            if next_active and entity.current_version_id is None:
                raise AppException("请先发布流程版本再启用", status_code=400)
            if next_active and payload.get("is_default", entity.is_default):
                await repository.disable_other_active_in_org(
                    session,
                    business_type_code=str(payload.get("business_type_code") or entity.business_type_code),
                    org_id=payload.get("org_id") or entity.org_id,
                    exclude_definition_id=entity.id,
                    user_id=current_user.user_id,
                )
            updated = await repository.update(session, item_id, payload, current_user)
            if updated is None:
                return None
            return await repository.to_item(session, await repository.get_entity(session, UUID(item_id)))

    async def list_definitions(self, params: WorkflowDefinitionListQuery, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            items, total = await repository.list_with_filters(session, params, current_user=current_user)
            return {
                "items": [i.model_dump(mode="json") for i in items],
                "total": total,
                "page": params.page,
                "page_size": params.page_size,
            }

    async def get_detail(self, item_id: str) -> WorkflowDefinitionDetailItem:
        async with self.session_getter() as session:
            return await repository.get_detail(session, UUID(item_id))

    async def upload_version(self, body: VersionUploadBody, current_user: AuthenticatedUser) -> WorkflowDefinitionVersionItem:
        async with self.session_getter() as session:
            definition = await repository.get_entity(session, body.definition_id)
            meta = validate_bpmn(
                body.bpmn_xml,
                process_id=body.bpmn_process_no,
                validation_variables=validation_variables_for(definition.business_type_code),
            )
            validate_assignee_config(body.bpmn_xml, definition.business_type_code)
            row = await repository.create_version(
                session,
                definition_id=body.definition_id,
                bpmn_xml=body.bpmn_xml,
                bpmn_process_no=meta.bpmn_process_no,
                user_id=current_user.user_id,
                remark=body.remark,
                spiff_spec_snapshot={"source": "bpmn_upload"},
            )
            await session.commit()
            return version_item(row)

    async def publish_version(
        self,
        version_id: str,
        current_user: AuthenticatedUser,
        *,
        body: VersionPublishBody | None = None,
    ) -> WorkflowDefinitionItem:
        async with self.session_getter() as session:
            version = await repository.get_version(session, UUID(version_id))
            if body and body.remark:
                version.flex_form = {**(version.flex_form or {}), "remark": body.remark}
            definition = await repository.get_entity(session, version.definition_id)
            snapshot = version.spiff_spec_snapshot if isinstance(version.spiff_spec_snapshot, dict) else {}
            if snapshot.get("source") in DESIGNER_SOURCES and snapshot.get("design"):
                _, bpmn_process_no, bpmn_xml, _ = compile_and_validate(snapshot["design"], definition.business_type_code)
                version.bpmn_xml = bpmn_xml
                version.bpmn_process_no = bpmn_process_no
            validate_bpmn(
                version.bpmn_xml or "",
                process_id=version.bpmn_process_no,
                validation_variables=validation_variables_for(definition.business_type_code),
            )
            validate_assignee_config(version.bpmn_xml or "", definition.business_type_code)
            definition = await repository.publish_version(
                session, version=version, definition=definition, user_id=current_user.user_id
            )
            await session.commit()
            return await repository.to_item(session, definition)

    async def validate_bpmn_xml(self, bpmn_xml: str, *, bpmn_process_no: str | None = None) -> dict:
        meta = validate_bpmn(bpmn_xml, process_id=bpmn_process_no)
        return {"bpmn_process_no": meta.bpmn_process_no, "user_tasks": _user_tasks_payload(meta)}

    async def list_assignee_options(self, business_type_code: str | None) -> dict:
        """设计器可选的审批对象：审批人类型、权限、业务负责人（按业务类型）。"""
        async with self.session_getter() as session:
            permissions = (
                await session.exec(
                    select(SysPermission.permission_key, SysPermission.permission_name, SysPermission.module_code)
                    .where(SysPermission.deleted_at.is_(None), SysPermission.is_active.is_(True))
                    .order_by(SysPermission.module_code, SysPermission.permission_key)
                )
            ).all()
        adapter = get_business_adapter(business_type_code or "")
        return {
            "assignee_types": [{"value": key, "label": label} for key, label in ASSIGNEE_TYPE_LABELS.items()],
            "permissions": [
                {"permission_key": key, "permission_name": name, "module_code": module}
                for key, name, module in permissions
            ],
            "business_owners": [
                {"value": item.key, "label": item.label} for item in (adapter.business_owners.values() if adapter else [])
            ],
        }

    async def search_assignee_users(self, *, keyword: str | None, limit: int = 50) -> list[dict]:
        async with self.session_getter() as session:
            rows = await search_selectable_users(session, keyword=keyword, org_id=None, limit=limit)
            return [{"id": str(r.id), "display_name": r.display_name} for r in rows]

    async def preview_assignees(self, *, definition_id: UUID, assignees: list[AssigneeConfig]) -> dict:
        async with self.session_getter() as session:
            definition = await repository.get_entity(session, definition_id)
            groups: list[dict] = []
            candidate_ids: list[UUID] = []
            dynamic_count = 0
            for assignee in assignees:
                dynamic = assignee.type in {"business_owner", "initiator_leader", "starter", "starter_select"}
                user_ids: list[UUID] = []
                if dynamic:
                    dynamic_count += 1
                else:
                    user_ids = await resolve_assignee_user_ids(
                        session,
                        assignee_type=assignee.type,
                        assignee_value=assignee.value,
                        org_id=definition.org_id,
                        business_type_code=definition.business_type_code,
                    )
                    user_ids = await validate_selectable_user_ids(session, user_ids=user_ids, org_id=definition.org_id)
                actionable = set(await validate_workflow_approver_user_ids(session, user_ids=user_ids))
                names = await user_display_names(session, set(user_ids))
                groups.append(
                    {
                        "type": assignee.type,
                        "value": assignee.value,
                        "dynamic": dynamic,
                        "members": [
                            {"user_id": str(uid), "name": names.get(uid, str(uid)), "actionable": uid in actionable}
                            for uid in user_ids
                        ],
                    }
                )
                candidate_ids.extend(uid for uid in user_ids if uid in actionable)
            unique_ids = list(dict.fromkeys(candidate_ids))
            names = await user_display_names(session, set(unique_ids))
            return {
                "org_id": str(definition.org_id),
                "groups": groups,
                "candidate_count": len(unique_ids),
                "candidates": [{"user_id": str(uid), "name": names.get(uid, str(uid))} for uid in unique_ids],
                "has_dynamic_assignees": dynamic_count > 0,
            }

    async def get_design_template(self, business_type_code: str) -> dict:
        factory = default_designs().get(business_type_code)
        if factory is not None:
            return factory().model_dump(mode="json")
        return FlowDesignV3(
            process_name="审批流程",
            nodes=[ApprovalNode(id="user_task_approval", name="审批人", assignee=AssigneeConfig(type="initiator_leader"))],
        ).model_dump(mode="json")

    async def get_latest_design(self, definition_id: str) -> dict | None:
        async with self.session_getter() as session:
            await repository.get_entity(session, UUID(definition_id))
            design = await repository.get_latest_design_snapshot(session, UUID(definition_id))
            return normalize_flow_design(design).model_dump(mode="json") if design else None

    async def save_design(self, body: VersionSaveDesignBody, current_user: AuthenticatedUser) -> WorkflowDefinitionVersionItem:
        async with self.session_getter() as session:
            definition = await repository.get_entity(session, body.definition_id)
            try:
                design, bpmn_process_no, bpmn_xml, _ = compile_and_validate(body.design, definition.business_type_code)
            except (BpmnValidationError, AppException):
                raise
            except Exception as exc:
                raise AppException(f"流程设计无效: {exc}", status_code=400) from exc
            validate_assignee_config(bpmn_xml, definition.business_type_code)
            row = await repository.create_version(
                session,
                definition_id=body.definition_id,
                bpmn_xml=bpmn_xml,
                bpmn_process_no=bpmn_process_no,
                user_id=current_user.user_id,
                remark=body.remark or "可视化设计保存",
                spiff_spec_snapshot=_design_snapshot(design),
            )
            await session.commit()
            return version_item(row)

    async def preview_design(self, design: dict, business_type_code: str) -> dict:
        try:
            _, bpmn_process_no, bpmn_xml, meta = compile_and_validate(design, business_type_code)
        except (BpmnValidationError, AppException):
            raise
        except Exception as exc:
            raise AppException(str(exc), status_code=400) from exc
        return {"bpmn_process_no": bpmn_process_no, "bpmn_xml": bpmn_xml, "user_tasks": _user_tasks_payload(meta)}

    async def list_condition_fields(self, business_type_code: str) -> list[dict]:
        async with self.session_getter() as session:
            await assert_valid_workflow_business_type(session, business_type_code)
        return condition_field_items(business_type_code)


service = WorkflowDefinitionService(repository=repository, session_getter=get_session_context)
