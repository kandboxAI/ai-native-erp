from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.integrations.redis_client import get_redis

REFRESH_KEY_PREFIX = "auth:refresh:"
REFRESH_USER_SET_PREFIX = "auth:refresh_user:"

_WRITE_REFRESH_LUA = """
if ARGV[3] ~= '' and not redis.call('GET', KEYS[1]) then return 0 end
local index_ttl = math.max(tonumber(ARGV[1]), redis.call('TTL', KEYS[3]))
redis.call('SETEX', KEYS[2], ARGV[1], ARGV[2])
if ARGV[3] ~= '' then
  redis.call('DEL', KEYS[1])
  redis.call('SREM', KEYS[3], ARGV[3])
end
redis.call('SADD', KEYS[3], ARGV[4])
redis.call('EXPIRE', KEYS[3], index_ttl)
return 1
"""


@dataclass(frozen=True)
class RefreshSession:
    # public.auth_user.id; tenant users have a separate identity.
    user_id: UUID
    email: str | None
    remember_me: bool
    expires_at: int
    tenant_id: UUID


def create_access_token(auth_user_id: UUID, email: str | None, tenant_id: UUID, *,
                        session_expires_at: int | None = None) -> tuple[str, int, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.jwt_access_expire_minutes)
    expires_at = now + expires_delta
    if session_expires_at is not None:
        expires_at = min(expires_at, datetime.fromtimestamp(session_expires_at, UTC))
        if expires_at <= now:
            raise HTTPException(status_code=401, detail="登录已到期，请重新登录")
    payload: dict[str, Any] = {
        "sub": str(auth_user_id),
        "email": email,
        "tenant_id": str(tenant_id),
        "aud": settings.access_token_audience,
        "exp": expires_at,
        "iat": now,
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(expires_at.timestamp()) - int(now.timestamp()), int(expires_at.timestamp())


def verify_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.access_token_audience,
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token") from exc

    if claims.get("type") != "access" or not claims.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")
    return claims


def _refresh_payload(session: RefreshSession) -> tuple[int, str]:
    ttl_seconds = session.expires_at - int(datetime.now(UTC).timestamp())
    if ttl_seconds <= 0:
        raise HTTPException(status_code=401, detail="登录已到期，请重新登录")
    payload = json.dumps({"user_id": str(session.user_id), "email": session.email,
                          "remember_me": session.remember_me, "expires_at": session.expires_at,
                          "tenant_id": str(session.tenant_id)})
    return ttl_seconds, payload


async def issue_refresh_token(session: RefreshSession) -> str:
    redis = get_redis()
    token = secrets.token_urlsafe(48)
    ttl_seconds, payload = _refresh_payload(session)
    # 短会话不能缩短同一用户其他长期会话的撤销索引寿命。
    await redis.eval(_WRITE_REFRESH_LUA, 3, "", f"{REFRESH_KEY_PREFIX}{token}",
                     f"{REFRESH_USER_SET_PREFIX}{session.user_id}", ttl_seconds, payload, "", token)
    return token


async def verify_refresh_token(refresh_token: str) -> RefreshSession:
    redis = get_redis()
    raw = await redis.get(f"{REFRESH_KEY_PREFIX}{refresh_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    data = json.loads(raw)
    if not data.get("tenant_id"):
        raise HTTPException(status_code=401, detail="登录凭证缺少租户信息，请重新登录")
    expires_at = data.get("expires_at")
    if expires_at is None:
        # 旧版本凭证保留 Redis 中的剩余期限，首次刷新后写入固定截止时间。
        ttl = await redis.ttl(f"{REFRESH_KEY_PREFIX}{refresh_token}")
        if ttl <= 0:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        expires_at = int(datetime.now(UTC).timestamp()) + ttl
    if expires_at <= int(datetime.now(UTC).timestamp()):
        raise HTTPException(status_code=401, detail="登录已到期，请重新登录")
    return RefreshSession(UUID(str(data["user_id"])), data.get("email"),
                          bool(data.get("remember_me", True)), int(expires_at), UUID(str(data["tenant_id"])))


async def revoke_refresh_token(refresh_token: str, user_id: UUID) -> None:
    redis = get_redis()
    await redis.delete(f"{REFRESH_KEY_PREFIX}{refresh_token}")
    await redis.srem(f"{REFRESH_USER_SET_PREFIX}{user_id}", refresh_token)


async def rotate_refresh_token(old_refresh_token: str, session: RefreshSession) -> str:
    redis = get_redis()
    new_token = secrets.token_urlsafe(48)
    ttl_seconds, payload = _refresh_payload(session)
    # 新凭证落库、旧凭证消费和撤销索引更新在同一次 Redis 原子操作中完成。
    rotated = await redis.eval(_WRITE_REFRESH_LUA, 3,
                               f"{REFRESH_KEY_PREFIX}{old_refresh_token}",
                               f"{REFRESH_KEY_PREFIX}{new_token}",
                               f"{REFRESH_USER_SET_PREFIX}{session.user_id}",
                               ttl_seconds, payload, old_refresh_token, new_token)
    if not rotated:
        raise HTTPException(status_code=401, detail="登录刷新凭证已失效，请重新登录")
    return new_token


async def revoke_all_refresh_tokens(user_id: UUID) -> None:
    redis = get_redis()
    user_set_key = f"{REFRESH_USER_SET_PREFIX}{user_id}"
    tokens = await redis.smembers(user_set_key)
    if tokens:
        await redis.delete(*[f"{REFRESH_KEY_PREFIX}{token}" for token in tokens])
    await redis.delete(user_set_key)
