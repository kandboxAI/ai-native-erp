from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from ..design_models import AssigneeConfig
from ..schemas import (
    VersionPreviewDesignBody,
    VersionPublishBody,
    VersionSaveDesignBody,
    VersionUploadBody,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListQuery,
    WorkflowDefinitionUpdate,
)
from .service import service

router = APIRouter(prefix="/api/workflow_definition", tags=["workflow_definition"])


class BpmnValidateBody(BaseModel):
    bpmn_xml: str
    bpmn_process_no: str | None = None


class AssigneePreviewBody(BaseModel):
    definition_id: UUID
    assignees: list[AssigneeConfig] = Field(..., min_length=1, max_length=20)


@router.get("/list")
async def list_definitions(
    params: WorkflowDefinitionListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_definitions(params, current_user))


@router.get("/detail/{item_id}")
async def get_definition_detail(
    item_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response((await service.get_detail(str(item_id))).model_dump(mode="json"))


@router.post("/create")
async def create_definition(
    body: WorkflowDefinitionCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    item = await service.create(body.model_dump(exclude_none=True), current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{item_id}")
async def update_definition(
    item_id: UUID,
    body: WorkflowDefinitionUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:update"])),
) -> dict[str, Any]:
    item = await service.update(str(item_id), body.model_dump(exclude_unset=True), current_user)
    return success_response(item.model_dump(mode="json") if item else None)


@router.delete("/delete/{item_id}")
async def delete_definition(
    item_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:delete"])),
) -> dict[str, Any]:
    return success_response({"deleted": await service.delete(str(item_id), current_user)})


@router.post("/version/upload")
async def upload_bpmn_version(
    body: VersionUploadBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    return success_response((await service.upload_version(body, current_user)).model_dump(mode="json"))


@router.post("/version/upload-file")
async def upload_bpmn_version_file(
    definition_id: UUID = Form(...),
    bpmn_process_no: str | None = Form(default=None),
    remark: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    raw = await file.read()
    body = VersionUploadBody(
        definition_id=definition_id,
        bpmn_xml=raw.decode("utf-8-sig"),
        bpmn_process_no=bpmn_process_no,
        remark=remark,
    )
    return success_response((await service.upload_version(body, current_user)).model_dump(mode="json"))


@router.post("/version/publish/{version_id}")
async def publish_bpmn_version(
    version_id: UUID,
    body: VersionPublishBody | None = None,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:update"])),
) -> dict[str, Any]:
    data = await service.publish_version(str(version_id), current_user, body=body)
    return success_response(data.model_dump(mode="json"))


@router.post("/bpmn/validate")
async def validate_bpmn_endpoint(
    body: BpmnValidateBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    return success_response(await service.validate_bpmn_xml(body.bpmn_xml, bpmn_process_no=body.bpmn_process_no))


@router.get("/assignee/options")
async def list_assignee_options(
    business_type_code: str | None = None,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    """审批对象候选：审批人类型、权限清单、该业务类型登记的业务负责人（如班主任）。"""
    return success_response(await service.list_assignee_options(business_type_code))


@router.get("/assignee/users")
async def search_assignee_users(
    keyword: str | None = None,
    limit: int = 50,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.search_assignee_users(keyword=keyword, limit=limit))


@router.post("/assignee/preview")
async def preview_assignees(
    body: AssigneePreviewBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.preview_assignees(definition_id=body.definition_id, assignees=body.assignees))


@router.get("/business-types")
async def list_business_types(
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.list_business_types())


@router.get("/design/template")
async def get_design_template(
    business_type_code: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.get_design_template(business_type_code))


@router.get("/design/latest")
async def get_latest_design(
    definition_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.get_latest_design(str(definition_id)))


@router.post("/design/save")
async def save_flow_design(
    body: VersionSaveDesignBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    return success_response((await service.save_design(body, current_user)).model_dump(mode="json"))


@router.get("/design/condition-fields")
async def list_design_condition_fields(
    business_type_code: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:detail"])),
) -> dict[str, Any]:
    return success_response(await service.list_condition_fields(business_type_code))


@router.post("/design/preview")
async def preview_flow_design(
    body: VersionPreviewDesignBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["workflow_definition:create"])),
) -> dict[str, Any]:
    return success_response(await service.preview_design(body.design, body.business_type_code))
