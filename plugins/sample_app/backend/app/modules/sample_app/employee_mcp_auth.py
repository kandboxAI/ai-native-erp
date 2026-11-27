"""专用于员工 MCP 的凭证，有效期 30 天，不能用来调用管理 API 或人工确认接口。"""
import time
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException, Request
from app.auth.dependencies import get_current_user
from app.auth.service import build_authenticated_user
from app.auth.token import verify_access_token
from app.core.config import get_settings
from app.core.runtime import online_user_registry
from app.core.security import bearer_scheme, extract_token
from app.framework.db.tenant import set_tenant_schema
from .employee_mcp_service import authorize

AUDIENCE = "sample-app-employee-mcp"
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


async def normal_employee(user=Depends(get_current_user)):
    authorize(user)
    return user


def issue_token(user, parent_token):
    authorize(user)
    claims = verify_access_token(parent_token)
    if str(claims["sub"]) != str(user.auth_user_id) or str(claims["tenant_id"]) != str(user.tenant_id):
        raise HTTPException(401, "登录凭证不匹配")
    now = int(time.time())
    expires = now + TOKEN_TTL_SECONDS
    token = jwt.encode({"sub": str(user.auth_user_id), "user_id": str(user.user_id), "tenant_id": str(user.tenant_id),
                       "aud": AUDIENCE, "type": "employee-mcp", "scope": "reimbursement:self",
                       "iat": now, "exp": expires}, get_settings().jwt_secret, algorithm="HS256")
    return {"access_token": token, "token_type": "Bearer", "expires_in": expires - now, "expires_at": expires}


async def mcp_user(request: Request, credentials=Depends(bearer_scheme)):
    token = extract_token(credentials)
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], audience=AUDIENCE,
                            options={"require": ["sub", "tenant_id", "user_id", "aud", "type", "scope", "exp", "iat"]})
        if claims["type"] != "employee-mcp" or claims["scope"] != "reimbursement:self":
            raise ValueError()
        auth_id = UUID(claims["sub"])
        if await online_user_registry.is_session_revoked(auth_id):
            raise HTTPException(401, "登录会话已撤销")
        user = await build_authenticated_user(claims)
        if str(user.user_id) != claims["user_id"]:
            raise ValueError()
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "员工 MCP 凭证无效或已到期，请重新登录获取", headers={"WWW-Authenticate": "Bearer"}) from None
    authorize(user)
    set_tenant_schema(user.tenant_schema)
    request.state.current_user = user
    return user
