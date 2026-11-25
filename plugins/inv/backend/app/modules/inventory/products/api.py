"""物料分类 /api/inventory_product_category、物料 /api/inventory_product（沿用原路由前缀与权限标识）。"""

from typing import Any

from fastapi import Depends

from app.auth.dependencies import require_any_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .schemas import (
    ItemCategoryCreate,
    ItemCategoryListQuery,
    ItemCategoryUpdate,
    ItemCreate,
    ItemListQuery,
    ItemOptionQuery,
    ItemUpdate,
)
from .service import category_service, item_service
from typing import Literal

category_router = build_crud_router(
    module_name="inventory_product_category",
    service=category_service,
    create_model=ItemCategoryCreate,
    update_model=ItemCategoryUpdate,
    tags=["inventory_product_category"],
    list_model=ItemCategoryListQuery,
)


@category_router.get("/options")
async def category_options(
    current_user: AuthenticatedUser = Depends(
        require_any_permissions(["inventory_product_category:list", "inventory_product:list", "inventory_item:list"])
    ),
) -> dict[str, Any]:
    return success_response({"items": await category_service.options()})


item_router = build_crud_router(
    module_name="inventory_product",
    service=item_service,
    create_model=ItemCreate,
    update_model=ItemUpdate,
    tags=["inventory_product"],
    list_model=ItemListQuery,
)

# 单据明细选物料：任一库存单据的新增权限即可
ITEM_OPTION_PERMISSIONS = [
    "inventory_product:list",
    "inventory_item:list",
    "inventory_inbound:list",
    "inventory_inbound:create",
    "inventory_inbound:update",
    "inventory_outbound:create",
    "inventory_transfer:create",
    "inventory_lend:create",
    "inventory_damage:create",
]


@item_router.get("/options")
async def item_options(
    query: ItemOptionQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_any_permissions(ITEM_OPTION_PERMISSIONS)),
) -> dict[str, Any]:
    items = await item_service.options(query, current_user)
    return success_response({"items": [item.model_dump(mode="json") for item in items]})


@item_router.get("/warehouse-options")
async def applicable_warehouse_options(action: Literal["create", "update", "list"] = "list",
    current_user: AuthenticatedUser = Depends(require_any_permissions([
        "inventory_product:list", "inventory_product:create", "inventory_product:update"]))):
    return success_response({"items": await item_service.warehouse_options(current_user, action)})


