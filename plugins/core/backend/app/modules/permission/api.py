from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import PermissionListQuery, PermissionUpdate
from .service import service

router = APIRouter(prefix="/api/permission", tags=["permission"])


@router.get("/list")
async def list_items(
    params: PermissionListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["permission:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user))


@router.get("/detail/{item_id}")
async def detail_item(
    item_id: str,
    _: AuthenticatedUser = Depends(require_permissions(["permission:detail"])),
) -> dict[str, Any]:
    item = await service.detail(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{item_id}")
async def update_item(
    item_id: str,
    payload: PermissionUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["permission:update"])),
) -> dict[str, Any]:
    item = await service.update(item_id, payload.model_dump(exclude_unset=True), current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.get("/permissions")
async def module_permissions(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    allowed = current_user.permissions or []
    return success_response({"module": "permission", "permissions": [item for item in allowed if item.startswith("permission:")]})
