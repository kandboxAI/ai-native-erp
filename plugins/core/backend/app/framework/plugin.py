"""内置能力包适配层：按部署组合读取 plugin.toml 与迁移分支。"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_plugin_enabled
from app.framework.deployment import plugin_keys_for_profile, get_deployment_profile
from app.framework.plugin_manifest import PluginManifest, builtin_plugin_manifests, resolve_plugin_manifests

# 新插件分支统一依赖独立的 L1 基线。
CORE_MIGRATION_LOCATION = "alembic/versions/core"
BACKEND_DIR = Path(__file__).resolve().parents[2]


BUILTIN_PLUGIN_MANIFESTS: tuple[PluginManifest, ...] = builtin_plugin_manifests()


def loaded_plugin_manifests(profile: str | None = None) -> tuple[PluginManifest, ...]:
    """按依赖顺序返回部署组合内的能力包。"""

    current = get_deployment_profile(profile)
    return resolve_plugin_manifests(frozenset(plugin_keys_for_profile(current)), BUILTIN_PLUGIN_MANIFESTS)


def iter_plugin_routers(profile: str | None = None):
    """只导入当前组合声明的业务路由，避免框架逐项登记业务模块。"""

    seen: set[str] = set()
    for manifest in loaded_plugin_manifests(profile):
        for reference in manifest.routers:
            if reference in seen:
                raise ValueError(f"能力包重复声明路由：{reference}")
            seen.add(reference)
            import_path, attribute = reference.split(":", 1)
            router = getattr(import_module(import_path), attribute)
            if not isinstance(router, APIRouter):
                raise TypeError(f"能力包 {manifest.key} 的 {reference} 不是 APIRouter")
            guarded = APIRouter(dependencies=[Depends(require_plugin_enabled(manifest.key))])
            guarded.include_router(router, tags=[f"plugin:{manifest.key}", f"module:{import_path.split('.')[2]}"])
            yield guarded


def expand_module_selection(names: set[str], profile: str | None = None) -> set[str]:
    """将 bootstrap 的能力包 key 展开为模块目录，并带上依赖能力包。"""

    manifests = {item.key: item for item in loaded_plugin_manifests(profile)}
    unavailable = names & ({item.key for item in BUILTIN_PLUGIN_MANIFESTS} - manifests.keys())
    if unavailable:
        raise ValueError(f"当前部署组合未加载能力包：{', '.join(sorted(unavailable))}")
    result = {name for name in names if name not in manifests}
    visited: set[str] = set()

    def add_plugin(key: str) -> None:
        if key in visited:
            return
        item = manifests[key]
        for spec in item.requires:
            dependency = spec.split(">=", 1)[0]
            add_plugin(dependency)
        visited.add(key)
        result.update(item.module_names)

    for name in names:
        if name in manifests:
            add_plugin(name)
    return result


def tenant_version_locations(profile: str | None = None) -> tuple[str, ...]:
    """保留本地所有插件的历史版本树；可见历史不代表本次升级目标。

    不导入插件模型，也不要求插件仍在 deployment 或保留源码清单。
    profile 参数仅保留调用兼容性，目录发现不再依赖部署组合。
    """
    root = BACKEND_DIR / "alembic/versions/plugins"
    directories = sorted(root.iterdir()) if root.is_dir() else ()
    compatibility = BACKEND_DIR / ".local-migrations/legacy"
    if compatibility.is_dir():
        directories = (*directories, *sorted(compatibility.iterdir()))
    return (CORE_MIGRATION_LOCATION, *(path.relative_to(BACKEND_DIR).as_posix() for path in directories
                                       if path.is_dir() and not path.name.startswith((".", "__"))))


def legacy_version_tables() -> tuple[str, ...]:
    """能力包分支曾经使用的独立版本表名（如 mes_alembic_version）；只用于一次性合并到 alembic_version。"""

    # 只有 MES 曾使用独立版本表；新能力包不生成不存在的历史兼容入口。
    return ("mes_alembic_version",)
