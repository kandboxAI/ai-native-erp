"""库存单据类型 /api/inventory_stock_order_type 与统一库存单据 /api/inventory_stock_order。

入库、出库、调拨、借出归还、报损页面都使用同一组单据接口，按 form（单据类型的表单）或 order_type_id 过滤；
接口内按类型对应的权限（inventory_inbound:* 等）校验。
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user, require_any_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response
from app.framework.crud.router import build_crud_router
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import type_repository
from .schemas import (
    OrderBatchCreate,
    OrderCreate,
    OrderLineListQuery,
    OrderListQuery,
    OrderReject,
    OrderTypeCreate,
    OrderTypeListQuery,
    OrderTypeOptionQuery,
    OrderTypeUpdate,
    OrderUpdate,
    OrderVoid,
    ReturnCreate,
)
from .service import service

ANY_ORDER_PERMISSIONS = [
    f"{resource}:{action}"
    for resource in ("inventory_inbound", "inventory_outbound", "inventory_transfer", "inventory_lend", "inventory_damage", "inventory_stocktake")
    for action in ("list", "create")
]

type_service = CrudService(repository=type_repository, session_getter=get_session_context)
type_router = build_crud_router(
    module_name="inventory_stock_order_type",
    service=type_service,
    create_model=OrderTypeCreate,
    update_model=OrderTypeUpdate,
    tags=["inventory_stock_order_type"],
    list_model=OrderTypeListQuery,
    enable_create=False,
    enable_update=False,
    enable_delete=False,
)


@type_router.get("/options")
async def order_type_options(
    query: OrderTypeOptionQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_any_permissions(ANY_ORDER_PERMISSIONS)),
) -> dict[str, Any]:
    """页面下拉用：按表单或方向列出启用的单据类型（前端不再写死类型选项）。"""
    items = await service.type_options(query, current_user)

    return success_response({"items": [item.model_dump(mode="json") for item in items]})


router = APIRouter(prefix="/api/inventory_stock_order", tags=["inventory_stock_order"])


@router.get("/list")
async def list_orders(
    query: OrderListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return paginated_response(**await service.list_orders(query, current_user))


@router.get("/line/list")
async def list_order_lines(
    query: OrderLineListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """按明细行展开的单据列表（调拨、借用、报损页面）。"""
    return paginated_response(**await service.list_lines(query, current_user))


@router.get("/personnel-options")
async def personnel_options(
    org_id: UUID | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(require_any_permissions(ANY_ORDER_PERMISSIONS)),
) -> dict[str, Any]:
    """领用部门、领用人 / 借用人下拉。"""
    return success_response(await service.personnel_options(org_id))


@router.get("/detail/{order_id}")
async def order_detail(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.detail(order_id, current_user))


@router.post("/create")
async def create_order(payload: OrderCreate, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.create(payload, current_user))


@router.post("/batch_create")
async def batch_create_orders(payload: OrderBatchCreate, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.batch_create(payload, current_user))


@router.put("/update/{order_id}")
async def update_order(order_id: UUID, payload: OrderUpdate, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.update(order_id, payload, current_user))


@router.delete("/delete/{order_id}")
async def delete_order(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    if not await service.delete(order_id, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response({"deleted": True})


@router.post("/submit/{order_id}")
async def submit_order(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.submit(order_id, current_user))


@router.post("/approve/{order_id}")
async def approve_order(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.approve(order_id, current_user))


@router.post("/reject/{order_id}")
async def reject_order(
    order_id: UUID, payload: OrderReject | None = None, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    return success_response(await service.reject(order_id, payload.reason if payload else None, current_user))


@router.post("/confirm/{order_id}")
async def confirm_order(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    """确认 = 记账：生成库存流水并更新余额；余额不足返回 409。"""
    return success_response(await service.confirm(order_id, current_user))


@router.get("/confirm-preview/{order_id}")
async def confirm_preview(order_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    """入库确认前的超上限预警。"""
    return success_response((await service.preview_inbound_warnings(order_id, current_user)).model_dump(mode="json"))


@router.post("/void/{order_id}")
async def void_order(
    order_id: UUID, payload: OrderVoid | None = None, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    return success_response(await service.void(order_id, payload.void_reason if payload else None, current_user))


@router.post("/reverse/{order_id}")
async def reverse_order(
    order_id: UUID, payload: OrderVoid | None = None, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """冲销已确认的单据：新建冲销单并反向记账。"""
    return success_response(await service.reverse(order_id, payload.void_reason if payload else None, current_user))


@router.post("/return/{lend_order_id}")
async def return_lend_order(
    lend_order_id: UUID, payload: ReturnCreate | None = None, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """按借出单生成并确认归还单（逐行引用借出行）；不传明细时归还全部未归还数量。"""
    return success_response(await service.create_return(lend_order_id, payload or ReturnCreate(), current_user))
