"""登录日志：只读（登录日志只追加，不提供修改、删除）。"""

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response

from .schemas import LoginLogListQuery
from .service import service

router = APIRouter(prefix="/api/login_log", tags=["login_log"])


@router.get("/list")
async def list_items(
    params: LoginLogListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["login_log:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user))
