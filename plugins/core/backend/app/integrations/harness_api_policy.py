"""Server-owned policy for model-visible ERP HTTP operations.

Business routes retain their authorized responses without privacy redaction.
Special projectors serve dynamic entity, knowledge and menu responses. Static
metadata never grants access or expands the original business data scope.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.auth.schemas import AuthenticatedUser
from app.framework.harness_http import HttpPolicy, ResourceProfile, RoutePolicy, RouteSnapshot, compile_http_registry, permitted
from app.framework.ai_catalog import ai_providers

from .harness_query_repository import RESOURCES
from .harness_schema_catalog import resource_descriptions
from .harness_value_policy import model_scalar
from app.framework.deployment import is_module_enabled

if is_module_enabled("knowledge"):
    from .knowledge.harness import KNOWLEDGE_CONTRACTS, project_base_options, project_content, project_search, project_version_status
else:
    KNOWLEDGE_CONTRACTS = {}
    project_base_options = project_content = project_search = project_version_status = None


def _menu_nodes(value: Any, depth: int = 0) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or len(value) > 200 or depth > 8:
        return None
    result: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            return None
        node = {key: model_scalar(row[key]) for key in ("menu_key", "menu_name", "path", "name") if key in row}
        if "children" in row:
            children = _menu_nodes(row["children"], depth + 1)
            if children is None:
                return None
            node["children"] = children
        result.append(node)
    return result


ReadProjector = Callable[[Any, Any], Any | None]
# Compatibility exceptions, not an exhaustive list of model-callable routes.
READ_ROUTES: dict[tuple[str, str], tuple[ReadProjector, str | tuple[str, ...] | None]] = {
    ("GET", "/api/auth/menus"): (lambda _body, data: _menu_nodes(data), None),
}
if is_module_enabled("knowledge"):
    READ_ROUTES.update({
        ("POST", "/api/knowledge/search"): (project_search, "knowledge:read"),
        ("POST", "/api/knowledge/read"): (project_content, "knowledge:read"),
        ("POST", "/api/knowledge/version-status"): (project_version_status, ("knowledge:authorization:manage", "knowledge:contribute")),
        ("POST", "/api/knowledge/base-options"): (project_base_options, ("knowledge:authorization:manage", "knowledge:contribute")),
        ("POST", "/api/knowledge/readable-base-options"): (project_base_options, "knowledge:read"),
        ("POST", "/api/knowledge/position-memory/read"): (lambda _body, data: data, "knowledge:read"),
    })

# Writes remain subject to their normal ERP route permissions and data scopes.
# The model receives only HTTP status, never a response body or error text.
WRITE_ROUTES: dict[tuple[str, str], tuple[str, ...]] = {}
if is_module_enabled("knowledge"):
    WRITE_ROUTES[("POST", "/api/knowledge/position-memory/update")] = ("knowledge:contribute",)


def automatic_position_memory_write(method, path):
    # 只有固定岗位记忆入口免确认；成员、受众和文档版本由该入口在事务内校验。
    return (method, path) == ("POST", "/api/knowledge/position-memory/update") and (method, path) in WRITE_ROUTES


READ_VALIDATORS = {}
READ_METADATA = {}
from app.framework.catalog import iter_module_attr
for module in iter_module_attr("harness_http_policy"):
    for target, attribute in ((READ_ROUTES, "READ_ROUTES"), (WRITE_ROUTES, "WRITE_ROUTES"), (READ_VALIDATORS, "READ_VALIDATORS"), (READ_METADATA, "READ_METADATA")):
        values = getattr(module, attribute, {})
        if target.keys() & values.keys():
            raise ValueError(f"Duplicate HTTP policy in {module.__name__}: {attribute}")
        target.update(values)


HTTP_POLICY_PATH = Path(__file__).with_name("harness_http_policy.json")


@lru_cache(maxsize=8)
def _compiled_http_registry(routes, policy_text, profiles):
    return compile_http_registry(routes.routes, HttpPolicy.model_validate_json(policy_text), dict(profiles),
                                 set(READ_ROUTES) | set(WRITE_ROUTES), scalar=model_scalar)


def http_registry(routes=None):
    if routes is None:
        # Import only after router construction: the registry never imports app.main.
        from app.framework.router import framework_router
        routes = framework_router.routes
    profiles = tuple((name, ResourceProfile(tuple(spec.ai_fields), spec.table_model))
                     for name, spec in sorted(RESOURCES.items()))
    snapshot = RouteSnapshot.capture(routes)
    policy = HttpPolicy.model_validate_json(HTTP_POLICY_PATH.read_text(encoding="utf-8"))
    providers = {}
    for owner, provider in ai_providers():
        if owner is not None:
            providers.setdefault(owner, []).append(provider)
    for route in snapshot.routes:
        owners = {tag.removeprefix("plugin:") for tag in getattr(route, "tags", ()) if tag.startswith("plugin:")}
        # 继承通用策略的插件也可明确声明只读 POST；人工配置仍优先。
        for method in route.methods or ():
            key = f"{method} {route.path}"
            if key not in policy.routes and any(
                provider.inherit_http_policy and (method, route.path) in provider.read_routes
                for owner in owners for provider in providers.get(owner, ())
            ):
                policy.routes[key] = RoutePolicy(mode="read")
        restricted = restricted_route_providers(route, owners, providers)
        if not restricted:
            continue
        for method in route.methods or ():
            key = f"{method} {route.path}"
            # 人工 deny 始终优先；能力包登记不能覆盖运维收紧的策略。
            if key in policy.routes and policy.routes[key].mode == "deny":
                continue
            is_read = all(any((method, route.path) in provider.read_routes for provider in group) for group in restricted)
            is_write = all(any((method, route.path) in provider.write_routes for provider in group) for group in restricted)
            if is_read and is_write:
                raise ValueError("同一接口不能同时登记为 AI 读取和写入")
            if not (is_read or is_write):
                policy.routes[key] = RoutePolicy(mode="deny")
            elif (method, route.path) not in READ_ROUTES and (method, route.path) not in WRITE_ROUTES:
                # 专用投影器继续校验动态响应，不能降为普通 read 策略。
                mode = "read" if is_read else "write"
                existing = policy.routes.get(key)
                policy.routes[key] = existing.model_copy(update={"mode": mode}) if existing else RoutePolicy(mode=mode)
    return _compiled_http_registry(snapshot, policy.model_dump_json(), profiles)


def restricted_route_providers(route, owners, providers):
    """Keep per-module policy boundaries when several modules share one package."""
    endpoint = route.endpoint
    source = getattr(endpoint, "__module__", "").split(".")
    declared = {tag.removeprefix("module:") for tag in getattr(route, "tags", ()) if tag.startswith("module:")}
    module = source[2] if source[:2] == ["app", "modules"] and len(source) > 2 else (
        next(iter(declared)) if len(declared) == 1 else getattr(endpoint, "__harness_crud__", {}).get("module"))
    restricted = []
    for owner in owners:
        group = providers.get(owner, ())
        if len(group) > 1:
            original = group
            group = [item for item in original if module in item.http_modules or any(
                (method, route.path) in item.read_routes for method in route.methods or ())]
            if module is None and not group:
                group = [item for item in original if not item.inherit_http_policy]
        if any(item.inherit_http_policy for item in group) and not all(item.inherit_http_policy for item in group):
            raise ValueError("同一模块不能混用继承 HTTP 策略和显式路由提供器")
        if group and not group[0].inherit_http_policy:
            restricted.append(group)
    return restricted


def inherited_operation(method: str, path: str, routes=None):
    from .harness_http_catalog import catalog_operation
    return catalog_operation(method, path, routes)


def special_route_enabled(method: str, path: str, routes=None) -> bool:
    # A missing optional route is not an enabled special operation.
    return any(row["method"] == method and row["path"] == path and row["state"] == "special"
               for row in http_registry(routes).diagnostics)


def allowed_write(method: str, path: str, routes=None) -> bool:
    if (method, path) in WRITE_ROUTES:
        return special_route_enabled(method, path, routes)
    operation = inherited_operation(method, path, routes)
    return operation is not None and operation.mode == "write"


def allowed_read(method: str, path: str, body: Any, routes=None) -> bool:
    if (method, path) not in READ_ROUTES:
        operation = inherited_operation(method, path, routes)
        return operation is not None and operation.mode == "read"
    if not special_route_enabled(method, path, routes):
        return False
    validator = READ_VALIDATORS.get((method, path))
    return bool(validator(body)) if validator else True


def project_read(method: str, path: str, body: Any, response: Any, routes=None) -> Any | None:
    rule = READ_ROUTES.get((method, path))
    if rule is not None:
        return rule[0](body, response) if special_route_enabled(method, path, routes) else None
    operation = inherited_operation(method, path, routes)
    if operation is None or operation.mode != "read" or operation.projection is None:
        return None
    from app.framework.harness_http import ProjectionError
    try:
        return operation.projection.apply(response, model_scalar)
    except ProjectionError:
        return None


def route_catalog(current_user: AuthenticatedUser, routes=None) -> dict[str, Any]:
    def owns_permission(permission: str) -> bool:
        return permission in current_user.permissions

    read: list[dict[str, Any]] = [{"method": "GET", "path": "/api/harness/catalog"}]
    for (method, path), (_, permission) in READ_ROUTES.items():
        if not special_route_enabled(method, path, routes):
            continue
        if not route_plugin_enabled(method, path, current_user, routes):
            continue
        if permission is not None and not any(owns_permission(key) for key in (permission if isinstance(permission, tuple) else (permission,))):
            continue
        entry: dict[str, Any] = {"method": method, "path": path}
        metadata = READ_METADATA.get((method, path))
        if metadata:
            entry.update(metadata())
        if path in KNOWLEDGE_CONTRACTS:
            entry["parameters"] = {"body": KNOWLEDGE_CONTRACTS[path]}
        read.append(entry)
    write = [
        {"method": method, "path": path}
        for (method, path), permissions in WRITE_ROUTES.items()
        if special_route_enabled(method, path, routes) and route_plugin_enabled(method, path, current_user, routes)
        and any(owns_permission(permission) for permission in permissions)
    ]
    from .harness_http_catalog import static_operations
    for operation in static_operations(routes):
        if not route_plugin_enabled(operation["method"], operation["path"], current_user, routes):
            continue
        if not permitted(operation["permissions"], current_user):
            continue
        entry = {"method": operation["method"], "path": operation["path"], "parameters": operation["parameters"]}
        if operation["resource"]:
            entry["response_resource"] = operation["resource"]
        (read if operation["mode"] == "read" else write).append(entry)
    return {"read": read, "write": write}


def route_availability(method: str, path: str, current_user: AuthenticatedUser, routes=None) -> str:
    """区分路由未注册与当前租户未开通，不从菜单或检索命中推断部署状态。"""
    if routes is None:
        from app.framework.router import framework_router

        routes = framework_router.routes
    for route in RouteSnapshot.capture(routes).routes:
        if method not in (route.methods or ()) or not route.path_regex.fullmatch(path):
            continue
        owners = {tag.removeprefix("plugin:") for tag in route.tags if tag.startswith("plugin:")}
        return "ready" if owners <= set(current_user.enabled_plugin_keys) else "plugin_not_enabled"
    return "route_not_found"


def route_plugin_enabled(method: str, path: str, current_user: AuthenticatedUser, routes=None) -> bool:
    """按路由装配时附带的 plugin 标签过滤 AI 入口和资源目录。"""
    return route_availability(method, path, current_user, routes) == "ready"


def route_plugin_owner(method: str, path: str, routes=None) -> str | None:
    if routes is None:
        from app.framework.router import framework_router
        routes = framework_router.routes
    for route in RouteSnapshot.capture(routes).routes:
        if method in (route.methods or ()) and route.path == path:
            owners = {tag.removeprefix("plugin:") for tag in route.tags if tag.startswith("plugin:")}
            if len(owners) > 1:
                raise ValueError("接口不能同时属于多个能力包")
            return next(iter(owners), None)
    raise ValueError("AI 特殊接口未在当前部署注册")
