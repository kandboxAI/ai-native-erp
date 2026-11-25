from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions, require_plugin_enabled
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from .sales_order_schemas import SalesOrderQuery, SalesOrderBody, SalesReleaseBody, SalesOrderApproval, SalesOrderCommand, SalesOrderEdit
from .sales_order_service import service

router = APIRouter(prefix="/sales-orders", dependencies=[Depends(require_plugin_enabled("mes"))])
LIST = "mes:sales_order:list"


@router.get("")
async def page(query: SalesOrderQuery = Depends(), user=Depends(require_permissions([LIST]))):
    return paginated_response(**await service.page(user, query))


@router.get("/sources")
async def sources(keyword: str = Query(default="", max_length=128), quotation_id: UUID | None = None,
        page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
        customer_id: UUID | None = None,
        user=Depends(require_permissions([LIST, "mes:sales_order:manage", "mes:quotation:list"]))):
    return paginated_response(**await service.sources(user, keyword, quotation_id, page, page_size, customer_id))


@router.get("/source-customers")
async def source_customers(keyword: str = Query(default="", max_length=128),
        user=Depends(require_permissions([LIST, "mes:sales_order:manage", "mes:quotation:list"]))):
    return success_response(await service.source_customers(user, keyword))


@router.post("")
async def create(body: SalesOrderBody, user=Depends(require_permissions([LIST, "mes:sales_order:manage", "mes:quotation:list"]))):
    try:
        return success_response(await service.create(body, user), "客户订单已确认")
    except IntegrityError as error:
        raise AppException("订单确认发生冲突，请使用原提交内容重试", 409) from error


@router.get("/{identifier}")
async def detail(identifier: UUID, user=Depends(require_permissions([LIST]))):
    return success_response(await service.detail(identifier, user))


@router.get("/{identifier}/production-defaults")
async def production_defaults(identifier: UUID,
        user=Depends(require_permissions([LIST, "mes:sales_order:release", "mes:work_order:create"]))):
    return success_response(await service.production_defaults(identifier, user))


@router.put("/{identifier}")
async def update(identifier: UUID, body: SalesOrderEdit, user=Depends(require_permissions([LIST, "mes:sales_order:manage"]))):
    return success_response(await service.update(identifier, body, user), "订单已更新")


@router.post("/{identifier}/approve")
async def approve(identifier: UUID, body: SalesOrderApproval,
        user=Depends(require_permissions([LIST, "mes:sales_order:approve"]))):
    return success_response(await service.approve(identifier, body, user), "客户订单审核通过")


@router.post("/{identifier}/release")
async def release(identifier: UUID, body: SalesReleaseBody,
        user=Depends(require_permissions([LIST, "mes:sales_order:release", "mes:work_order:create"]))):
    try:
        return success_response(await service.release(identifier, body, user), "生产工单已生成")
    except IntegrityError as error:
        raise AppException("生产安排发生冲突，未重复安排，请刷新后核对", 409) from error


@router.post("/{identifier}/cancel")
async def cancel(identifier: UUID, body: SalesOrderCommand, user=Depends(require_permissions([LIST, "mes:sales_order:manage"]))):
    return success_response(await service.cancel(identifier, body, user), "客户订单已取消")
