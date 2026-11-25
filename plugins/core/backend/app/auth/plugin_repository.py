"""public.auth_tenant_plugin 的持久化与租户级操作锁。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import AuthTenant, AuthTenantPlugin


class TenantPluginRepository:
    async def get_tenant(self, session: AsyncSession, tenant_id: UUID) -> AuthTenant | None:
        return await session.get(AuthTenant, tenant_id)

    async def get_tenant_by_schema(self, session: AsyncSession, schema: str) -> AuthTenant | None:
        return (await session.exec(select(AuthTenant).where(AuthTenant.schema_name == schema))).scalars().first()

    async def list_for_tenant(self, session: AsyncSession, tenant_id: UUID) -> list[AuthTenantPlugin]:
        statement = select(AuthTenantPlugin).where(AuthTenantPlugin.tenant_id == tenant_id)
        return list((await session.exec(statement)).scalars().all())

    async def active_keys(self, session: AsyncSession, tenant_id: UUID) -> set[str]:
        statement = select(AuthTenantPlugin).where(
            AuthTenantPlugin.tenant_id == tenant_id,
            AuthTenantPlugin.provisioning_status_code == "ready",
            AuthTenantPlugin.is_active.is_(True),
        )
        from app.framework.plugin import loaded_plugin_manifests
        from app.framework.plugin_manifest import recorded_plugin_keys
        return recorded_plugin_keys((await session.exec(statement)).scalars().all(), loaded_plugin_manifests())

    async def lock_tenant(self, session: AsyncSession, tenant_id: UUID) -> None:
        # 专用会话保持连接直到 unlock；不同进程的开通和停用也按租户串行。
        await session.exec(select(func.pg_advisory_lock(self._lock_key(tenant_id))))

    async def unlock_tenant(self, session: AsyncSession, tenant_id: UUID) -> None:
        await session.exec(select(func.pg_advisory_unlock(self._lock_key(tenant_id))))

    @staticmethod
    def _lock_key(tenant_id: UUID) -> int:
        return int.from_bytes(tenant_id.bytes[:8], byteorder="big", signed=True)


repository = TenantPluginRepository()
