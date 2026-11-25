from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.export.attachment_headers import binary_attachment_disposition

from .import_excel import XLSX_MEDIA_TYPE
from .import_models import OrganizationImportOptions
from .import_service import PERMISSION, service

router = APIRouter(prefix="/import", tags=["organization"])


@router.get("/template")
async def download_template(
    current_user: AuthenticatedUser = Depends(require_permissions([PERMISSION])),
) -> Response:
    body = await service.build_template(current_user)
    return Response(content=body, media_type=XLSX_MEDIA_TYPE, headers={
        "Content-Disposition": binary_attachment_disposition("组织架构导入模板.xlsx", ".xlsx")
    })


@router.post("/validate")
async def validate_import(
    file: UploadFile = File(...),
    allow_update_existing: bool = Form(False),
    current_user: AuthenticatedUser = Depends(require_permissions([PERMISSION])),
) -> dict[str, Any]:
    result = await service.validate_import(
        await file.read(),
        file.filename or "organization.xlsx",
        current_user,
        OrganizationImportOptions(allow_update_existing=allow_update_existing),
    )
    return success_response(result.model_dump(mode="json"))


@router.post("")
async def import_data(
    file: UploadFile = File(...),
    allow_update_existing: bool = Form(False),
    current_user: AuthenticatedUser = Depends(require_permissions([PERMISSION])),
) -> dict[str, Any]:
    result = await service.import_data(
        await file.read(),
        file.filename or "organization.xlsx",
        current_user,
        OrganizationImportOptions(allow_update_existing=allow_update_existing),
    )
    return success_response(result.model_dump(mode="json"))
