from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from app.db.pagination import PageParams
from .schemas import MesOptionQuery
from .exception_schemas import ExceptionQuery, ExceptionCreate, ExceptionCommand, ExceptionAction
from .exception_service import exception_service as service

router=APIRouter()


@router.get("/exceptions")
async def page(query:ExceptionQuery=Depends(),user=Depends(require_permissions(["mes:exception:list"]))):
    return paginated_response(**await service.page(query,user))


@router.get("/exception-options/orders")
async def orders(query:MesOptionQuery=Depends(),user=Depends(require_permissions(["mes:exception:create","mes:work_order:list"]))):
    return success_response(await service.orders(query,user))


@router.get("/exception-options/orders/{identifier}")
async def source(identifier:UUID,query:MesOptionQuery=Depends(),user=Depends(require_permissions(["mes:exception:create","mes:work_order:list"]))):
    return success_response(await service.source_options(identifier,query,user))


@router.get("/exceptions/{identifier}")
async def detail(identifier:UUID,user=Depends(require_permissions(["mes:exception:list"]))):
    return success_response(await service.detail(identifier,user))


@router.get("/exceptions/{identifier}/events")
async def events(identifier:UUID,query:PageParams=Depends(),user=Depends(require_permissions(["mes:exception:list"]))):
    return paginated_response(**await service.history(identifier,query,user))


@router.get("/exceptions/{identifier}/assignees")
async def assignees(identifier:UUID,query:MesOptionQuery=Depends(),user=Depends(require_permissions(["mes:exception:list","mes:exception:manage"]))):
    return success_response(await service.assignees(identifier,query,user))


@router.post("/exceptions")
async def create(body:ExceptionCreate,user=Depends(require_permissions(["mes:exception:create","mes:exception:list","mes:work_order:list"]))):
    try: return success_response(await service.create(body,user))
    except IntegrityError as error: raise AppException("登记标识已使用或关联数据已变化，请刷新重试",409) from error


@router.post("/exceptions/{identifier}/actions/{action}")
async def command(identifier:UUID,action:ExceptionAction,body:ExceptionCommand,user=Depends(require_permissions(["mes:exception:list"]))):
    # 每个动作的权限、数据范围、责任人和状态在 Service 中再次校验。
    return success_response(await service.command(identifier,action,body,user))
