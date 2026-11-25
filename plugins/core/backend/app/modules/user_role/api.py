from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import UserRoleCreate, UserRoleListQuery
from .service import service

router = APIRouter(prefix="/api/user_role", tags=["user_role"])


@router.get("/list")
async def list_items(
    params: UserRoleListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["user_role:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user))


@router.get("/detail/{item_id}")
async def detail_item(item_id: str, current_user: AuthenticatedUser = Depends(require_permissions(["user_role:detail"]))) -> dict[str, Any]:
    item = await service.detail(item_id, current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_item(payload: UserRoleCreate, current_user: AuthenticatedUser = Depends(require_permissions(["user_role:create"]))) -> dict[str, Any]:
    return success_response((await service.create(payload, current_user)).model_dump(mode="json"))


@router.delete("/delete/{item_id}")
async def delete_item(item_id: str, current_user: AuthenticatedUser = Depends(require_permissions(["user_role:delete"]))) -> dict[str, Any]:
    if not await service.delete(item_id, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})
