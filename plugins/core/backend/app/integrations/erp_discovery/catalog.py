"""Compile reviewed metadata; authorization remains owned by ERP policies."""
from typing import Any

from sqlalchemy import Numeric, Integer, Float

from app.auth.schemas import AuthenticatedUser
from app.framework.deployment import is_module_enabled
from app.core.config import get_settings
from app.integrations.harness_api_policy import READ_ROUTES, WRITE_ROUTES, special_route_enabled, route_plugin_owner
from app.integrations.harness_http_catalog import static_operations
from app.integrations.harness_query_repository import RESOURCES, aggregate_column, canonical_resource_name, conditions, resource_authorized
from app.integrations.harness_ai_catalog import load_semantics
from app.framework.plugin import loaded_plugin_manifests
from app.integrations.harness_query_schemas import QueryAggregate, QueryRequest
from app.integrations.harness_schema_catalog import resource_descriptions
from app.integrations.harness_relations import approved_relations, relation_documents
from app.integrations.harness_value_policy import model_scalar
if is_module_enabled("knowledge"):
    from app.integrations.knowledge.harness import KNOWLEDGE_CONTRACTS
else:
    KNOWLEDGE_CONTRACTS = {}

from resource_discovery.catalog import digest, normalize_catalog
from .models import Semantics



def safe_text(value: str) -> str:
    if model_scalar(value) != value:
        raise ValueError("Discovery metadata contains an unsafe or oversized value")
    return value


