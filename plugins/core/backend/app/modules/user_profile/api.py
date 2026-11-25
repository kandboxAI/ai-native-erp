from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import UserCreate, UserListQuery, UserResetPassword, UserStatusUpdate, UserUpdate
from .service import service
from .avatar_service import service as avatars
from .schemas import AvatarSave

router = APIRouter(prefix="/api/user_profile", tags=["user_profile"])


@router.put("/me/avatar")
async def update_my_avatar(
    payload: AvatarSave,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """只修改当前登录用户的头像，不接收目标用户、组织或授权字段。"""
    return success_response(await avatars.save(payload, current_user), message="头像已更新")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")


@router.get("/list")
async def list_items(
    params: UserListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user))


@router.get("/detail/{item_id}")
async def detail_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:detail"])),
) -> dict[str, Any]:
    item = await service.detail(item_id, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_item(
    payload: UserCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:create"])),
) -> dict[str, Any]:
    item = await service.create(payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{item_id}")
async def update_item(
    item_id: str,
    payload: UserUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:update"])),
) -> dict[str, Any]:
    item = await service.update(item_id, payload, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/reset_password/{item_id}")
async def reset_password_item(
    item_id: str,
    payload: UserResetPassword,
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:reset_password"])),
) -> dict[str, Any]:
    if not await service.reset_password(item_id, payload, current_user):
        raise _not_found()
    return success_response({"updated": True})


@router.put("/status/{item_id}")
async def update_status_item(
    item_id: str,
    payload: UserStatusUpdate,
    current_user: AuthenticatedUser = Depends(require_any_permissions(["user_profile:update", "user_profile:delete"])),
) -> dict[str, Any]:
    if not await service.update_status(item_id, is_active=payload.is_active, current_user=current_user):
        raise _not_found()
    return success_response({"updated": True, "is_active": payload.is_active})


@router.delete("/delete/{item_id}")
async def delete_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["user_profile:delete"])),
) -> dict[str, Any]:
    if not await service.delete(item_id, current_user):
        raise _not_found()
    return success_response({"deleted": True})


@router.get("/org_options")
async def org_options(
    _: AuthenticatedUser = Depends(require_any_permissions(["user_profile:create", "user_profile:update"])),
) -> dict[str, Any]:
    """新增、编辑用户时可选的组织（启用的组织）。"""
    return success_response(await service.org_options())


@router.get("/permissions")
async def module_permissions(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    allowed = current_user.permissions or []
    return success_response({"module": "user_profile", "permissions": [p for p in allowed if p.startswith("user_profile:")]})


@router.get("/position_options")
async def position_options(org_id: UUID,
    current_user: AuthenticatedUser = Depends(require_any_permissions(["user_profile:create", "user_profile:update"]))):
    permission = "user_profile:update" if "user_profile:update" in current_user.permissions else "user_profile:create"
    return success_response(await service.position_options(current_user, permission, org_id))
