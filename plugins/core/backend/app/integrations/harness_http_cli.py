"""Offline HTTP inventory; does not start FastAPI, call business APIs or grant access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.framework.harness_http import safe_schema
from app.integrations import harness_api_policy
from app.integrations.harness_value_policy import model_scalar
from app.integrations.harness_http_catalog import CATALOG_DIR, CATALOG_VERSION, operation_document
from app.integrations.harness_artifacts import CORE_OWNER, artifact_path, publish_artifacts, read_artifact, route_owner, selected_owners
from resource_discovery.catalog import digest

DEFAULT_OUTPUT = CATALOG_DIR


def snapshot() -> dict:
    registry = harness_api_policy.http_registry()
    schema = get_openapi(title="ERP HTTP inventory", version="1", routes=list(registry.routes))
    components = schema.get("components", {}).get("schemas", {})
    by_key = {(item["method"], item["path"]): item for item in registry.diagnostics}
    entries = []
    for route in registry.routes:
        if not isinstance(getattr(route, "original_route", route), APIRoute):
            continue
        for method in sorted(route.methods):
            diagnostic = by_key.get((method, route.path))
            if diagnostic is None:
                continue
            contract = schema.get("paths", {}).get(route.path_format, {}).get(method.lower(), {})
            parameters = []
            for parameter in contract.get("parameters", []):
                parameters.append({"name": parameter["name"], "in": parameter["in"],
                                   "required": parameter.get("required", False),
                                   "schema": safe_schema(parameter.get("schema", {}), components, scalar=model_scalar)})
            body = contract.get("requestBody", {})
            responses = {status: safe_schema(response.get("content", {}).get("application/json", {}).get("schema", {}),
                                            components, scalar=model_scalar)
                         for status, response in contract.get("responses", {}).items()}
            entries.append({**diagnostic, "owner": route_owner(route), "summary": model_scalar(route.summary or route.name),
                            "description": model_scalar(route.description), "parameters": parameters,
                            "request_body": safe_schema(body.get("content", {}).get("application/json", {}).get("schema", {}),
                                                        components, scalar=model_scalar), "responses": responses})
    return {"version": CATALOG_VERSION,
            "operations": [operation_document(operation) for _, operation in sorted(registry.operations.items())],
            "routes": entries}


def partition_snapshot(current, plugins=None):
    available = set(selected_owners())
    owners = {(operation.get("metadata_key") or operation.get("plugin_key") or CORE_OWNER) for operation in current["operations"]}
    owners.update(route["owner"] for route in current["routes"])
    if owners - available:
        raise ValueError("接口目录包含未加载的能力包归属")
    documents = {}
    for owner in selected_owners(plugins):
        operations = [operation for operation in current["operations"] if (operation.get("metadata_key") or operation.get("plugin_key") or CORE_OWNER) == owner]
        routes = [route for route in current["routes"] if route["owner"] == owner]
        payload = {"version": CATALOG_VERSION, "owner": owner, "operations": operations, "routes": routes}
        documents[owner] = {**payload, "source_hash": digest(payload)}
    return documents


def run(command, output=None, plugins=None) -> int:
    documents = partition_snapshot(snapshot(), plugins)
    directory = output if output is not None else DEFAULT_OUTPUT
    if command == "sync":
        publish_artifacts(directory, documents)
        print(f"接口目录已同步：{', '.join(documents)}")
    else:
        for owner, document in documents.items():
            path = artifact_path(directory, owner)
            if not path.exists() or read_artifact(path, owner=owner, version=CATALOG_VERSION) != document:
                print(f"接口快照缺失或与当前路由/策略不一致：{owner}，请执行 sync 并审核差异。")
                return 1
        print("所选能力的接口快照与当前路由和策略一致。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成静态接口目录并可选重建索引，不修改字段策略")
    parser.add_argument("command", choices=("sync", "check", "rebuild"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plugin", action="append", dest="plugins", help="core、已加载 shared_* 分组或插件；可重复；默认全部")
    parser.add_argument("--schema", help="rebuild 发布索引的目标租户；sync/check 不访问数据库")
    args = parser.parse_args(argv)
    if args.command == "rebuild" and not args.schema:
        print("rebuild 必须通过 --schema 指定索引发布的目标租户，未生成目录或发布索引。")
        return 1
    if args.command == "rebuild" and (args.output.resolve() != CATALOG_DIR.resolve() or args.plugins):
        print("rebuild 必须使用默认目录位置，未生成目录或发布索引。")
        return 1
    try:
        code = run("sync" if args.command == "rebuild" else args.command, args.output, args.plugins)
        if code:
            return code
        if args.command == "rebuild":
            from app.modules.harness_discovery.cli import main as discovery_main
            return discovery_main(["build-index", "--schema", args.schema])
        return 0
    except (ValueError, OSError):
        print("接口目录检查失败，请核对路由契约与集中策略；未修改访问策略。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