def compile_catalog() -> list[dict[str, Any]]:
    semantics = load_semantics()
    # 语义源文件可以同时包含多个能力包；部署组合只发布当前已注册资源。
    # 未安装能力包不能影响当前组合的目录生成。
    semantics = semantics.model_copy(
        update={
            "resources": {name: value for name, value in semantics.resources.items() if name in RESOURCES},
            "metrics": {name: value for name, value in semantics.metrics.items() if value.resource in RESOURCES},
        }
    )
    documents: list[dict[str, Any]] = []
    graph = approved_relations(semantics=semantics)
    max_joins = get_settings().harness_query_max_joins
    for name, spec in sorted(RESOURCES.items()):
        extra = semantics.resources.get(name)
        metadata = resource_descriptions(spec)
        description = safe_text(extra.description) if extra and extra.description else metadata.get("description", "")
        aliases = [safe_text(value) for value in extra.aliases] if extra else []
        field_aliases = extra.field_aliases if extra else {}
        if set(field_aliases) - set(spec.ai_fields):
            raise ValueError(f"Semantics includes hidden fields in {name}")
        fields = [{"name": field, "type": str(spec.table_model.__table__.columns[field].type),
                   "description": metadata.get("field_descriptions", {}).get(field, ""),
                   "aliases": [safe_text(value) for value in field_aliases.get(field, [])],
                   "numeric": isinstance(spec.table_model.__table__.columns[field].type, (Numeric, Integer, Float))}
                  for field in spec.ai_fields]
        relations = relation_documents(name, graph)
        for relation in extra.relations if extra else []:
            if relation.target not in RESOURCES or relation.field not in spec.ai_fields \
                    or relation.target_field not in RESOURCES[relation.target].ai_fields:
                raise ValueError(f"Invalid approved relation in {name}")
        document = {"id": "resource:" + name, "kind": "resource", "label": safe_text(extra.label) if extra else name,
                    "description": description, "aliases": aliases, "domain": spec.domain, "plugin_key": spec.plugin_key,
                    "grain": safe_text(extra.grain) if extra else "", "fields": fields, "relations": relations,
                    "capabilities": ["filter", "order", "paginate", "aggregate", "group_by"] + (["join"] if relations else []),
                    "execution": {"tool": "erp_query", "operation": "query", "resource": name,
                                  "plan_operation": "plan", "plan_version": 1, "max_joins": max_joins,
                                  "aggregate_grain": "root_records_per_group"},
                    "permissions_any": [spec.permission], "dependencies": []}
        documents.append(document)
    if special_route_enabled("GET", "/api/auth/menus"):
        documents.append({"id": "operation:auth.menus", "kind": "operation", "label": "ERP 页面菜单",
                      "description": "获取当前账号可以导航的菜单名称和路径", "aliases": ["跳转", "打开页面"],
                      "domain": "system", "fields": [], "relations": [], "capabilities": ["read"],
                      "permissions_any": [], "dependencies": [],
                      "execution": {"tool": "erp_api", "method": "GET", "path": "/api/auth/menus"}})
    for path, contract in KNOWLEDGE_CONTRACTS.items():
        if not is_module_enabled("knowledge") or not special_route_enabled("POST", path):
            continue
        is_search = path.endswith("/search")
        is_status = path.endswith("/version-status")
        is_bases = path.endswith("/base-options")
        documents.append({"id": f"operation:POST:{path}", "kind": "operation",
                          "label": "新建文档的目标知识库" if is_bases else "知识版本审核进度" if is_status else "企业知识检索" if is_search else "企业知识文档正文",
                          "description": "查询当前用户可管理且可用的知识库名称和 ERP 标识，用于新建在线 Markdown 草稿；不返回凭据或正文。" if is_bases else "查询 ERP 草稿版本编号、并发令牌和审核发布状态，不返回原文。" if is_status else "ERP 按当前用户、角色许可与数据范围先授权，再检索已确认可进入模型的资料；返回可追溯的本地文档编号和来源快照。" if is_search else "使用知识检索结果中的 document_id 分页读取正文；每次读取重新校验权限与来源。",
                          "aliases": ["新建知识文档", "目标知识库", "创建文档"] if is_bases else ["版本", "草稿", "审核进度"] if is_status else ["知识库", "制度", "操作手册"] if is_search else ["文档正文"],
                          "domain": "knowledge", "plugin_key": route_plugin_owner("POST", path),
                          "fields": [], "relations": [], "capabilities": ["read"],
                          "permissions_any": list(READ_ROUTES[("POST", path)][1]) if isinstance(READ_ROUTES[("POST", path)][1], tuple) else [READ_ROUTES[("POST", path)][1]], "dependencies": [],
                          "execution": {"tool": "erp_api", "method": "POST", "path": path},
                          "parameters": {"body": contract}})
    for (method, path), permissions in sorted(WRITE_ROUTES.items()):
        if not special_route_enabled(method, path):
            continue
        documents.append({"id": f"operation:{method}:{path}", "kind": "operation", "label": f"{method} {path}",
                          "description": "业务写入操作；只在用户明确要求对应修改时使用，不返回业务响应正文",
                          "aliases": [], "domain": route_plugin_owner(method, path) or "system", "plugin_key": route_plugin_owner(method, path), "fields": [], "relations": [],
                          "capabilities": ["write"], "permissions_any": list(permissions), "dependencies": [],
                          "execution": {"tool": "erp_api", "method": method, "path": path},
                          "parameter_contract": "使用 ERP 业务文档中已定义的参数；未知参数不得猜测"})
    # Retrieval reads generated static contracts, not a fresh OpenAPI inventory.
    # Each contract is intersected with live permission and output policy first.
    for operation in static_operations():
        resource_name = operation["resource"]
        resource = "resource:" + resource_name if resource_name else None
        label = semantics.resources[resource_name].label if resource_name in semantics.resources else operation["summary"] or operation["path"]
        action = operation["action"]
        action_label = {"list": "列表", "detail": "详情", "create": "新增", "update": "修改", "delete": "删除"}.get(
            action, "读取" if operation["mode"] == "read" else "写入")
        documents.append({"id": f"operation:{operation['method']}:{operation['path']}", "kind": "operation",
                          "label": safe_text(f"{label}{action_label}接口")[:120],
                          "description": "静态接口文档；" + ("沿用业务接口权限和数据范围，原样返回业务字段" if operation["mode"] == "read" else "需要用户确认后执行；仅返回状态")
                                         + ("；" + operation["description"] if operation["description"] else ""),
                          "aliases": [], "domain": operation["module"],
                          "plugin_key": operation.get("plugin_key"),
                          "fields": [{"name": name, "description": spec.get("description", ""), "type": spec.get("type", "scalar"), "schema": spec}
                                     for name, spec in operation["response_schema"].get("properties", {}).items()],
                          "relations": [], "capabilities": [operation["mode"]],
                          "permissions_any": [], "dependencies": [resource] if resource else [],
                          "recipe": {"http_permissions": operation["permissions"]},
                          "execution": {"tool": "erp_api", "method": operation["method"], "path": operation["path"]},
                          "parameters": operation["parameters"], "response_resource": resource})
    for name, metric in sorted(semantics.metrics.items()):
        if metric.resource not in RESOURCES:
            raise ValueError("Metric references an unapproved resource")
        spec = RESOURCES[metric.resource]
        query = QueryRequest(operation="query", resource=metric.resource, fields=metric.dimensions or None,
                             aggregate=QueryAggregate(function=metric.function, field=metric.field),
                             filters=metric.filters, group_by=metric.dimensions)
        validate_query(query, AuthenticatedUser(auth_user_id="00000000-0000-0000-0000-000000000000",
            tenant_id="00000000-0000-0000-0000-000000000000", tenant_no="catalog", tenant_schema="t_catalog",
            user_id="00000000-0000-0000-0000-000000000000", permissions=[spec.permission],
            permission_scopes={spec.permission: "all"}, enabled_plugin_keys=[item.key for item in loaded_plugin_manifests()]))
        documents.append({"id": "metric:" + name, "kind": "metric", "label": safe_text(metric.label),
                          "description": safe_text(metric.description), "aliases": [safe_text(a) for a in metric.aliases],
                          "domain": semantics.resources.get(metric.resource).domain if metric.resource in semantics.resources else "system",
                          "fields": [], "relations": [], "capabilities": ["metric"], "unit": safe_text(metric.unit),
                          "dimensions": metric.dimensions, "recipe": query.model_dump(),
                          "permissions_any": [spec.permission], "dependencies": ["resource:" + metric.resource],
                          "execution": {"tool": "erp_discover", "action": "metric", "metric_id": "metric:" + name}})
    for document in documents:
        if document["kind"] == "metric":
            document["plugin_key"] = RESOURCES[document["recipe"]["resource"]].plugin_key
        document["content_hash"] = digest(document)
    return normalize_catalog(documents)


