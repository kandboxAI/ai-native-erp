"""客户端可见的移动能力目录；来源于插件声明和已验证的当前用户。"""
import json
from pathlib import Path

from app.auth.schemas import AuthenticatedUser
from app.framework.plugin import loaded_plugin_manifests
from app.framework.plugin_manifest import PLUGIN_DIR, read_frontend_manifest


def miniapp_capabilities(user: AuthenticatedUser) -> dict:
    core = json.loads(Path(__file__).with_name("miniapp_core.json").read_text(encoding="utf-8"))
    owners = {path: "core" for path in core["pages"]}
    available = dict(owners)
    deployed = []
    for plugin in loaded_plugin_manifests():
        deployed.append(plugin.key)
        if not plugin.frontend_manifest:
            continue
        definition = read_frontend_manifest(PLUGIN_DIR / plugin.key / plugin.frontend_manifest)
        for path in definition["miniapp_pages"]:
            if path in owners:
                raise ValueError(f"小程序页面归属重复：{path}")
            owners[path] = plugin.key
            if plugin.key in user.enabled_plugin_keys:
                available[path] = plugin.key
    return {
        "protocol_version": 1,
        "deployed_plugin_keys": deployed,
        "enabled_plugin_keys": [key for key in deployed if key in user.enabled_plugin_keys],
        "permissions": sorted(set(user.permissions)),
        "page_owners": available,
    }
