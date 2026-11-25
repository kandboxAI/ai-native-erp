"""操作日志：只读（只追加，不提供新增、修改、删除接口；由操作日志中间件写入）。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import OperationLogListQuery
from .service import service

router = APIRouter(prefix="/api/operation_log", tags=["operation_log"])


@router.get("/options")
async def audit_options(current_user: AuthenticatedUser = Depends(require_permissions(["operation_log:list"]))):
    from .policy import audit_target_options
    return success_response({"targets": audit_target_options()})


@router.get("/list")
async def list_items(
    params: OperationLogListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["operation_log:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user))


@router.get("/detail/{item_id}")
async def detail_item(
    item_id: str,
    current_user: AuthenticatedUser = Depends(require_permissions(["operation_log:detail"])),
) -> dict[str, Any]:
    item = await service.detail(item_id, current_user)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    return success_response(item.model_dump(mode="json"))
