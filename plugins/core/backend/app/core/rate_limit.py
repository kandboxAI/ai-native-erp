from __future__ import annotations

import hashlib

from fastapi import status

from app.core.exceptions import AppException
from app.integrations.redis_client import get_redis


def _safe_part(value: str) -> str:
    normalized = (value or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


async def enforce_fixed_window_rate_limit(
    *,
    namespace: str,
    key_parts: list[str],
    limit: int,
    window_seconds: int,
    message: str = "请求过于频繁，请稍后再试",
) -> None:
    redis = get_redis()
    key = f"rate:{namespace}:{':'.join(_safe_part(part) for part in key_parts)}"
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    if int(current) > limit:
        raise AppException(message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
