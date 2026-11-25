from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access
from app.core.response import success_response
from app.modules.workflow.integration.registry import get_business_adapter
from app.modules.workflow.runtime.service import workflow_runtime_service

router = APIRouter(prefix="/api/workflow_runtime", tags=["workflow_runtime"])

DEFAULT_START_PERMISSION = "workflow_runtime:start"


def _require_start_permission(current_user: AuthenticatedUser, business_type_code: str) -> str:
    adapter = get_business_adapter(business_type_code)
    candidates = ((adapter.start_permission,) + adapter.start_permissions) if adapter else ()
    permission_key = next((key for key in candidates if key in current_user.permissions), None)
    permission_key = permission_key or (adapter.start_permission if adapter else None) or DEFAULT_START_PERMISSION
    if permission_key not in current_user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing permissions: {permission_key}")
    return permission_key


class WorkflowStartBody(BaseModel):
    business_type_code: str = Field(..., max_length=64)
    business_id: UUID
    org_id: UUID | None = None
    variables: dict[str, Any] | None = None
    starter_choices: dict[str, list[UUID]] | None = None


@router.post("/start")
async def start_workflow(
    body: WorkflowStartBody,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    permission_key = _require_start_permission(current_user, body.business_type_code)
    if body.org_id is not None:
        ensure_org_access(current_user, body.org_id, permission_key)
    instance = await workflow_runtime_service.start(
        business_type_code=body.business_type_code,
        business_id=body.business_id,
        org_id=body.org_id,
        variables=body.variables,
        starter_choices=body.starter_choices,
        current_user=current_user,
    )
    return success_response(
        {"id": str(instance.id), "status_code": instance.status_code, "bpmn_activity_no": instance.bpmn_activity_no}
    )


@router.get("/start-requirements")
async def workflow_start_requirements(
    business_type_code: str,
    org_id: UUID | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    permission_key = _require_start_permission(current_user, business_type_code)
    target_org = org_id or current_user.org_id
    if target_org is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_id is required")
    ensure_org_access(current_user, target_org, permission_key)
    return success_response(
        await workflow_runtime_service.start_requirements(business_type_code=business_type_code, org_id=target_org)
    )


@router.get("/starter-candidates")
async def workflow_starter_candidates(
    business_type_code: str,
    org_id: UUID | None = None,
    keyword: str | None = None,
    limit: int = 50,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    permission_key = _require_start_permission(current_user, business_type_code)
    if org_id is not None:
        ensure_org_access(current_user, org_id, permission_key)
    return success_response(
        await workflow_runtime_service.starter_candidates(keyword=keyword, org_id=org_id or current_user.org_id, limit=limit)
    )


@router.get("/instance/by_business")
async def instance_by_business(
    business_type_code: str,
    business_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    data = await workflow_runtime_service.get_by_business(business_type_code=business_type_code, business_id=business_id)
    if data is None:
        return success_response(None)
    instance = data["instance"]
    return success_response(
        {
            "id": str(instance.id),
            "status_code": instance.status_code,
            "bpmn_activity_no": instance.bpmn_activity_no,
            "business_type_code": instance.business_type_code,
            "business_id": str(instance.business_id),
            "pending_tasks": [
                {
                    "id": str(t.id),
                    "task_key": t.task_key,
                    "task_name": t.task_name,
                    "assignee_type_code": t.assignee_type_code,
                    "assignee_value": t.assignee_value,
                    "approval_mode_code": t.approval_mode_code,
                    "candidate_user_ids": [str(u) for u in data["candidates"].get(t.id, [])],
                    "required_count": max(len(data["candidates"].get(t.id, [])), 1) if t.approval_mode_code == "all" else 1,
                }
                for t in data["pending_tasks"]
            ],
        }
    )
