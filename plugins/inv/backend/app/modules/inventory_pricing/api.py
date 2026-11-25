from uuid import UUID
from typing import Literal
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends
from app.auth.dependencies import require_permissions
from app.core.response import paginated_response, success_response
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.organization.public import list_writable_org_options
from .schemas import PriceBody, PriceQuery
from .repository import price_repository as repo
from .service import price_service


router = APIRouter(prefix="/api/inventory_supplier_price", tags=["inventory-supplier-price"])


@router.get("")
async def page(query: PriceQuery = Depends(), user=Depends(require_permissions(["inventory_supplier_price:list"]))):
    async with get_session_context() as session:
        rows, total = await repo.page(session, query, user)
        return paginated_response(items=rows, total=total, page=query.page, page_size=query.page_size)


@router.get("/organizations")
async def organizations(keyword: str = "", user=Depends(require_permissions(["inventory_supplier_price:manage"]))):
    async with get_session_context() as session:
        return success_response(await list_writable_org_options(session, user, "inventory_supplier_price:manage", keyword))


@router.post("")
async def create(body: PriceBody, user=Depends(require_permissions(["inventory_supplier_price:manage"]))):
    return await save(body, user)


@router.get("/options/{kind}")
async def options(kind: Literal["items", "suppliers"], keyword: str = "", user=Depends(require_permissions(["inventory_supplier_price:manage"]))):
    async with get_session_context() as session:
        return success_response(await repo.options(session, kind, keyword))


@router.put("/{identifier}")
async def update(identifier: UUID, body: PriceBody, user=Depends(require_permissions(["inventory_supplier_price:manage"]))):
    return await save(body, user, identifier)


async def save(body, user, identifier=None):
    try: return success_response(await price_service.save(body, user, identifier))
    except IntegrityError as error: raise AppException("采购价关联已变化，请刷新后重试", 409) from error
