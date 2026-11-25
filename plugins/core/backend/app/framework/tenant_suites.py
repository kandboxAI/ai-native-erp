"""Tenant suite orchestration over existing plugin records and a single tenant lock."""
from __future__ import annotations

from uuid import UUID

from app.core.exceptions import AppException
from app.framework import tenant_plugins as plugins
from app.framework.plugin_suite import ROOT, deployed_suites


def _suites():
    return {suite.key: (suite, manifests) for suite, manifests in deployed_suites()}


def _display(suite, manifests, states):
    components = [states[item.key] for item in manifests]
    ready = all(row["provisioning_status_code"] == "ready" and row["installed_version"] == row["version"] for row in components)
    active = all(row["is_active"] for row in components)
    return {"suite_key": suite.key, "name": suite.name, "version": suite.version,
            "plugins": [item.key for item in manifests], "components": components,
            "is_active": active, "is_ready": ready,
            "upgrade_available": any(row["upgrade_available"] for row in components),
            "provisioning_status_code": "failed" if any(row["provisioning_status_code"] == "failed" for row in components)
                else "installing" if any(row["provisioning_status_code"] == "installing" for row in components)
                else "ready" if ready else "pending"}


async def list_tenant_suites(tenant_id: UUID) -> list[dict]:
    states = {row["plugin_key"]: row for row in await plugins.list_tenant_plugins(tenant_id)}
    return [_display(suite, manifests, states) for suite, manifests in _suites().values()]


def _check_migrations(manifests):
    """Offline preflight of all suite branches before the first provisioning write."""
    from app.framework.plugin_package import _migration_ready
    from app.framework.plugin_manifest import migration_locations
    from app.framework.plugin_migrations import plugin_migration_config
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(plugin_migration_config("t_suite_check"))
    for manifest in manifests:
        if manifest.migration_base != "core" or not manifest.migration_location:
            raise AppException(f"组件 {manifest.key} 缺少 core 独立迁移声明", status_code=409)
        contents = {path.relative_to(ROOT).as_posix(): path.read_bytes()
                    for location in migration_locations(manifest)
                    for path in (ROOT / "plugins/core/backend" / location).glob("*.py")}
        if not _migration_ready(contents, manifest):
            raise AppException(f"组件 {manifest.key} 尚无完整迁移，请先准备正式套件包", status_code=409)
        head = script.get_revision(f"{manifest.key}@head")
        if "core_0001" not in {revision.revision for revision in script.iterate_revisions(head.revision, "base")}:
            raise AppException(f"组件 {manifest.key} 的迁移未依赖 core", status_code=409)


async def change_tenant_suite(tenant_id: UUID, suite_key: str, action: str, *, auth_user_id: UUID) -> dict:
    if action not in {"enable", "disable", "upgrade"}:
        raise AppException("不支持的套件操作")
    definition = _suites().get(suite_key)
    if definition is None:
        raise AppException("当前部署未装载该套件", status_code=404)
    suite, manifests = definition
    completed, retained = [], []
    async with plugins._tenant_operation(tenant_id):
        states = {row["plugin_key"]: row for row in await plugins.list_tenant_plugins(tenant_id)}
        if action != "disable":
            _check_migrations(manifests)
            for item in manifests:
                installed = plugins._version_key(states[item.key]["installed_version"] or "")
                if installed is not None and installed > plugins._version_key(states[item.key]["version"]):
                    raise AppException(f"组件 {item.key} 的已安装版本高于部署版本，不支持套件降级", status_code=409)
            if action == "upgrade" and any(not states[item.key]["installed_version"] for item in manifests):
                raise AppException("套件尚未完整安装，请先启用完成开通", status_code=409)
        if action == "upgrade":
            selected = [item for item in manifests if states[item.key]["upgrade_available"]]
            # A failed upgrade retains the old version; retry through the same operation.
            if not selected:
                raise AppException("当前套件没有待升级组件", status_code=409)
        else:
            selected = list(manifests if action == "enable" else reversed(manifests))
        for item in selected:
            if action == "disable":
                # Preserve shared dependencies needed by a plugin that remains active,
                # including dependencies retained earlier in this reverse-order walk.
                needed_by = [other.key for other in plugins._loaded_manifests().values()
                             if states[other.key]["is_active"] and item.key in plugins._dependency_keys(other)]
                if needed_by:
                    retained.append({"plugin_key": item.key, "required_by": sorted(needed_by)})
                    continue
            try:
                result = await plugins._set_tenant_plugin_active_locked(
                    tenant_id, item.key, action != "disable", auth_user_id=auth_user_id,
                    upgrade_only=action == "upgrade",
                )
            except AppException as exc:
                # Component migrations commit separately. Report partial progress;
                # never pretend that already applied DDL was rolled back.
                raise AppException(
                    f"{suite.name}操作未完成；失败组件：{item.key}；已完成：{', '.join(completed) or '无'}。{exc.message}；可重试。",
                    status_code=exc.status_code,
                ) from exc
            states[item.key] = result
            completed.append(item.key)
        states = {row["plugin_key"]: row for row in await plugins.list_tenant_plugins(tenant_id)}
    return {**_display(suite, manifests, states), "completed_plugins": completed, "retained_plugins": retained}
