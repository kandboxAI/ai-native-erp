"""当前租户的能力包开通与启停入口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.plugin import loaded_plugin_manifests
from app.framework.miniapp import miniapp_capabilities
from app.framework.tenant_plugins import list_tenant_plugins, set_tenant_plugin_active

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("/suites")
async def list_suites(current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    from app.framework.tenant_suites import list_tenant_suites
    return success_response(await list_tenant_suites(current_user.tenant_id))


@router.post("/suites/{suite_key}/enable")
async def enable_suite(suite_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    from app.framework.tenant_suites import change_tenant_suite
    return success_response(await change_tenant_suite(current_user.tenant_id, suite_key, "enable", auth_user_id=current_user.auth_user_id))


@router.post("/suites/{suite_key}/disable")
async def disable_suite(suite_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    from app.framework.tenant_suites import change_tenant_suite
    return success_response(await change_tenant_suite(current_user.tenant_id, suite_key, "disable", auth_user_id=current_user.auth_user_id))


@router.post("/suites/{suite_key}/upgrade")
async def upgrade_suite(suite_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    from app.framework.tenant_suites import change_tenant_suite
    return success_response(await change_tenant_suite(current_user.tenant_id, suite_key, "upgrade", auth_user_id=current_user.auth_user_id))


@router.get("")
async def list_plugins(current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    return success_response(await list_tenant_plugins(current_user.tenant_id))


@router.get("/skills")
async def list_enabled_plugin_skills(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Return skill identifiers available to this authenticated tenant."""
    response.headers["cache-control"] = "no-store"
    enabled_plugins = set(current_user.enabled_plugin_keys)
    skills_by_plugin = {
        manifest.key: list(manifest.ai_skill_keys)
        for manifest in loaded_plugin_manifests()
        if manifest.key in enabled_plugins
    }
    return success_response({"enabled_skill_keys_by_plugin": skills_by_plugin})


@router.get("/ai-capabilities")
def list_enabled_ai_capabilities(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """通用 ERP 协议能力；具体资源与页面在每次请求时独立授权。"""
    response.headers["cache-control"] = "no-store"
    return success_response({"protocol_version": 1, "capabilities": ["erp.data", "erp.navigation"]})


@router.post("/{plugin_key}/enable")
async def enable_plugin(plugin_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    result = await set_tenant_plugin_active(
        current_user.tenant_id, plugin_key, True, auth_user_id=current_user.auth_user_id
    )
    return success_response(result)


@router.post("/{plugin_key}/disable")
async def disable_plugin(plugin_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    result = await set_tenant_plugin_active(
        current_user.tenant_id, plugin_key, False, auth_user_id=current_user.auth_user_id
    )
    return success_response(result)


@router.post("/{plugin_key}/upgrade")
async def upgrade_plugin(plugin_key: str, current_user: AuthenticatedUser = Depends(require_permissions(["plugin:manage"]))) -> dict:
    result = await set_tenant_plugin_active(
        current_user.tenant_id, plugin_key, True,
        auth_user_id=current_user.auth_user_id, upgrade_only=True,
    )
    return success_response(result)


@router.get("/miniapp")
def list_miniapp_capabilities(response: Response, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    response.headers["cache-control"] = "no-store"
    return success_response(miniapp_capabilities(current_user))
