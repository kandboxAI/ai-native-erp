"""当前请求的租户 schema（每个租户一个 schema：t_<租户编号>）。

- 认证依赖解析出当前租户后调用 set_tenant_schema；后台任务、种子脚本用 use_tenant_schema。
- SQLModel 会话在每个事务开始时执行 ``set local search_path = <租户 schema>, public``（见 session.py），
  事务结束即恢复，连接池中的连接不会带着上一个租户的设置。
- 没有设置租户时，连接的 search_path 只有 public：访问业务表会直接报错，而不是读到其他租户的数据。
- 直接使用 asyncpg 连接池的代码必须通过 tenant_connection() 获取连接。
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token

TENANT_SCHEMA_PATTERN = re.compile(r"t_[a-z][a-z0-9_]{0,29}")

_current_tenant_schema: ContextVar[str | None] = ContextVar("current_tenant_schema", default=None)


def validate_tenant_schema(schema: str) -> str:
    if not TENANT_SCHEMA_PATTERN.fullmatch(schema or ""):
        raise ValueError(f"invalid tenant schema: {schema!r}")
    return schema


def set_tenant_schema(schema: str | None) -> Token:
    return _current_tenant_schema.set(validate_tenant_schema(schema) if schema else None)


def reset_tenant_schema(token: Token) -> None:
    _current_tenant_schema.reset(token)


def get_tenant_schema() -> str | None:
    return _current_tenant_schema.get()


def require_tenant_schema() -> str:
    schema = get_tenant_schema()
    if schema is None:
        raise RuntimeError("tenant schema is not set for the current context")
    return schema


def search_path_sql(schema: str) -> str:
    # schema 已按白名单格式校验，可以安全拼接为标识符
    return f"set local search_path to {validate_tenant_schema(schema)}, public"


@contextmanager
def use_tenant_schema(schema: str) -> Iterator[None]:
    token = set_tenant_schema(schema)
    try:
        yield
    finally:
        reset_tenant_schema(token)


@asynccontextmanager
async def tenant_connection() -> AsyncIterator:
    """asyncpg 连接：在事务内切换到当前租户 schema。"""
    from app.db.connection import get_pool

    schema = require_tenant_schema()
    async with get_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(search_path_sql(schema))
            yield connection
