from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response

from .banner_schemas import BannerSave
from .banner_service import service

router = APIRouter()


@router.get("/home-banners")
async def home_banners(user: AuthenticatedUser = Depends(get_current_user)):
    rows = await service.list(user, public=True)
    return success_response({"items": [row.model_dump(mode="json") for row in rows]})


@router.get("/banners")
async def list_banners(user: AuthenticatedUser = Depends(require_permissions(["miniapp_menu:list"]))):
    rows = await service.list(user)
    return success_response({"items": [row.model_dump(mode="json") for row in rows]})


@router.post("/banners")
async def create_banner(payload: BannerSave, user: AuthenticatedUser = Depends(require_permissions(["miniapp_menu:create"]))):
    row = await service.save(payload, user)
    return success_response(row.model_dump(mode="json"))


@router.put("/banners/{banner_id}")
async def update_banner(banner_id: UUID, payload: BannerSave, user: AuthenticatedUser = Depends(require_permissions(["miniapp_menu:update"]))):
    row = await service.save(payload, user, banner_id=banner_id)
    return success_response(row.model_dump(mode="json"))


@router.delete("/banners/{banner_id}")
async def delete_banner(banner_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["miniapp_menu:delete"]))):
    await service.delete(banner_id, user)
    return success_response({"deleted": True})