def authorized_catalog(documents: list[dict[str, Any]], user: AuthenticatedUser) -> list[dict[str, Any]]:
    def permitted(doc):
        from app.framework.harness_http import permitted as permissions_match
        groups = (doc.get("recipe") or {}).get("http_permissions", [])
        owner = doc.get("plugin_key")
        if owner is not None and owner not in user.enabled_plugin_keys:
            return False
        return permissions_match(groups, user) and (not doc["permissions_any"] or any(p in user.permissions for p in doc["permissions_any"]))
    allowed = {doc["id"]: doc for doc in documents if permitted(doc)}
    return [doc for doc in allowed.values() if all(dep in allowed for dep in doc["dependencies"])]


def validate_query(query: QueryRequest, user: AuthenticatedUser) -> None:
    from fastapi import HTTPException
    spec = RESOURCES.get(canonical_resource_name(query.resource) or "")
    if spec is None or not resource_authorized(spec, user):
        raise HTTPException(403, "RESOURCE_UNAVAILABLE")
    allowed = set(spec.ai_fields)
    selected = query.fields or list(spec.ai_fields)
    if len(selected) != len(set(selected)) or len(query.group_by) != len(set(query.group_by)) \
            or set(selected + query.group_by + [o.field for o in query.order]) - allowed:
        raise HTTPException(400, "Unknown or duplicate query field")
    conditions(spec, query, user, allowed)
    if query.group_by and query.aggregate is None:
        raise HTTPException(400, "group_by requires aggregate")
    if query.group_by and query.order:
        raise HTTPException(400, "Grouped aggregate does not accept row ordering")
    if "value" in query.group_by:
        raise HTTPException(400, "The grouped result reserves value for the aggregate")
    if query.aggregate:
        aggregate_column(spec, query.aggregate, allowed)
