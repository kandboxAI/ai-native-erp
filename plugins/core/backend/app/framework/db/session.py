from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.framework.db.registry import import_all_models
from app.framework.db.tenant import get_tenant_schema, search_path_sql
from app.framework.db.list_sorting import apply_list_sort


class TenantSession(Session):
    """每个事务开始时切换到当前租户的 schema（set local，事务结束自动恢复）。"""


@event.listens_for(TenantSession, "do_orm_execute")
def _apply_display_sort(execute_state) -> None:
    if execute_state.is_select and not execute_state.is_relationship_load:
        execute_state.statement = apply_list_sort(execute_state.statement)


@event.listens_for(TenantSession, "after_begin")
def _switch_tenant_schema(session, transaction, connection) -> None:
    schema = get_tenant_schema()
    if schema is not None:
        connection.exec_driver_sql(search_path_sql(schema))

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


async def startup_sqlmodel_database() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return

    import_all_models()
    settings = get_settings()
    _engine = create_async_engine(
        _build_async_database_url(settings.database_url),
        pool_pre_ping=True,
        pool_size=settings.sqlalchemy_pool_size,
        max_overflow=settings.sqlalchemy_max_overflow,
        pool_timeout=settings.sqlalchemy_pool_timeout_seconds,
        connect_args={
            "server_settings": {"timezone": "Asia/Shanghai", "search_path": "public"},
        },
    )
    _sessionmaker = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        sync_session_class=TenantSession,
        expire_on_commit=False,
    )


async def shutdown_sqlmodel_database() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("sqlmodel session has not been initialized")
    return _sessionmaker


@asynccontextmanager
async def get_session_context() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as session:
        yield session
