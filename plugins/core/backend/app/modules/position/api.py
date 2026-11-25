from fastapi import APIRouter, Depends
from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router
from .schemas import PositionWrite, PositionQuery
from .service import position_service, reference_options

router = APIRouter()


@router.get("/api/position/options", tags=["岗位管理"])
async def options(user: AuthenticatedUser = Depends(require_permissions(["position:list"]))):
    return success_response(await reference_options(user, "position:list"))


router.include_router(build_crud_router(module_name="position", service=position_service, create_model=PositionWrite,
    update_model=PositionWrite, list_model=PositionQuery, tags=["岗位管理"]))

