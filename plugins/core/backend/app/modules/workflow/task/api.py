from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.workflow.task.schemas import (
    WorkflowCcListQuery,
    WorkflowCommentBody,
    WorkflowResubmitBody,
    WorkflowSupervisionListQuery,
    WorkflowTaskCompleteBody,
    WorkflowTaskListQuery,
)
from app.modules.workflow.task.service import SUPERVISE_PERMISSION, workflow_task_service

router = APIRouter(prefix="/api/workflow_task", tags=["workflow_task"])


@router.get("/business-types")
async def task_business_types(
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return success_response(await workflow_task_service.business_types())


@router.get("/list")
async def list_workflow_tasks(
    params: WorkflowTaskListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return paginated_response(**await workflow_task_service.list_tasks(params, current_user))


@router.get("/pending_for_business")
async def pending_task_for_business(
    business_type_code: str,
    business_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return success_response(
        await workflow_task_service.pending_for_business(
            business_type_code=business_type_code, business_id=business_id, current_user=current_user
        )
    )


@router.get("/cc/list")
async def list_workflow_cc_records(
    params: WorkflowCcListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return paginated_response(**await workflow_task_service.list_cc_records(params, current_user))


@router.post("/cc/read/{cc_id}")
async def mark_workflow_cc_read(
    cc_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return success_response(await workflow_task_service.mark_cc_read(cc_id, current_user))


@router.get("/cc/detail/{cc_id}")
async def workflow_cc_detail(
    cc_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:list"])),
) -> dict[str, Any]:
    return success_response(await workflow_task_service.cc_detail(cc_id, current_user))


@router.get("/supervision/list")
async def list_workflow_supervision_records(
    params: WorkflowSupervisionListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions([SUPERVISE_PERMISSION])),
) -> dict[str, Any]:
    return paginated_response(**await workflow_task_service.list_supervision_records(params, current_user))


@router.get("/supervision/detail/{instance_id}")
async def workflow_supervision_detail(
    instance_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions([SUPERVISE_PERMISSION])),
) -> dict[str, Any]:
    return success_response(await workflow_task_service.supervision_detail(instance_id, current_user))


@router.get("/timeline")
async def workflow_timeline(
    business_type_code: str,
    business_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = await workflow_task_service.timeline_for_business(business_type_code, business_id, current_user)
    return success_response(data.model_dump(mode="json"))


@router.post("/business/{business_type_code}/{business_id}/comments")
async def add_workflow_comment(
    business_type_code: str,
    business_id: UUID,
    body: WorkflowCommentBody,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = await workflow_task_service.add_comment(business_type_code, business_id, body.comment, current_user)
    return success_response(data.model_dump(mode="json"))


@router.post("/business/{business_type_code}/{business_id}/resubmit")
async def resubmit_workflow(
    business_type_code: str,
    business_id: UUID,
    body: WorkflowResubmitBody,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = await workflow_task_service.resubmit(
        business_type_code, business_id, body.comment, current_user, selected_starter_choices=body.starter_choices
    )
    return success_response(data.model_dump(mode="json"))


@router.get("/detail/{task_id}")
async def workflow_task_detail(
    task_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:detail"])),
) -> dict[str, Any]:
    return success_response(await workflow_task_service.detail(task_id, current_user))


@router.post("/complete/{task_id}")
async def complete_workflow_task(
    task_id: UUID,
    body: WorkflowTaskCompleteBody | None = None,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:complete"])),
) -> dict[str, Any]:
    comment = body.comment.strip() if body and body.comment else None
    return success_response(await workflow_task_service.complete(task_id, comment, current_user))


@router.post("/reject/{task_id}")
async def reject_workflow_task(
    task_id: UUID,
    body: WorkflowTaskCompleteBody | None = None,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_task:complete"])),
) -> dict[str, Any]:
    comment = body.comment.strip() if body and body.comment else None
    if not comment:
        raise AppException("请填写驳回原因", status_code=400)
    return success_response(await workflow_task_service.reject(task_id, comment, current_user))
