"""Redis-backed short-lived gateway credentials and per-user usage counters."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from app.integrations.redis_client import get_redis
from app.modules.llm_gateway.models import GatewayIdentity


def _token_key(token: str) -> str:
    return f"llm-gateway:credential:{hashlib.sha256(token.encode()).hexdigest()}"


async def issue_credential(identity: GatewayIdentity, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(48)
    await get_redis().setex(_token_key(token), ttl_seconds, identity.model_dump_json())
    return token


async def read_credential(token: str) -> GatewayIdentity | None:
    raw = await get_redis().get(_token_key(token))
    return GatewayIdentity.model_validate_json(raw) if raw else None


async def revoke_credential(token: str) -> None:
    await get_redis().delete(_token_key(token))


async def consume_request_quota(user_id: UUID, per_minute: int, per_day: int) -> bool:
    now = datetime.now(UTC)
    minute = int(now.timestamp()) // 60
    day = now.strftime("%Y%m%d")
    minute_key = f"llm-gateway:rate:{user_id}:{minute}"
    day_key = f"llm-gateway:day:{user_id}:{day}"
    redis = get_redis()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)
        pipe.incr(day_key)
        pipe.expire(day_key, 172800)
        results = await pipe.execute()
    return int(results[0]) <= per_minute and int(results[2]) <= per_day


async def record_usage(user_id: UUID, request_id: str, model: str, usage: dict[str, int], status_code: int) -> None:
    day = datetime.now(UTC).strftime("%Y%m%d")
    key = f"llm-gateway:usage:{user_id}:{day}"
    redis = get_redis()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, "requests", 1)
        pipe.hincrby(key, "input_tokens", max(0, usage.get("input_tokens", 0)))
        pipe.hincrby(key, "output_tokens", max(0, usage.get("output_tokens", 0)))
        pipe.expire(key, 172800)
        pipe.setex(
            f"llm-gateway:audit:{request_id}", 172800,
            json.dumps({"user_id": str(user_id), "model": model, "status_code": status_code,
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0)}, separators=(",", ":")),
        )
        await pipe.execute()
