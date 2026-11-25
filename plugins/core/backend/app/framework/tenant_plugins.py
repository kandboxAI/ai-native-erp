"""按租户开通和启停已装载的能力包；public 记录是运行时的权威状态。"""

from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import status

from app.auth.models import AuthTenantPlugin
from app.auth.plugin_repository import repository
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.plugin import loaded_plugin_manifests

logger = logging.getLogger(__name__)


def _provisioning_trace(exc: Exception) -> str:
    """Log exception locations/types without SQL parameters or secret values."""
    parts = []
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(type(current).__name__)
        for frame in traceback.extract_tb(current.__traceback__):
            parts.append(f'  {frame.filename}:{frame.lineno} in {frame.name}')
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return "\n".join(parts)


@asynccontextmanager
async def _tenant_operation(tenant_id: UUID):
    async with get_session_context() as lock_session:
        await repository.lock_tenant(lock_session, tenant_id)
        try:
            yield
        finally:
            await repository.unlock_tenant(lock_session, tenant_id)


async def active_plugin_keys(tenant_id: UUID) -> set[str]:
    """每个请求从 public 读取，启停对已有登录会话即时生效。"""

    async with get_session_context() as session:
        from app.framework.deployment import effective_plugin_keys

        return effective_plugin_keys(await repository.active_keys(session, tenant_id))


async def is_plugin_enabled_for_schema(schema: str, plugin_key: str) -> bool:
    async with get_session_context() as session:
        tenant = await repository.get_tenant_by_schema(session, schema)
        if tenant is None or not tenant.is_active:
            return False
        from app.framework.deployment import effective_plugin_keys

        return plugin_key in effective_plugin_keys(await repository.active_keys(session, tenant.id))


def _loaded_manifests():
    return {item.key: item for item in loaded_plugin_manifests()}


def _dependency_keys(manifest) -> set[str]:
    return {spec.split(">=", 1)[0] for spec in manifest.requires}


def _version_key(version: str) -> tuple[int, ...] | None:
    parts = version.split(".")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(map(int, parts)) + (0,) * (3 - len(parts))


def _upgrade_available(manifest, record: AuthTenantPlugin | None) -> bool:
    installed = _version_key(record.installed_version) if record and record.installed_version else None
    deployed = _version_key(manifest.version)
    return installed is not None and deployed is not None and installed < deployed


def _display(manifest, record: AuthTenantPlugin | None) -> dict:
    merged_pending = bool(getattr(manifest, "replaces", ()) and record and record.installed_version != manifest.version)
    return {
        "plugin_key": manifest.key,
        "name": manifest.name,
        "version": manifest.version,
        "requires": list(manifest.requires),
        "installed_version": record.installed_version if record else None,
        "upgrade_available": _upgrade_available(manifest, record),
        "provisioning_status_code": record.provisioning_status_code if record else "pending",
        "is_active": bool(record and record.provisioning_status_code == "ready" and record.is_active and not merged_pending),
        "enabled_at": record.enabled_at.isoformat() if record and record.enabled_at else None,
        "last_error_type": record.last_error_type if record else None,
    }


async def list_tenant_plugins(tenant_id: UUID) -> list[dict]:
    manifests = loaded_plugin_manifests()
    async with get_session_context() as session:
        records = {row.plugin_key: row for row in await repository.list_for_tenant(session, tenant_id)}
    return [_display(manifest, records.get(manifest.key)) for manifest in manifests]


async def mark_bootstrap_ready(tenant_id: UUID, modules: set[str] | None = None) -> None:
    """迁移、目录与 tenant_setup 全部成功后补录状态；重复运行不重新启用已停用项。"""

    manifests = [
        item for item in loaded_plugin_manifests()
        if modules is None or set(item.module_names) <= modules
    ]
    async with _tenant_operation(tenant_id):
        async with get_session_context() as session:
            records = {row.plugin_key: row for row in await repository.list_for_tenant(session, tenant_id)}
            for manifest in manifests:
                row = records.get(manifest.key)
                if row is None:
                    row = AuthTenantPlugin(tenant_id=tenant_id, plugin_key=manifest.key, is_active=True)
                    session.add(row)
                elif row.provisioning_status_code != "ready":
                    # 显式开通失败的记录只由重试流程修复；bootstrap 不能误开放。
                    continue
                row.installed_version = manifest.version
                row.provisioning_status_code = "ready"
                if row.is_active and row.enabled_at is None:
                    row.enabled_at = utc_now()
                row.updated_at = utc_now()
            await session.commit()


async def set_tenant_plugin_active(
    tenant_id: UUID, plugin_key: str, is_active: bool, *, auth_user_id: UUID,
    upgrade_only: bool = False,
) -> dict:
    async with _tenant_operation(tenant_id):
        return await _set_tenant_plugin_active_locked(
            tenant_id, plugin_key, is_active, auth_user_id=auth_user_id, upgrade_only=upgrade_only,
        )


