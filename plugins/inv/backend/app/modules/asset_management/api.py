"""资产管理 HTTP 接口。"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_permissions, require_any_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import (
    AssetItemOptionQuery,
    AssetEventQuery,
    AssetLedgerQuery,
    AssetRegistrationConfirm,
    AssetRegistrationVoid,
    AssetRegistrationCreate,
    AssetRegisterCreate,
    AssetRegisterQuery,
    AssetRegisterTransfer,
    AssetRegisterUpdate,
    LocationAssetAdjust,
    LocationAssetCreate,
    LocationAssetQuery,
    LocationAssetTransfer,
    LocationAssetUpdate,
)
from .service import service
from .stock_service import stock_service
from .registration_service import registration_service

router = APIRouter(prefix="/api/asset", tags=["asset"])


@router.get("/registration-options")
async def registration_options(org_id: UUID | None = None,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:create", "asset_register:confirm"]))):
    return success_response(await registration_service.options(user, org_id))


@router.post("/registrations")
async def register_assets(body: AssetRegistrationCreate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:create", "asset_register:confirm"]))):
    return success_response(await registration_service.create(body, user))


@router.get("/stock-bindings")
async def stock_bindings(item_id: UUID, warehouse_id: UUID | None = None,
    keyword: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:transfer"]))):
    return paginated_response(**await stock_service.binding_options(user, item_id=item_id,
        warehouse_id=warehouse_id, page=page, page_size=page_size, keyword=keyword))


@router.get("/stock-target-options")
async def stock_target_options(org_id: UUID | None = None,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:transfer"]))):
    return success_response(await service.options(org_id, "ledger", user, permission_override="asset_register:transfer"))


@router.get("/item-options")
async def item_options(
    query: AssetItemOptionQuery = Depends(),
    user: AuthenticatedUser = Depends(require_any_permissions(["asset_register:list", "asset_register:create"])),
) -> dict[str, Any]:
    return paginated_response(**await service.item_options(query, user))


@router.get("/options")
async def options(
    org_id: UUID | None = None,
    scope: Literal["ledger"] = "ledger",
    user: AuthenticatedUser = Depends(
        require_permissions(["asset_register:list"])
    ),
) -> dict[str, Any]:
    return success_response(await service.options(org_id, scope, user))


@router.get("/summary")
async def summary(
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:list"])),
) -> dict[str, Any]:
    return success_response(await service.summary(user))


@router.get("/ledger")
async def ledger(
    query: AssetLedgerQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_ledger(query, user))


@router.get("/location-items")
async def location_items(
    query: LocationAssetQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_location_items(query, user))


@router.get("/location-items/{row_id}")
async def location_item_detail(
    row_id: UUID,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:detail"])),
) -> dict[str, Any]:
    return success_response(await service.location_item_detail(row_id, user))


@router.post("/location-items")
async def create_location_item(
    body: LocationAssetCreate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:create"])),
) -> dict[str, Any]:
    return success_response(await service.create_location_item(body, user))


@router.put("/location-items/{row_id}")
async def update_location_item(
    row_id: UUID,
    body: LocationAssetUpdate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:update"])),
) -> dict[str, Any]:
    return success_response(await service.update_location_item(row_id, body, user))


@router.post("/location-items/{row_id}/adjust")
async def adjust_location_item(
    row_id: UUID,
    body: LocationAssetAdjust,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:adjust"])),
) -> dict[str, Any]:
    return success_response(await service.adjust_location_item(row_id, body, user))


@router.post("/location-items/{row_id}/transfer")
async def transfer_location_item(
    row_id: UUID,
    body: LocationAssetTransfer,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:transfer"])),
) -> dict[str, Any]:
    return success_response(await service.transfer_location_item(row_id, body, user))


@router.get("/registers")
async def registers(
    query: AssetRegisterQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_registers(query, user))


@router.get("/registers/{register_id}")
async def register_detail(
    register_id: UUID,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:detail"])),
) -> dict[str, Any]:
    return success_response(await service.register_detail(register_id, user))


@router.post("/registers")
async def create_register(
    body: AssetRegisterCreate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:create"])),
) -> dict[str, Any]:
    return success_response(await service.create_register(body, user))


@router.put("/registers/{register_id}")
async def update_register(
    register_id: UUID,
    body: AssetRegisterUpdate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:update"])),
) -> dict[str, Any]:
    return success_response(await service.update_register(register_id, body, user))


@router.post("/registers/{register_id}/transfer")
async def transfer_register(
    register_id: UUID,
    body: AssetRegisterTransfer,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:transfer"])),
) -> dict[str, Any]:
    return success_response(await service.transfer_register(register_id, body, user))


@router.post("/{management_mode}/{asset_id}/registration/confirm")
async def confirm_registration(
    management_mode: str,
    asset_id: UUID,
    body: AssetRegistrationConfirm,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:confirm"])),
) -> dict[str, Any]:
    return success_response(await service.confirm_registration(management_mode, asset_id, body, user))


@router.post("/{management_mode}/{asset_id}/registration/void")
async def void_registration(
    management_mode: str,
    asset_id: UUID,
    body: AssetRegistrationVoid,
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:void"])),
) -> dict[str, Any]:
    return success_response(await service.void_registration(management_mode, asset_id, body, user))


@router.get("/events")
async def events(
    query: AssetEventQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_register:detail"])),
) -> dict[str, Any]:
    return paginated_response(**await service.events(query, user))
