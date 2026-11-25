from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions
from app.core.exceptions import AppException
from app.core.response import success_response,paginated_response
from .schedule_plan_schemas import SchedulePlanCreate, SchedulePlanQuery, SchedulePlanCommand,ReadinessUpdate
from .schedule_plan_service import service

router=APIRouter(prefix="/schedule-plans",tags=["MES自动排程方案"])


@router.get("")
async def page(query:SchedulePlanQuery=Depends(),user=Depends(require_permissions(["mes:schedule:list"]))):
    return paginated_response(**await service.page(query,user))


@router.post("")
async def create(body:SchedulePlanCreate,user=Depends(require_permissions(["mes:schedule:manage"]))):
    try:return success_response(await service.create(body,user))
    except IntegrityError as error:raise AppException("方案资料冲突或已被修改，请重新读取后计算",409) from error


@router.get("/{identifier}")
async def detail(identifier:UUID,user=Depends(require_permissions(["mes:schedule:list"]))):
    return success_response(await service.detail(identifier,user))


@router.post("/{identifier}/apply")
async def apply(identifier:UUID,body:SchedulePlanCommand,user=Depends(require_permissions(["mes:schedule:manage","mes:schedule:apply"]))):
    try:return success_response(await service.apply(identifier,body,user))
    except IntegrityError as error:raise AppException("方案关联发生变化，未应用，请重新计算",409) from error


@router.post("/{identifier}/cancel")
async def cancel(identifier:UUID,body:SchedulePlanCommand,user=Depends(require_permissions(["mes:schedule:manage"]))):
    return success_response(await service.cancel(identifier,body,user))


@router.put("/{identifier}/readiness")
async def readiness(identifier:UUID,body:ReadinessUpdate,user=Depends(require_permissions(["mes:schedule:manage"]))):
    return success_response(await service.update_readiness(identifier,body,user))
