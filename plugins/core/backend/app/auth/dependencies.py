from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from starlette.requests import Request

from app.auth.schemas import AuthenticatedUser
from app.auth.service import build_authenticated_user
from app.auth.token import verify_access_token
from app.core.runtime import online_user_registry
from app.core.security import bearer_scheme, extract_token
from app.framework.db.tenant import set_tenant_schema


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return ""


async def get_optional_current_user(
    request: Request,
    credentials=Depends(bearer_scheme),
) -> AuthenticatedUser | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


async def get_current_user(request: Request, credentials=Depends(bearer_scheme)) -> AuthenticatedUser:
    token = extract_token(credentials)
    claims = verify_access_token(token)
    auth_user_id = UUID(str(claims["sub"]))
    if await online_user_registry.is_session_revoked(auth_user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session terminated by administrator",
        )
    user = await build_authenticated_user(claims)
    # 本请求之后的数据库访问都在该租户的 schema 中（会话每个事务开始时 set local search_path）
    set_tenant_schema(user.tenant_schema)
    request.state.current_user = user  # 供操作日志中间件读取
    await online_user_registry.touch(
        user.auth_user_id,
        str(user.email) if user.email else None,
        user.role_nos,
        display_name=(user.display_name or "").strip() or None,
        ip_address=_client_ip(request) or None,
        user_agent=request.headers.get("user-agent"),
    )
    return user


get_current_user.__harness_authenticated__ = True


def require_permissions(required_permissions: list[str]) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """要求拥有全部权限。只按权限判断：内置管理员角色被授予全部权限，不在代码中特殊处理。"""

    async def dependency(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        missing = [item for item in required_permissions if item not in current_user.permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permissions: {', '.join(missing)}",
            )
        return current_user

    dependency.__harness_permissions__ = ("all", tuple(required_permissions))
    return dependency


def require_any_permissions(
    allowed_permissions: list[str],
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """满足 allowed_permissions 中任意一项即可访问。"""

    async def dependency(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if any(item in current_user.permissions for item in allowed_permissions):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"missing any of permissions: {', '.join(allowed_permissions)}",
        )

    dependency.__harness_permissions__ = ("any", tuple(allowed_permissions))
    return dependency


def require_plugin_enabled(plugin_key: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """能力包路由的请求级守卫；启停状态每次请求从 public 重建。"""

    async def dependency(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if plugin_key not in current_user.enabled_plugin_keys:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="功能未开通")
        return current_user

    dependency.__harness_authenticated__ = True
    return dependency
