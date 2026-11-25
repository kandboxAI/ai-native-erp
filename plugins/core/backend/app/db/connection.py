import asyncpg
from asyncpg import Pool

from app.core.config import get_settings

_pool: Pool | None = None


async def startup_database() -> None:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            timeout=settings.database_pool_timeout_seconds,
            command_timeout=settings.database_pool_timeout_seconds,
            server_settings={
                "timezone": "Asia/Shanghai",
                "search_path": "public",
                "statement_timeout": str(settings.database_statement_timeout_ms),
            },
        )


async def shutdown_database() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("database pool has not been initialized")
    return _pool
