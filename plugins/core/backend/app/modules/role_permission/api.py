from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import RolePermissionBatchSync, RolePermissionCreate, RolePermissionListQuery, RolePermissionUpdate
from .service import service

router = APIRouter(prefix="/api/role_permission", tags=["role_permission"])


@router.get("/list")
async def list_items(
    params: RolePermissionListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["role_permission:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params))


@router.get("/detail/{item_id}")
async def detail_item(
    item_id: str,
    _: AuthenticatedUser = Depends(require_permissions(["role_permission:detail"])),
) -> dict[str, Any]:
    item = await service.detail(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_item(
    payload: RolePermissionCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_permission:create"])),
) -> dict[str, Any]:
    item = await service.create(payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{item_id}")
async def update_item(
    item_id: str,
    payload: RolePermissionUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_permission:update"])),
) -> dict[str, Any]:
    item = await service.update(item_id, payload.model_dump(exclude_unset=True), current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.post("/batch-sync")
async def batch_sync(
    payload: RolePermissionBatchSync,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_permission:create", "role_permission:delete"])),
) -> dict[str, Any]:
    """把角色权限一次性对齐为提交的列表（需同时具备新增与删除角色权限的权限）。"""
    return success_response(await service.batch_sync(payload, current_user))


@router.delete("/delete/{item_id}")
async def delete_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_permission:delete"])),
) -> dict[str, Any]:
    if not await service.delete(item_id, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})


@router.get("/permissions")
async def module_permissions(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    allowed = current_user.permissions or []
    return success_response({"module": "role_permission", "permissions": [p for p in allowed if p.startswith("role_permission:")]})
