from typing import Any

from fastapi import Depends

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .favorite_schemas import UserFavoriteSave
from .favorite_service import service as favorite_service
from .schemas import MenuCreate, MenuListQuery, MenuUpdate
from .service import service

router = build_crud_router(
    module_name="menu",
    service=service,
    create_model=MenuCreate,
    update_model=MenuUpdate,
    tags=["menu"],
    list_model=MenuListQuery,
)


@router.get("/tree")
async def tree_items(
    current_user: AuthenticatedUser = Depends(require_permissions(["menu:list"])),
) -> dict[str, Any]:
    return success_response(await service.tree(current_user))


@router.get("/favorites")
async def current_user_favorites(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """查询当前用户收藏及其有权自助选择的叶子菜单。"""

    config = await favorite_service.config(current_user)
    return success_response(config.model_dump(mode="json"))


@router.put("/favorites")
async def save_current_user_favorites(
    payload: UserFavoriteSave,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """按请求顺序完整替换当前用户收藏；空列表表示清空。"""

    config = await favorite_service.save(payload, current_user)
    return success_response(config.model_dump(mode="json"), message="收藏已更新")
