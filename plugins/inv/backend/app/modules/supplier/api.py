from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status

from app.auth.dependencies import require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .schemas import SupplierBankAccountWrite, SupplierCreate, SupplierListQuery, SupplierUpdate
from .service import service

router = build_crud_router(
    module_name="supplier",
    service=service,
    create_model=SupplierCreate,
    update_model=SupplierUpdate,
    tags=["supplier"],
    list_model=SupplierListQuery,
)


@router.get("/options")
async def supplier_options(
    keyword: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    current_user: AuthenticatedUser = Depends(require_any_permissions(["supplier:list", "inventory_product:list", "inventory_inbound:list"])),
) -> dict[str, Any]:
    items = await service.options(keyword=keyword, active_only=active_only)
    return success_response({"items": [item.model_dump(mode="json") for item in items]})


# 收款账户属于商业机密：单独的权限，只返回脱敏账号
@router.get("/{supplier_id}/bank_account/list")
async def list_bank_accounts(
    supplier_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["supplier_bank_account:list"])),
) -> dict[str, Any]:
    items = await service.list_bank_accounts(supplier_id, current_user)
    return success_response({"items": [item.model_dump(mode="json") for item in items]})


@router.post("/{supplier_id}/bank_account/create")
async def create_bank_account(
    supplier_id: UUID,
    payload: SupplierBankAccountWrite,
    current_user: AuthenticatedUser = Depends(require_permissions(["supplier_bank_account:update"])),
) -> dict[str, Any]:
    item = await service.save_bank_account(supplier_id, payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/{supplier_id}/bank_account/update/{account_id}")
async def update_bank_account(
    supplier_id: UUID,
    account_id: UUID,
    payload: SupplierBankAccountWrite,
    current_user: AuthenticatedUser = Depends(require_permissions(["supplier_bank_account:update"])),
) -> dict[str, Any]:
    item = await service.save_bank_account(supplier_id, payload, current_user, account_id)
    return success_response(item.model_dump(mode="json"))


@router.delete("/{supplier_id}/bank_account/delete/{account_id}")
async def delete_bank_account(
    supplier_id: UUID,
    account_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["supplier_bank_account:update"])),
) -> dict[str, Any]:
    if not await service.delete_bank_account(supplier_id, account_id, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})
