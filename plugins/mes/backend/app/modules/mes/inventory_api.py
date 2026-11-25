from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions, require_any_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from app.framework.db.session import get_session_context
from app.modules.inventory import public as stock
from .inventory_repository import inventory_repository as repo
from .inventory_schemas import InventoryPostingBody, InventoryPostingQuery, InventoryPostingCommand
from .inventory_service import inventory_service as service, active
from .delivery_repository import delivery_repository
from .warehouse_policy import allows

router = APIRouter(tags=["mes-inventory"])


@router.get("/inventory-postings")
async def postings(query: InventoryPostingQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:list"]))):
    return paginated_response(**await service.page(query, user))


@router.post("/inventory-postings")
async def create_posting(body: InventoryPostingBody, user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    try: return success_response(await service.create(body, user))
    except IntegrityError as error: raise AppException("库存申请已存在或来源关系已变化，请刷新后重试", 409) from error


@router.post("/inventory-postings/{posting_id}/{action}")
async def posting_action(posting_id: UUID, action: str, body: InventoryPostingCommand, user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    return success_response(await service.action(posting_id, action, body.reason, user))


@router.get("/inventory-options/orders")
async def order_options(query: InventoryPostingQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    async with get_session_context() as session:
        rows, total = await repo.order_options(session, query, user)
        return paginated_response(items=[dict(id=row.id, label=f"{row.work_order_no} · {row.product_item_name_snapshot}") for row in rows], total=total, page=query.page, page_size=query.page_size)


@router.get("/inventory-options/warehouses")
async def warehouse_options(direction: str = "in", purpose: str = "issue", user: AuthenticatedUser = Depends(require_any_permissions(["mes:inventory:manage", "mes:shipment:manage"]))):
    if direction not in {"in", "out"}: raise AppException("仓库方向不正确", 422)
    if purpose not in {"issue", "return", "receipt", "shipment"}: raise AppException("仓库用途不正确", 422)
    async with get_session_context() as session:
        rows = await stock.list_stock_warehouses(session, user, f"inventory_{'inbound' if direction == 'in' else 'outbound'}:create", scope_key="mes")
        return success_response([row for row in rows if allows(row, purpose)])


@router.get("/inventory-options/items")
async def item_options(keyword: str = "", user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    async with get_session_context() as session:
        return success_response(await stock.list_active_item_options(session, keyword))


@router.get("/inventory-options/items/{item_id}/lots")
async def lot_options(item_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    async with get_session_context() as session:
        return success_response(await stock.list_item_lots(session, item_id))


@router.get("/inventory-options/orders/{order_id}")
async def order_inventory_options(order_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:inventory:manage"]))):
    async with get_session_context() as session:
        order = await repo.order(session, order_id, user)
        if order is None: raise AppException("工单不存在或无权操作", 404)
        snapshot = await service.snapshot(session, order.id)
        issues = []
        for row, state in snapshot:
            if row.posting_type_code != "issue" or not active(state, confirmed=True): continue
            lots = await stock.get_stock_order_lots(session, row.stock_order_id)
            by_lot = {}
            for lot in lots:
                key = lot["lot_id"]
                by_lot[key] = by_lot.get(key, 0) + lot["quantity"]
            for lot_id, quantity in by_lot.items():
                returned = sum((entry.quantity for entry, status in snapshot if entry.source_posting_id == row.id and entry.lot_id == lot_id and active(status)), 0)
                if quantity > returned:
                    issues.append(dict(id=row.id, order_no=state["order_no"], item_id=row.item_id, item_name=row.item_name_snapshot, operation_id=row.operation_id,
                        warehouse_id=row.warehouse_id, lot_id=lot_id, lot_no=next((entry["lot_no"] for entry in lots if entry["lot_id"] == lot_id), None), available_quantity=str(quantity-returned), unit_code=row.unit_code))
        capacity = await service.produced(session, order) - await delivery_repository.direct_shipped_quantity(session, order.id) - await service.receipt_reserved(session, order.id)
        operations = await repo.operations(session, order.id)
        return success_response(dict(org_id=order.org_id, product_item_id=order.product_item_id, product_item_name=order.product_item_name_snapshot,
            receipt_available_quantity=str(max(0, capacity)), operations=[dict(id=row.id, label=row.operation_name_snapshot) for row in operations], issues=issues))
