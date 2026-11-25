from typing import Any

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.token import verify_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def extract_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return credentials.credentials


def decode_access_token_claims(token: str) -> dict[str, Any]:
    """校验 access token 并返回 claims（供中间件等同步场景使用）。"""
    return verify_access_token(token)
