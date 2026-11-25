"""Static OpenAPI operation documents, revalidated against live server policy."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from resource_discovery.catalog import digest
from app.framework.harness_http import DEFAULT_REQUEST_BYTES

from . import harness_api_policy
from .harness_artifacts import CORE_OWNER, artifact_path, selected_owners, route_owner
from .harness_value_policy import model_scalar

CATALOG_DIR = Path(__file__).with_name("harness_http")
CATALOG_VERSION = 4
logger = logging.getLogger(__name__)


def operation_document(operation) -> dict:
    """Deterministic safe contract, also used to detect obsolete static entries."""
    binding = getattr(operation.route.endpoint, "__harness_crud__", {})
    document = {
        "metadata_key": route_owner(operation.route),
        "method": operation.method, "path": operation.route.path, "mode": operation.mode,
        "module": binding.get("module") or operation.route.path.split("/")[2],
        "action": binding.get("action") or operation.mode,
        "summary": model_scalar(operation.route.summary or operation.route.name),
        "description": model_scalar(operation.route.description),
        "resource": operation.resource, "parameters": operation.parameters,
        "response_schema": operation.response_schema,
        "response_policy": operation.response_policy,
        "approval_required": operation.mode == "write",
        "output_rules": operation.projection.rules.model_dump() if operation.projection and operation.projection.rules else None,
        "permissions": [[mode, list(names)] for mode, names in operation.permissions],
    }
    owners = {tag.removeprefix("plugin:") for tag in operation.route.tags if tag.startswith("plugin:")}
    if len(owners) > 1:
        raise ValueError("HTTP 接口不能同时属于多个能力包")
    if owners:
        document["plugin_key"] = next(iter(owners))
    # 例外容量纳入契约哈希；默认容量不改变其他接口的既有快照。
    if operation.max_request_bytes != DEFAULT_REQUEST_BYTES:
        document["max_request_bytes"] = operation.max_request_bytes
    document["contract_hash"] = digest(document)
    return document


@lru_cache(maxsize=4)
def _parse(text, owner):
    source = json.loads(text)
    if not isinstance(source, dict) or source.get("version") != CATALOG_VERSION or source.get("owner") != owner or not isinstance(source.get("operations"), list):
        raise ValueError("接口静态目录格式无效，请执行 sync")
    entries = {}
    for document in source["operations"]:
        if not isinstance(document, dict):
            raise ValueError("接口静态目录条目无效")
        if document.get("metadata_key") != owner:
            raise ValueError("接口静态目录条目归属错误")
        key = (document.get("method"), document.get("path"))
        if key in entries:
            raise ValueError("接口静态目录包含重复条目")
        entries[key] = document
    return entries


def static_operations(routes=None) -> list[dict]:
    entries = {}
    for owner in selected_owners():
        try:
            shard = _parse(artifact_path(CATALOG_DIR, owner).read_text(encoding="utf-8"), owner)
        except (OSError, ValueError, TypeError):
            logger.warning("接口静态目录缺失或损坏：%s；该能力的普通 HTTP 接口未开放，请执行 harness_http_cli sync", owner)
            continue
        if entries.keys() & shard.keys():
            raise ValueError("接口静态目录跨能力重复")
        entries.update(shard)
    # No static permission or projection can grant access. Match every field
    # against today's compiler, so revocations and shape changes apply at once.
    registry = harness_api_policy.http_registry(routes)
    return [entries[key] for key, operation in registry.operations.items()
            if key in entries and entries[key] == operation_document(operation)]


def catalog_operation(method, path, routes=None):
    operation = harness_api_policy.http_registry(routes).resolve(method, path)
    if operation is None:
        return None
    key = (operation.method, operation.route.path)
    return operation if any((doc["method"], doc["path"]) == key for doc in static_operations(routes)) else None
