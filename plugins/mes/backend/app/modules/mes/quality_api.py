from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from .quality_schemas import QualityQuery, QualityInspectionBody
from .quality_service import quality_service

router = APIRouter()


@router.get("/quality/tasks")
async def tasks(query: QualityQuery = Depends(), user=Depends(require_permissions(["mes:quality:list"]))):
    return paginated_response(**await quality_service.tasks(query, user))


@router.get("/quality/tasks/{identifier}")
async def detail(identifier: UUID, user=Depends(require_permissions(["mes:quality:list"]))):
    return success_response(await quality_service.detail(identifier, user))


@router.post("/quality/tasks/{identifier}/inspections")
async def inspect(identifier: UUID, body: QualityInspectionBody, user=Depends(require_permissions(["mes:quality:inspect"]))):
    try:
        result = await quality_service.inspect(identifier, body, user)
    except IntegrityError as error:
        raise AppException("检验任务已更新或提交标识重复，请刷新后重试", 409) from error
    return success_response(result)
