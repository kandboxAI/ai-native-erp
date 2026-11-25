from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response
from app.modules.miniapp_menu.schemas import MiniappPortal

from .schemas import RoleMiniappMenuBatchSync, RoleMiniappMenuCreate, RoleMiniappMenuListQuery
from .service import service

router = APIRouter(prefix="/api/role_miniapp_menu", tags=["role_miniapp_menu"])


@router.get("/catalog")
async def catalog(current_user: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:list"]))) -> dict[str, Any]:
    """全部启用的小程序菜单，按门户、分组组织，供角色配置页选择。"""
    return success_response(await service.catalog(current_user))


@router.get("/my")
async def current_user_menus(
    portal_code: MiniappPortal,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """当前用户在某个门户可见的小程序菜单（由角色小程序菜单配置决定）。"""
    return success_response((await service.current_user_menus(current_user, portal_code)).model_dump(mode="json"))


@router.get("/role/{role_id}")
async def role_config(role_id: UUID, current_user: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:list"]))) -> dict[str, Any]:
    return success_response((await service.role_config(role_id, current_user)).model_dump(mode="json"))


@router.get("/list")
async def list_items(
    params: RoleMiniappMenuListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params))


@router.get("/detail/{item_id}")
async def detail_item(item_id: str, _: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:detail"]))) -> dict[str, Any]:
    item = await service.detail(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_item(
    payload: RoleMiniappMenuCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:create"])),
) -> dict[str, Any]:
    return success_response((await service.create(payload, current_user)).model_dump(mode="json"))


@router.post("/batch-sync")
async def batch_sync(
    payload: RoleMiniappMenuBatchSync,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:create", "role_miniapp_menu:delete"])),
) -> dict[str, Any]:
    return success_response(await service.batch_sync(payload, current_user))


@router.delete("/delete/{item_id}")
async def delete_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["role_miniapp_menu:delete"])),
) -> dict[str, Any]:
    if not await service.delete(item_id, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})
