from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response
from app.framework.export.attachment_headers import binary_attachment_disposition
from app.framework.export.xlsx_builder import XLSX_MEDIA_TYPE

from .schemas import RoleCreate, RoleListQuery, RoleUpdate
from .service import service

router = APIRouter(prefix="/api/role", tags=["role"])


@router.get("/list")
async def list_items(
    params: RoleListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["role:list"])),
) -> dict[str, Any]:
    result = await service.list(params)
    return paginated_response(**result)


@router.get("/permission-template")
async def download_permission_template(
    current_user: AuthenticatedUser = Depends(require_permissions(["role:list", "menu:list", "permission:list"])),
) -> Response:
    body = await service.build_permission_template(current_user, include_existing_roles=False)
    return Response(
        content=body,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": binary_attachment_disposition("角色权限导入模板.xlsx", ".xlsx"),
        },
    )


@router.get("/permission-template/export")
async def export_permission_template(
    current_user: AuthenticatedUser = Depends(require_permissions(["role:list", "menu:list", "permission:list"])),
) -> Response:
    body = await service.build_permission_template(current_user, include_existing_roles=True)
    return Response(
        content=body,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": binary_attachment_disposition("角色权限配置导出.xlsx", ".xlsx"),
        },
    )


@router.post("/permission-template/import")
async def import_permission_template(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(
        require_permissions(
            [
                "role:create",
                "role:update",
                "role_menu:create",
                "role_menu:delete",
                "role_permission:create",
                "role_permission:delete",
            ]
        )
    ),
) -> dict[str, Any]:
    content = await file.read()
    result = await service.import_permission_template(content, current_user)
    return success_response(result.model_dump(mode="json"))


@router.get("/detail/{item_id}")
async def detail_item(
    item_id: str,
    _: AuthenticatedUser = Depends(require_permissions(["role:detail"])),
) -> dict[str, Any]:
    item = await service.detail(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.get("/permission-config/{item_id}")
async def permission_config(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["role:detail", "permission:list"])),
) -> dict[str, Any]:
    """角色接口权限页面的轻量读取接口，不加载菜单和已绑定用户。"""
    item = await service.permission_config(item_id, current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_item(
    payload: RoleCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["role:create"])),
) -> dict[str, Any]:
    item = await service.create(payload.model_dump(exclude_none=True), current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{item_id}")
async def update_item(
    item_id: str,
    payload: RoleUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["role:update"])),
) -> dict[str, Any]:
    item = await service.update(item_id, payload.model_dump(exclude_unset=True), current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.delete("/delete/{item_id}")
async def delete_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["role:delete"])),
) -> dict[str, Any]:
    deleted = await service.delete(item_id, current_user)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})


@router.get("/permissions")
async def module_permissions(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    allowed = current_user.permissions or []
    return success_response(
        {
            "module": "role",
            "permissions": [item for item in allowed if item.startswith("role:")],
        }
    )
