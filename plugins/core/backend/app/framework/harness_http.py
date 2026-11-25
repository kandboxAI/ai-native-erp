"""Compile FastAPI metadata against reusable, server-owned HTTP policies.

No business modules or database access belong here. OpenAPI is a description,
never an authorization grant. Business reads retain the authorized API response;
restricted compositions may still declare reviewed resource profiles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Callable, Literal, Union, get_args, get_origin
from uuid import UUID

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from fastapi import routing
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from starlette.routing import Match
from .model_data_protection import OutputRules, filter_result, filtered_schema

DEFAULT_REQUEST_BYTES = 64 * 1024


class StrictPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModulePolicy(StrictPolicy):
    read_actions: list[str] = Field(default_factory=lambda: ["list", "detail", "read"])
    write_actions: list[str] = Field(default_factory=list)
    allow_authenticated: bool = False


class ModelPolicy(StrictPolicy):
    # A model either reuses an approved resource or declares its safe fields once.
    resource: str | None = None
    fields: list[str] = Field(default_factory=list)


class RoutePolicy(StrictPolicy):
    mode: Literal["deny", "read", "write"]
    resource: str | None = None
    shape: Literal["row", "list", "page"] = "row"
    max_request_bytes: int = Field(default=DEFAULT_REQUEST_BYTES, ge=1, le=28_000_000)


class HttpPolicy(StrictPolicy):
    version: Literal[1] = 1
    automatic_reads: bool = False
    all_business_interfaces: bool = False
    output_rules: OutputRules = Field(default_factory=OutputRules)
    # 保留已发布配置字段的解析兼容；自动响应不再按名称或聚合类型筛选。
    aggregate_fields: list[str] = Field(default_factory=lambda: [
        "total", "count", "page", "page_size", "pageSize", "total_pages",
        "amount", "sum", "average", "avg", "minimum", "maximum", "min", "max", "rate", "ratio", "percentage",
    ])
    aggregate_suffixes: list[str] = Field(default_factory=lambda: ["_count", "_total", "_amount", "_rate", "_ratio", "_percentage"])
    modules: dict[str, ModulePolicy] = Field(default_factory=dict)
    models: dict[str, ModelPolicy] = Field(default_factory=dict)
    routes: dict[str, RoutePolicy] = Field(default_factory=dict)


@dataclass(frozen=True)
class ResourceProfile:
    fields: tuple[str, ...]
    item_model: type[BaseModel]


class ProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class Projection:
    kind: Literal["scalar", "object", "list", "filtered"]
    fields: tuple[tuple[str, "Projection"], ...] = ()
    item: "Projection | None" = None
    nullable: bool = False
    required: tuple[str, ...] = ()
    schema: dict = field(default_factory=dict)
    rules: OutputRules | None = None

    def apply(self, value: Any, scalar: Callable[[Any], Any], depth: int = 0,
              *, counts: dict[str, int] | None = None) -> Any:
        if self.kind == "filtered":
            try:
                return filter_result(value, self.rules or OutputRules(), self.schema, counts=counts)
            except ValueError as error:
                raise ProjectionError(str(error)) from error
        if depth > 8:
            raise ProjectionError("Response nesting exceeds policy")
        if value is None and (self.nullable or self.kind == "scalar"):
            return None
        if self.kind == "scalar":
            if isinstance(value, (dict, list)):
                raise ProjectionError("Unexpected structured value")
            return scalar(value)
        if self.kind == "list":
            if not isinstance(value, list) or len(value) > 200 or self.item is None:
                raise ProjectionError("Unexpected or oversized collection")
            return [self.item.apply(item, scalar, depth + 1) for item in value]
        if not isinstance(value, dict):
            raise ProjectionError("Unexpected response shape")
        if set(self.required) - set(value):
            raise ProjectionError("Required response fields are missing")
        return {name: child.apply(value[name], scalar, depth + 1)
                for name, child in self.fields if name in value}


SCALAR = Projection("scalar")


def model_key(model: type[BaseModel]) -> str:
    return f"{model.__module__}.{model.__qualname__}"


def model_projection(annotation: Any, policy: HttpPolicy, resources: dict[str, ResourceProfile],
                     seen: tuple[type, ...] = (), by_alias: bool = True) -> Projection:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated:
        return model_projection(args[0], policy, resources, seen, by_alias)
    if origin in (Union, UnionType):
        non_null = [arg for arg in args if arg is not type(None)]
        if len(non_null) != 1:
            raise ProjectionError("Ambiguous union response needs a profile")
        child = model_projection(non_null[0], policy, resources, seen, by_alias)
        return Projection(child.kind, child.fields, child.item, type(None) in args, child.required)
    if origin is list:
        return Projection("list", item=model_projection(args[0], policy, resources, seen, by_alias))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen or len(seen) >= 8:
            raise ProjectionError("Recursive response needs a special projector")
        config = next((policy.models[model_key(base)] for base in annotation.__mro__
                       if issubclass(base, BaseModel) and model_key(base) in policy.models), None)
        if config is None:
            resource = next((profile for profile in resources.values() if profile.item_model is annotation), None)
            names = resource.fields if resource else ()
        elif config.resource:
            if config.fields or config.resource not in resources:
                raise ProjectionError("Invalid model resource profile")
            names = resources[config.resource].fields
        else:
            names = tuple(config.fields)
        if not names or len(names) != len(set(names)) or set(names) - set(annotation.model_fields):
            raise ProjectionError("Response model has no complete field policy")
        def wire_name(name):
            field = annotation.model_fields[name]
            return (field.serialization_alias or field.alias or name) if by_alias else name
        return Projection("object", fields=tuple(
            (wire_name(name), model_projection(annotation.model_fields[name].annotation, policy, resources, (*seen, annotation), by_alias))
            for name in names), required=tuple(wire_name(name) for name in names if annotation.model_fields[name].is_required()))
    if annotation in (str, int, float, bool, UUID, date, datetime, time, type(None)) \
            or origin is Literal or isinstance(annotation, type) and issubclass(annotation, Enum):
        return SCALAR
    raise ProjectionError("Untyped/object response needs a reviewed profile")


def resource_projection(resource: str, shape: str, resources: dict[str, ResourceProfile]) -> Projection:
    profile = resources.get(resource)
    if profile is None or not profile.fields or set(profile.fields) - set(profile.item_model.model_fields):
        raise ProjectionError("Unknown or invalid resource profile")
    row = Projection("object", fields=tuple((name, SCALAR) for name in profile.fields))
    if shape == "row":
        return row
    rows = Projection("list", item=row)
    if shape == "list":
        return rows
    return Projection("object", fields=(("items", rows), ("total", SCALAR), ("page", SCALAR), ("page_size", SCALAR)),
                      required=("items", "total", "page", "page_size"))


def dependency_policy(route: APIRoute) -> tuple[bool, tuple[tuple[str, tuple[str, ...]], ...]]:
    authenticated = False
    groups: list[tuple[str, tuple[str, ...]]] = []
    seen = set()

    def visit(dependency):
        nonlocal authenticated
        if id(dependency) in seen:
            return
        seen.add(id(dependency))
        call = dependency.call
        authenticated |= bool(getattr(call, "__harness_authenticated__", False))
        if rule := getattr(call, "__harness_permissions__", None):
            groups.append((rule[0], tuple(rule[1])))
        for child in dependency.dependencies:
            visit(child)

    visit(route.dependant)
    return authenticated, tuple(groups)


def permitted(groups, user) -> bool:
    owned = set(user.permissions)
    return all((all(permission in owned for permission in permissions) if mode == "all"
                else any(permission in owned for permission in permissions)) for mode, permissions in groups)


def safe_schema(schema: Any, components: dict, seen: tuple[str, ...] = (), depth: int = 0,
                scalar: Callable[[Any], Any] = lambda _value: None) -> Any:
    """Keep structural contracts; never copy examples, defaults or vendor extensions."""
    if not isinstance(schema, dict) or depth > 8:
        return {}
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return {"type": "object"}
        return safe_schema(components.get(name, {}), components, (*seen, name), depth + 1, scalar)
    result = {key: schema[key] for key in ("type", "format", "minimum", "maximum", "minLength", "maxLength",
                                           "minItems", "maxItems", "required") if key in schema}
    if "enum" in schema:
        result["enum"] = [scalar(value) for value in schema["enum"]]
    if isinstance(schema.get("description"), str) and scalar(schema["description"]) is not None:
        result["description"] = scalar(schema["description"])
    if "properties" in schema:
        result["properties"] = {name: safe_schema(value, components, seen, depth + 1, scalar)
                                for name, value in schema["properties"].items()}
    if "items" in schema:
        result["items"] = safe_schema(schema["items"], components, seen, depth + 1, scalar)
    for name in ("anyOf", "oneOf", "allOf"):
        if name in schema:
            result[name] = [safe_schema(value, components, seen, depth + 1, scalar) for value in schema[name]]
    return result


@dataclass
class HttpOperation:
    route: APIRoute
    method: str
    mode: str
    projection: Projection | None
    permissions: tuple[tuple[str, tuple[str, ...]], ...]
    resource: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    response_policy: str = "approved_fields"
    max_request_bytes: int = DEFAULT_REQUEST_BYTES


@dataclass
class HttpRegistry:
    routes: tuple[APIRoute, ...]
    operations: dict[tuple[str, str], HttpOperation]
    diagnostics: list[dict[str, str]]
    denied_routes: set[tuple[str, str]] = field(default_factory=set)

    def resolve(self, method: str, path: str) -> HttpOperation | None:
        # Match actual dispatch order, including unapproved shadowing routes.
        scope = {"type": "http", "method": method, "path": path, "root_path": ""}
        for route in self.routes:
            match, _ = route.matches(scope)
            if match is Match.FULL:
                return self.operations.get((method, route.path))
        return None


def route_contexts(routes) -> tuple:
    # Recent FastAPI preserves included routers lazily. Its OpenAPI iterator
    # applies prefixes and include-level dependencies; older releases are flat.
    iterator = getattr(routing, "iter_route_contexts", None)
    return tuple(iterator(routes)) if iterator else tuple(routes)


@dataclass(frozen=True)
class RouteSnapshot:
    signature: tuple
    routes: tuple = field(compare=False, hash=False)

    @classmethod
    def capture(cls, routes):
        contexts = route_contexts(routes)
        signature = tuple((id(getattr(route, "original_route", route)), getattr(route, "path", None),
                           tuple(sorted(getattr(route, "methods", None) or ())), id(getattr(route, "dependant", None)),
                           getattr(route, "include_in_schema", None),
                           tuple(sorted(getattr(route, "tags", ()) or ()))) for route in contexts)
        return cls(signature, contexts)


def compile_http_registry(routes, policy: HttpPolicy, resources: dict[str, ResourceProfile],
                          special_routes: set[tuple[str, str]] = frozenset(),
                          scalar: Callable[[Any], Any] = lambda _value: None) -> HttpRegistry:
    routes = route_contexts(routes)
    operations = {}
    diagnostics = []
    seen_keys = set()
    for route in routes:
        if not isinstance(getattr(route, "original_route", route), APIRoute):
            continue
        for method in sorted(route.methods):
            key = (method, route.path)
            if key in seen_keys:
                raise ValueError("Duplicate HTTP route requires explicit resolution")
            seen_keys.add(key)
            if not route.path.startswith("/api/") or route.path.startswith(("/api/harness/", "/api/llm-gateway/", "/api/plugins", "/api/ai/")):
                continue
            if key in special_routes:
                override = policy.routes.get(f"{method} {route.path}")
                if override and override.mode != "deny":
                    raise ValueError("Special projectors only support deny overrides")
                diagnostics.append({"method": method, "path": route.path, "state": "blocked" if override else "special",
                                    "reason": "接口显式禁用" if override else "特殊投影规则"})
                continue
            reason = "模块未启用"
            binding = getattr(route.endpoint, "__harness_crud__", {})
            module = binding.get("module") or route.path.split("/")[2]
            module_policy = policy.modules.get(module) or (ModulePolicy(allow_authenticated=True,
                write_actions=["create", "update", "delete", "write"]) if policy.all_business_interfaces
                else ModulePolicy() if policy.automatic_reads else None)
            override = policy.routes.get(f"{method} {route.path}")
            try:
                if not route.include_in_schema:
                    raise ProjectionError("未公开的接口")
                if override and override.mode == "deny":
                    raise ProjectionError("接口显式禁用")
                if policy.all_business_interfaces and (
                    route.path.startswith("/api/auth/")
                    or any(part in route.path.casefold() for part in ("oauth", "captcha", "credential", "token", "bind-url", "register_options"))
                ):
                    raise ProjectionError("认证凭证接口隔离")
                if module_policy is None:
                    raise ProjectionError(reason)
                authenticated, permissions = dependency_policy(route)
                if not policy.all_business_interfaces and (not authenticated or not any(group[1] for group in permissions) and not module_policy.allow_authenticated):
                    raise ProjectionError("认证或权限元数据不完整")
                action = binding.get("action") or ("read" if method == "GET" else "write" if policy.all_business_interfaces else "unknown")
                mode = override.mode if override else ("read" if action in module_policy.read_actions
                                                        else "write" if action in module_policy.write_actions else "deny")
                if mode == "deny" or mode == "read" and method not in ("GET", "POST"):
                    raise ProjectionError("接口动作未启用")
                if binding.get("action") in {"create", "update", "delete"} and mode == "read":
                    raise ProjectionError("标准写操作不能声明为读取")
                resource = override.resource if override and override.resource else binding.get("resource")
                if policy.all_business_interfaces and resource not in resources:
                    resource = None
                projection = None
                response_policy = "approved_fields"
                if mode == "read":
                    if policy.all_business_interfaces:
                        # 原业务接口执行权限和范围校验，AI 不再增加逐字段白名单。
                        projection = Projection("filtered", rules=policy.output_rules)
                        response_policy = "recursive_filter"
                    elif resource and resource in resources:
                        shape = override.shape if override and override.resource else ("page" if action == "list" else "row")
                        projection = resource_projection(resource, shape, resources)
                    else:
                        if resource:
                            raise ProjectionError("Unknown or invalid resource profile")
                        response_model = route.response_model
                        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel) \
                                or not {"code", "data"}.issubset(response_model.model_fields):
                            raise ProjectionError("响应缺少已声明的标准 envelope 和字段策略")
                        try:
                            projection = model_projection(response_model.model_fields["data"].annotation, policy, resources,
                                                          by_alias=route.response_model_by_alias)
                        except ProjectionError:
                            if not policy.automatic_reads:
                                raise
                            projection = Projection("filtered", rules=policy.output_rules)
                        leaf = projection
                        while leaf.kind == "list":
                            leaf = leaf.item
                        if leaf.kind == "scalar":
                            envelope_policy = next((policy.models[model_key(base)] for base in response_model.__mro__
                                                    if issubclass(base, BaseModel) and model_key(base) in policy.models), None)
                            if envelope_policy is None or "data" not in envelope_policy.fields:
                                raise ProjectionError("顶层标量或标量列表需要明确的 envelope 字段策略")
                operations[key] = HttpOperation(route, method, mode, projection, permissions, resource,
                                                response_policy=response_policy,
                                                max_request_bytes=override.max_request_bytes if override else DEFAULT_REQUEST_BYTES)
                if projection is not None:
                    if resource:
                        row_schema = resources[resource].item_model.model_json_schema()
                        row_schema = safe_schema(row_schema, row_schema.get("$defs", {}), scalar=scalar)
                        if projection.kind == "list":
                            declared = {"type": "array", "items": row_schema}
                        elif projection.required == ("items", "total", "page", "page_size"):
                            declared = {"properties": {"items": {"type": "array", "items": row_schema}}}
                        else:
                            declared = row_schema
                    elif projection.kind == "filtered":
                        declared = {}
                    else:
                        declared = TypeAdapter(route.response_model.model_fields["data"].annotation).json_schema(
                            mode="serialization", by_alias=route.response_model_by_alias)
                        declared = safe_schema(declared, declared.get("$defs", {}), scalar=scalar)
                    operations[key].response_schema = projection_contract(projection, declared) if projection.kind != "filtered" else filtered_schema(declared, policy.output_rules)
                state, reason = "approved", "继承模块与响应策略"
            except ProjectionError as error:
                state, reason = "blocked", str(error)
            diagnostics.append({"method": method, "path": route.path, "state": state, "reason": reason})
    if operations:
        unique_routes = {id(op.route): op.route for op in operations.values()}
        schema = get_openapi(title="Harness contracts", version="1", routes=list(unique_routes.values()))
        components = schema.get("components", {}).get("schemas", {})
        for operation in operations.values():
            contract = schema.get("paths", {}).get(operation.route.path_format, {}).get(operation.method.lower(), {})
            for parameter in contract.get("parameters", []):
                name = f"{parameter['in']}.{parameter['name']}"
                operation.parameters[name] = {"in": parameter["in"], "name": parameter["name"],
                                              "required": parameter.get("required", False),
                                              **safe_schema(parameter.get("schema", {}), components, scalar=scalar)}
            body = contract.get("requestBody", {})
            if body:
                operation.parameters["body"] = {"in": "body", "required": body.get("required", False),
                                                 **safe_schema(body.get("content", {}).get("application/json", {}).get("schema", {}), components, scalar=scalar)}
            if operation.response_policy == "recursive_filter":
                response = next((value for status, value in contract.get("responses", {}).items() if str(status).startswith("2")), {})
                declared = safe_schema(response.get("content", {}).get("application/json", {}).get("schema", {}), components, scalar=scalar)
                declared = declared.get("properties", {}).get("data", declared)
                operation.projection = Projection("filtered", schema=declared, rules=policy.output_rules)
                operation.response_schema = filtered_schema(declared, policy.output_rules)
    denied = {(key.split(" ", 1)[0], key.split(" ", 1)[1]) for key, value in policy.routes.items() if value.mode == "deny"}
    return HttpRegistry(routes, operations, diagnostics, denied)


def projection_contract(projection: Projection, declared: dict) -> dict:
    """Describe exactly the projected output, never the raw response model."""
    if projection.kind == "scalar":
        return {key: value for key, value in declared.items()
                if key in {"type", "format", "description", "enum", "minimum", "maximum", "anyOf", "oneOf"}}
    if projection.kind == "list":
        return {"type": "array", "items": projection_contract(projection.item, declared.get("items", {})), "maxItems": 200}
    result = {"type": "object", "properties": {
        name: projection_contract(child, declared.get("properties", {}).get(name, {})) for name, child in projection.fields}}
    if projection.required:
        result["required"] = list(projection.required)
    return result
