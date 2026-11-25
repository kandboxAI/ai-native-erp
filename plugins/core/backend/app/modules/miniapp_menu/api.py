from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .favorite_schemas import MiniappFavoriteSave
from .favorite_service import favorite_service
from .schemas import MiniappMenuCreate, MiniappMenuListQuery, MiniappMenuUpdate, MiniappPortal
from .service import service
from .banner_api import router as banner_router

router = build_crud_router(
    module_name="miniapp_menu",
    service=service,
    create_model=MiniappMenuCreate,
    update_model=MiniappMenuUpdate,
    tags=["miniapp_menu"],
    list_model=MiniappMenuListQuery,
)
router.include_router(banner_router)


@router.get("/favorites")
async def current_user_favorites(
    portal_code: MiniappPortal,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """查询当前用户在指定门户中的常用入口及可选目录。"""

    config = await favorite_service.config(current_user, portal_code)
    return success_response(config.model_dump(mode="json"))


@router.put("/favorites")
async def save_current_user_favorites(
    payload: MiniappFavoriteSave,
    portal_code: MiniappPortal,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """按请求顺序完整替换常用入口；数量不设业务上限。"""

    config = await favorite_service.save(payload, current_user, portal_code)
    return success_response(config.model_dump(mode="json"), message="常用菜单已更新")