async def _set_tenant_plugin_active_locked(
    tenant_id: UUID,
    plugin_key: str,
    is_active: bool,
    *,
    auth_user_id: UUID,
    upgrade_only: bool = False,
) -> dict:
    """同租户串行操作；升级保留启停意图，成功后才登记部署版本。"""

    manifests = _loaded_manifests()
    manifest = manifests.get(plugin_key)
    if manifest is None:
        raise AppException("当前部署未装载该能力包", status_code=status.HTTP_404_NOT_FOUND)

    async with get_session_context() as session:
        tenant = await repository.get_tenant(session, tenant_id)
        if tenant is None or not tenant.is_active:
            raise AppException("租户不存在或已停用", status_code=status.HTTP_404_NOT_FOUND)
        records = {row.plugin_key: row for row in await repository.list_for_tenant(session, tenant_id)}
        recorded_active = {
            key for key, row in records.items()
            if row.provisioning_status_code == "ready" and row.is_active
        }
        from app.framework.deployment import effective_plugin_keys

        active = effective_plugin_keys(recorded_active)
        row = records.get(plugin_key)
        if upgrade_only:
            if row is None or not row.installed_version:
                raise AppException("该能力包尚未安装，请先启用完成开通", status_code=status.HTTP_409_CONFLICT)
            if not _upgrade_available(manifest, row):
                raise AppException("当前部署没有可升级的版本", status_code=status.HTTP_409_CONFLICT)
        activate_after_setup = bool(row.is_active) if upgrade_only else True
        if not is_active:
            dependents = [
                item.key for item in manifests.values()
                if item.key in active and plugin_key in _dependency_keys(item)
            ]
            if dependents:
                raise AppException(
                    f"请先停用依赖该能力包的模块：{', '.join(sorted(dependents))}",
                    status_code=status.HTTP_409_CONFLICT,
                )
            if row is not None and row.is_active:
                row.is_active = False
                row.updated_by = auth_user_id
                row.updated_at = utc_now()
                await session.commit()
            return _display(manifest, row)

        if upgrade_only and not activate_after_setup:
            # An inactive component can be upgraded while its dependencies stay
            # inactive, provided their schema/configuration is already current.
            active |= {
                key for key, dependency in records.items()
                if key in _dependency_keys(manifest) and key in manifests and dependency.provisioning_status_code == "ready"
                and _version_key(dependency.installed_version or "") is not None
                and _version_key(dependency.installed_version) >= _version_key(manifests[key].version)
            }
        missing = _dependency_keys(manifest) - active
        if missing:
            raise AppException(
                f"请先启用依赖能力包：{', '.join(sorted(missing))}",
                status_code=status.HTTP_409_CONFLICT,
            )
        if row is not None and row.provisioning_status_code == "ready" and row.installed_version == manifest.version:
            if not row.is_active:
                row.is_active = True
                row.enabled_at = utc_now()
                row.updated_by = auth_user_id
                row.updated_at = utc_now()
                await session.commit()
            return _display(manifest, row)

        if row is None:
            row = AuthTenantPlugin(tenant_id=tenant_id, plugin_key=plugin_key, created_by=auth_user_id)
            session.add(row)
        row.provisioning_status_code = "installing"
        row.is_active = False
        row.last_error_type = None
        row.updated_by = auth_user_id
        row.updated_at = utc_now()
        await session.commit()

    stage = "数据库迁移"
    try:
        # Alembic 使用独立同步连接；锁会话仍持有租户级 advisory lock。
        from app.modules.system.tenant_template import sync_existing_tenant, upgrade_tenant_schema

        await asyncio.to_thread(upgrade_tenant_schema, tenant.schema_name, {plugin_key})
        stage = "租户初始化"
        context = await sync_existing_tenant(
            tenant,
            upgrade_schema=False,
            modules=set(manifest.module_names),
            mark_plugins_ready=False,
        )
        if context is None:
            raise RuntimeError("租户缺少根组织或管理员，能力包开通未完成")
    except Exception as exc:
        logger.error(
            "tenant plugin provisioning failed: tenant_id=%s plugin=%s stage=%s error_type=%s\n%s",
            tenant_id, plugin_key, stage, type(exc).__name__, _provisioning_trace(exc),
        )
        async with get_session_context() as session:
            record = next(
                row for row in await repository.list_for_tenant(session, tenant_id)
                if row.plugin_key == plugin_key
            )
            record.provisioning_status_code = "failed"
            record.is_active = False
            record.last_error_type = type(exc).__name__[:64]
            record.updated_at = utc_now()
            await session.commit()
        action = "升级" if upgrade_only else "开通"
        from app.framework.environment_migrations import ModelMigrationRequired
        if isinstance(exc, ModelMigrationRequired):
            raise AppException(f"能力包{action}未完成：{exc}", status_code=status.HTTP_409_CONFLICT) from exc
        raise AppException(
            f"能力包{action}失败（{stage}，{type(exc).__name__}），请检查服务日志后重试",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    async with get_session_context() as session:
        record = next(
            row for row in await repository.list_for_tenant(session, tenant_id)
            if row.plugin_key == plugin_key
        )
        record.installed_version = manifest.version
        record.provisioning_status_code = "ready"
        record.is_active = activate_after_setup
        if activate_after_setup and not upgrade_only:
            record.enabled_at = utc_now()
        record.updated_by = auth_user_id
        record.updated_at = utc_now()
        await session.commit()
        return _display(manifest, record)
