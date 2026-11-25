from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


async def startup_redis() -> None:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
            health_check_interval=30,
            max_connections=settings.redis_max_connections,
        )
        await _redis.ping()


async def shutdown_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("redis client has not been initialized")
    return _redis
