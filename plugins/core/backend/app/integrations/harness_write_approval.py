"""Short-lived, single-use write grants bound to an ERP user and exact request."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException

from app.core.config import get_settings
from .redis_client import get_redis

AUDIENCE = "harness-erp-write"
TTL_SECONDS = 300


def request_hash(method, path, body, contract_hash):
    data = json.dumps([method, path, body, contract_hash], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def issue_grant(user, method, path, body, contract_hash):
    now = datetime.now(UTC)
    return jwt.encode({"aud": AUDIENCE, "sub": str(user.user_id), "type": "harness-write",
                       "tenant_id": str(user.tenant_id), "auth_user_id": str(user.auth_user_id),
                       "request_hash": request_hash(method, path, body, contract_hash),
                       "jti": secrets.token_hex(24), "iat": now, "exp": now + timedelta(seconds=TTL_SECONDS)},
                      get_settings().jwt_secret, algorithm="HS256")


async def consume_grant(token, user, method, path, body, contract_hash):
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], audience=AUDIENCE,
                            options={"require": ["sub", "tenant_id", "auth_user_id", "aud", "exp", "iat", "jti", "request_hash", "type"]})
        if claims["sub"] != str(user.user_id) or claims["type"] != "harness-write" \
                or claims["tenant_id"] != str(user.tenant_id) or claims["auth_user_id"] != str(user.auth_user_id) \
                or claims["request_hash"] != request_hash(method, path, body, contract_hash):
            raise ValueError("grant mismatch")
        if not await get_redis().set("harness:write-used:" + claims["jti"], "1", nx=True, ex=TTL_SECONDS):
            raise ValueError("grant already used")
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise HTTPException(403, "写操作确认已失效，请重新确认") from error
