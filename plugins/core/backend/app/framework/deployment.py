"""部署组合选择。

能力包架构的第一阶段仍兼容 ``app/modules`` 内置模块。这个文件把部署组合
集中定义，路由、目录、模型注册和 bootstrap 共用同一份判断，避免出现“接口
没有了但模型/菜单还在加载”的半裁剪状态。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from app.framework.plugin_manifest import builtin_plugin_manifests, resolve_plugin_manifests

DeploymentProfile = Literal["core", "custom"]

PROFILE_ENV_NAMES: Final = ("ERP_DEPLOYMENT_PROFILE", "DEPLOYMENT_PROFILE")
VALID_PROFILES: Final = frozenset({"core", "custom"})
DEPLOYMENT_FILE: Final = Path(__file__).resolve().parents[5] / "deployment.json"
PROFILE_PLUGIN_KEYS: Final = {"core": ()}


@lru_cache(maxsize=8)
def _profile_manifests(profile: DeploymentProfile):
    return resolve_plugin_manifests(frozenset(plugin_keys_for_profile(profile)))


def plugin_keys_for_profile(profile: str) -> tuple[str, ...]:
    if profile in PROFILE_PLUGIN_KEYS:
        return PROFILE_PLUGIN_KEYS[profile]
    if profile == "custom":
        return _read_deployment_keys(DEPLOYMENT_FILE)
    raise ValueError(f"未知部署组合：{profile}")


@lru_cache(maxsize=1)
def _module_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for manifest in builtin_plugin_manifests():
        for module_name in manifest.module_names:
            previous = owners.setdefault(module_name, manifest.key)
            if previous != manifest.key:
                raise ValueError(f"模块 {module_name} 同时属于能力包 {previous} 和 {manifest.key}")
    return owners


def _read_deployment_keys(path: Path) -> tuple[str, ...]:
    """只接受已安装清单及完整依赖；空数组表示底座。"""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"缺少部署清单：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"部署清单不是有效 JSON：{path}（第 {exc.lineno} 行）") from exc
    if not isinstance(document, dict) or set(document) != {"format_version", "plugins"}:
        raise ValueError("部署清单只能包含 format_version 和 plugins")
    if type(document["format_version"]) is not int or document["format_version"] != 1:
        raise ValueError("部署清单 format_version 必须为 1")
    plugins = document["plugins"]
    if not isinstance(plugins, list) or any(not isinstance(key, str) for key in plugins):
        raise ValueError("部署清单 plugins 必须是字符串数组；空数组表示仅加载底座")
    if len(plugins) != len(set(plugins)):
        raise ValueError("部署清单 plugins 不能重复")
    selected = frozenset(plugins)
    # 先校验清单依赖，让依赖关系只由 plugin.toml 定义。
    return tuple(sorted(item.key for item in resolve_plugin_manifests(selected)))


def load_deployment_profile(path: Path = DEPLOYMENT_FILE) -> DeploymentProfile:
    return "custom" if _read_deployment_keys(path) else "core"


def selected_plugin_keys(profile: str | None = None) -> tuple[str, ...]:
    """Return the plug-in keys selected by deployment.json."""

    return plugin_keys_for_profile(get_deployment_profile(profile))


@lru_cache(maxsize=1)
def _configured_profile() -> DeploymentProfile:
    """进程启动后固定组合，编辑部署清单须重启进程。"""

    return load_deployment_profile()

# L1 目录、权限、文件、工作流和 Harness 基础模块在所有部署组合中都存在。
CORE_MODULES: Final = frozenset(
    json.loads((Path(__file__).with_name("core_manifest.json")).read_text(encoding="utf-8"))["module_names"]
)

@lru_cache(maxsize=1)
def _menu_owners() -> dict[str, str]:
    """从所有清单读取稳定菜单标识；未加载插件的历史菜单也能被识别。"""

    owners: dict[str, str] = {}
    for manifest in builtin_plugin_manifests():
        for menu_key in manifest.menu_keys:
            previous = owners.setdefault(menu_key, manifest.key)
            if previous != manifest.key:
                raise ValueError(f"菜单 {menu_key} 同时属于能力包 {previous} 和 {manifest.key}")
    return owners


@lru_cache(maxsize=1)
def _permission_module_owners() -> dict[str, str]:
    """租户自建菜单可通过所需权限的模块编码继承能力包归属。"""

    owners: dict[str, str] = {}
    for manifest in builtin_plugin_manifests():
        for module_code in manifest.module_codes:
            previous = owners.setdefault(module_code, manifest.key)
            if previous != manifest.key:
                raise ValueError(f"模块编码 {module_code} 同时属于能力包 {previous} 和 {manifest.key}")
    return owners


def get_deployment_profile(profile: str | None = None) -> DeploymentProfile:
    """默认读取部署清单；显式参数或旧命令行环境变量可临时覆盖。"""

    configured = next((os.getenv(name) for name in PROFILE_ENV_NAMES if os.getenv(name)), None)
    value = (profile or configured or _configured_profile()).strip().lower()
    if value not in VALID_PROFILES:
        choices = ", ".join(sorted(VALID_PROFILES))
        raise ValueError(f"部署组合必须是 {choices} 之一，当前为 {value!r}")
    _profile_manifests(value)
    return value  # type: ignore[return-value]


def is_module_enabled(module_name: str, profile: str | None = None) -> bool:
    """判断 ``app.modules.<module_name>`` 是否属于当前部署组合。"""

    current = get_deployment_profile(profile)
    selected = _profile_manifests(current)
    owner = _module_owners().get(module_name)
    if owner is not None:
        return owner in {item.key for item in selected}
    return module_name in CORE_MODULES


def module_plugin_owner(module_name: str) -> str | None:
    return _module_owners().get(module_name)


def is_menu_enabled(
    menu_key: str,
    profile: str | None = None,
    permission_module_code: str | None = None,
) -> bool:
    """判断菜单是否属于当前部署组合。

    这是对已有租户菜单数据的运行时保护。bootstrap 只补齐新目录，不会自动
    删除租户历史菜单。使用不可变的 menu_key，租户修改路径或权限后归属不变。
    """

    owner = menu_plugin_owner(menu_key, permission_module_code)
    return owner is None or owner in plugin_keys_for_profile(get_deployment_profile(profile))


def menu_plugin_owner(menu_key: str, permission_module_code: str | None = None) -> str | None:
    owner = _menu_owners().get(menu_key)
    if owner is None and permission_module_code:
        owner = _permission_module_owners().get(permission_module_code)
    return owner


@lru_cache(maxsize=1)
def _miniapp_menu_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for manifest in builtin_plugin_manifests():
        for menu_key in manifest.miniapp_menu_keys:
            previous = owners.setdefault(menu_key, manifest.key)
            if previous != manifest.key:
                raise ValueError(f"小程序菜单 {menu_key} 同时属于能力包 {previous} 和 {manifest.key}")
    return owners


def miniapp_menu_plugin_owner(menu_key: str) -> str | None:
    return _miniapp_menu_owners().get(menu_key)


def permission_module_plugin_owner(module_code: str) -> str | None:
    return _permission_module_owners().get(module_code)


def blocked_plugin_module_codes(enabled_plugin_keys: set[str] | list[str]) -> set[str]:
    enabled = set(enabled_plugin_keys)
    return {
        code
        for manifest in builtin_plugin_manifests()
        if manifest.key not in enabled
        for code in manifest.module_codes
    }


def effective_plugin_keys(recorded_active_keys: set[str], profile: str | None = None) -> set[str]:
    """只认可当前组合内、依赖链也已启用的能力包。"""
    selected = _profile_manifests(get_deployment_profile(profile))
    effective: set[str] = set()
    for manifest in selected:
        dependencies = {spec.split(">=", 1)[0] for spec in manifest.requires}
        if manifest.key in recorded_active_keys and dependencies <= effective:
            effective.add(manifest.key)
    return effective


def enabled_module_names(all_module_names: set[str] | frozenset[str], profile: str | None = None) -> set[str]:
    """将已发现的内置模块裁剪为当前部署组合。"""

    return {name for name in all_module_names if is_module_enabled(name, profile)}


def profile_description(profile: str | None = None) -> str:
    keys = plugin_keys_for_profile(get_deployment_profile(profile))
    return "L1 管理底座" + (" + " + ", ".join(keys) if keys else "（无业务插件）")
