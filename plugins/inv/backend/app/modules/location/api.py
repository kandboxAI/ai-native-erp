from uuid import UUID
from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user, require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from .schemas import LocationCreate, LocationUpdate, VersionBody
from .service import service

router = APIRouter(prefix="/api/location", tags=["统一位置"])


@router.get("/list")
async def list_locations(org_id: UUID | None = None, user: AuthenticatedUser = Depends(require_permissions(["md_location:list"]))):
    return success_response(await service.choices(user, org_id=org_id))


@router.get("/options")
async def options(permission_key: str = "md_location:list", org_id: UUID | None = None, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.choices(user, permission_key, org_id, selectable=True))


@router.get("/meta")
async def metadata(user: AuthenticatedUser = Depends(require_any_permissions(["md_location:list", "md_location:manage"]))):
    return success_response(await service.metadata(user))


@router.post("")
async def create(body: LocationCreate, user: AuthenticatedUser = Depends(require_permissions(["md_location:manage"]))):
    return success_response(await service.save(body, user))


@router.put("/{location_id}")
async def update(location_id: UUID, body: LocationUpdate, user: AuthenticatedUser = Depends(require_permissions(["md_location:manage"]))):
    return success_response(await service.save(body, user, location_id))


@router.delete("/{location_id}")
async def delete(location_id: UUID, body: VersionBody, user: AuthenticatedUser = Depends(require_permissions(["md_location:manage"]))):
    await service.delete(location_id, body.expected_version, user)
    return success_response(None)
