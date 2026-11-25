"""租户目录查询（public.auth_tenant）：后台任务、开通脚本按租户循环时使用。"""

from __future__ import annotations

from sqlalchemy import select

from app.auth.models import AuthTenant
from app.framework.db.session import get_session_context


class TenantDirectoryNotInitializedError(RuntimeError):
    """The connection works, but public migrations have not created the directory."""


async def ensure_tenant_directory_initialized() -> None:
    """Read only catalog metadata before starting tenant-scoped jobs."""
    from app.db.connection import get_pool

    exists = await get_pool().fetchval(
        "SELECT to_regclass($1) IS NOT NULL", AuthTenant.__table__.fullname
    )
    if not exists:
        raise TenantDirectoryNotInitializedError(
            "数据库租户目录未初始化：缺少 public.auth_tenant。"
            "请核对 DATABASE_URL；新库请先按 docs/business-plugin-integration.md "
            "执行底座初始化，再启动后端。已有库请先核对连接与迁移状态。"
        )


async def list_tenants(*, active_only: bool = True) -> list[AuthTenant]:
    async with get_session_context() as session:
        statement = select(AuthTenant).order_by(AuthTenant.created_at)
        if active_only:
            statement = statement.where(AuthTenant.is_active.is_(True))
        return list((await session.exec(statement)).scalars().all())


async def list_active_tenant_schemas() -> list[str]:
    return [tenant.schema_name for tenant in await list_tenants()]
