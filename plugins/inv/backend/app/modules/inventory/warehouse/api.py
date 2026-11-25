"""仓库 /api/inventory_warehouse。后勤库存不设库位接口。"""

from typing import Any
from uuid import UUID

from fastapi import Depends

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .schemas import WarehouseCreate, WarehouseListQuery, WarehouseUpdate, RequisitionScopeSave
from .service import warehouse_service
from .requisition_scope import service as requisition_scope_service
from .requisition_scope_repository import SCOPE_PERMISSION
from .access_service import service as access_service
from .access_repository import AUTHORIZE
from .schemas import WarehouseAccessSave

warehouse_router = build_crud_router(
    module_name="inventory_warehouse",
    service=warehouse_service,
    create_model=WarehouseCreate,
    update_model=WarehouseUpdate,
    tags=["inventory_warehouse"],
    list_model=WarehouseListQuery,
    enable_create=True,
    enable_update=True,
    enable_delete=True,
)


@warehouse_router.get("/options")
async def warehouse_options(
    warehouse_scope_key: str | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items = await warehouse_service.options(current_user, warehouse_scope_key)
    return success_response({"items": [item.model_dump(mode="json") for item in items]})


@warehouse_router.get("/department-options")
async def warehouse_department_options(org_id: UUID, permission_key: str,
    current_user: AuthenticatedUser = Depends(get_current_user)):
    return success_response({"items": await warehouse_service.department_options(current_user, org_id, permission_key)})


@warehouse_router.get("/custodian-options")
async def warehouse_custodian_options(org_id: UUID, permission_key: str,
    current_user: AuthenticatedUser = Depends(get_current_user)):
    return success_response({"items": await warehouse_service.custodian_options(current_user, org_id, permission_key)})


@warehouse_router.get("/create_org_options")
async def warehouse_create_org_options(
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_warehouse:create"])),
) -> dict[str, Any]:
    return success_response({"items": await warehouse_service.create_org_options(current_user)})


@warehouse_router.get("/{warehouse_id}/requisition-scope")
async def requisition_scope_detail(
    warehouse_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions([SCOPE_PERMISSION])),
) -> dict[str, Any]:
    return success_response(await requisition_scope_service.detail(warehouse_id, current_user))


@warehouse_router.put("/{warehouse_id}/requisition-scope")
async def requisition_scope_save(
    warehouse_id: UUID, payload: RequisitionScopeSave,
    current_user: AuthenticatedUser = Depends(require_permissions([SCOPE_PERMISSION])),
) -> dict[str, Any]:
    return success_response(await requisition_scope_service.save(warehouse_id, payload, current_user))


@warehouse_router.get("/{warehouse_id}/management-access")
async def management_access_detail(warehouse_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions([AUTHORIZE]))):
    return success_response(await access_service.detail(warehouse_id, current_user))


@warehouse_router.put("/{warehouse_id}/management-access")
async def management_access_save(warehouse_id: UUID, payload: WarehouseAccessSave,
    current_user: AuthenticatedUser = Depends(require_permissions([AUTHORIZE]))):
    return success_response(await access_service.save(warehouse_id, payload, current_user))
