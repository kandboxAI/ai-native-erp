from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.core.runtime import online_user_registry, scheduler_registry
from app.modules.user_profile.service import service as user_service
from app.db.pagination import PageParams
from app.framework.todos import list_my_todos

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/my-todos")
async def my_todos(params: PageParams = Depends(), user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    # 每个来源自行执行权限、范围与租户插件启停检查，不要求业务用户拥有流程审批权限。
    return success_response(await list_my_todos(user, params))


class KickOnlineUserBody(BaseModel):
    auth_user_id: UUID = Field(..., description="登录账号 ID（public.auth_user.id）")


@router.get("/online-users")
async def online_users(current_user: AuthenticatedUser = Depends(require_permissions(["online_user:list"]))) -> dict:
    """在线用户：只返回本租户的用户（在本租户有用户身份的登录账号）。"""
    del current_user
    items = await online_user_registry.list_active()
    tenant_users = await user_service.map_tenant_users_by_auth_user(
        [UUID(str(item["auth_user_id"])) for item in items if item.get("auth_user_id")]
    )
    result = []
    for item in items:
        user = tenant_users.get(str(item.get("auth_user_id")))
        if user is not None:
            result.append({**item, "user_id": user["user_id"], "display_name": item.get("display_name") or user["display_name"]})
    return success_response(result)


@router.post("/online-users/kick")
async def kick_online_user(
    body: KickOnlineUserBody,
    current_user: AuthenticatedUser = Depends(require_permissions(["online_user:kick"])),
) -> dict:
    if body.auth_user_id == current_user.auth_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能强制下线自己")
    tenant_users = await user_service.map_tenant_users_by_auth_user([body.auth_user_id])
    if str(body.auth_user_id) not in tenant_users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该账号不属于本租户")
    await online_user_registry.kick_user(body.auth_user_id)
    return success_response({"kicked": True})


@router.get("/jobs")
async def scheduled_jobs(_: AuthenticatedUser = Depends(require_permissions(["scheduled_task:list"]))) -> dict:
    scheduler_registry.bootstrap_defaults()
    return success_response(scheduler_registry.list_jobs())
