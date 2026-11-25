"""Merge observed schema metadata owned by the currently loaded AI providers.

Tenant schemas may install different packages. Artifacts contain no tenant name,
business rows or authorization grants; missing artifacts disable relation evidence.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.framework.ai_catalog import registered_ai_resources
from .harness_artifacts import CORE_OWNER, artifact_path, read_artifact, selected_owners
from .harness_value_policy import model_scalar

SNAPSHOT_DIR = Path(__file__).with_name("harness_schema")
SNAPSHOT_VERSION = 3


def resource_owners() -> dict[str, str]:
    return {name: resource.metadata_key for name, resource in registered_ai_resources().items()}


def validate_shard(document: dict, owner: str) -> None:
    def field_list(value):
        return isinstance(value, list) and all(isinstance(field, str) for field in value) and len(value) == len(set(value))

    tables = document.get("tables")
    if not isinstance(tables, list):
        raise ValueError("结构快照 tables 必须是数组")
    owners = resource_owners()
    seen = set()
    for table in tables:
        if not isinstance(table, dict) or not isinstance(table.get("name"), str):
            raise ValueError("结构快照表定义无效")
        name = table["name"]
        if name in seen or owners.get(name) != owner:
            raise ValueError(f"结构快照包含重复、未登记或归属不符的表：{name}")
        seen.add(name)
        columns = table.get("columns")
        if not isinstance(columns, list) or any(not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in columns):
            raise ValueError(f"结构快照字段定义无效：{name}")
        names = [row["name"] for row in columns]
        if len(names) != len(set(names)):
            raise ValueError(f"结构快照字段重复：{name}")
        if not isinstance(table.get("primary_key"), list) or not isinstance(table.get("unique_keys"), list) or not isinstance(table.get("foreign_keys"), list):
            raise ValueError(f"结构快照缺少约束证据：{name}")
        if not field_list(table["primary_key"]) or not all(field_list(key) and key for key in table["unique_keys"]):
            raise ValueError(f"结构快照键定义无效：{name}")
        for relation in table["foreign_keys"]:
            if not isinstance(relation, dict) or not isinstance(relation.get("target"), str) \
                    or not field_list(relation.get("fields")) or not relation["fields"] \
                    or not field_list(relation.get("target_fields")) \
                    or len(relation["fields"]) != len(relation["target_fields"]) \
                    or type(relation.get("validated")) is not bool:
                raise ValueError(f"结构快照外键证据无效：{name}")


def read_shards(directory: Path, plugins=None) -> dict[str, dict]:
    documents = {}
    for owner in selected_owners(plugins):
        path = artifact_path(directory, owner)
        if not path.exists():
            continue
        document = read_artifact(path, owner=owner, version=SNAPSHOT_VERSION)
        validate_shard(document, owner)
        documents[owner] = document
    return documents


@lru_cache(maxsize=1)
def load_snapshot() -> dict[str, Any]:
    documents = read_shards(SNAPSHOT_DIR)
    tables = [table for document in documents.values() for table in document["tables"]]
    return {"version": SNAPSHOT_VERSION, "tables": sorted(tables, key=lambda table: table["name"])}


def snapshot_errors(directory: Path | None = None, plugins=None) -> list[str]:
    from .harness_query_repository import RESOURCES
    documents = read_shards(directory if directory is not None else SNAPSHOT_DIR, plugins)
    errors = []
    owners = resource_owners()
    for owner in selected_owners(plugins):
        if owner not in documents:
            errors.append(f"缺少结构快照：{owner}")
            continue
        observed = {table["name"]: {column["name"] for column in table["columns"]}
                    for table in documents[owner]["tables"]}
        primary_keys = {table["name"]: set(table["primary_key"]) for table in documents[owner]["tables"]}
        for name, resource in RESOURCES.items():
            if owners[name] == owner:
                missing = set(resource.ai_fields) - observed.get(name, set())
                if missing:
                    errors.append(f"结构快照缺少模型字段：{name}({', '.join(sorted(missing))})")
                if name in primary_keys and primary_keys[name] != set(RESOURCES[name].table_model.__table__.primary_key.columns.keys()):
                    errors.append(f"结构快照主键与当前 ORM 不一致：{name}")
    return errors


def resource_descriptions(resource: Any) -> dict[str, Any]:
    """返回已登记资源的模型字段注释，不按个人信息分级裁剪。"""
    table_name = resource.table_model.__tablename__
    table_row = next((row for row in load_snapshot()["tables"] if row.get("name") == table_name), None)
    if table_row is None:
        return {}
    visible: dict[str, Any] = {}
    if description := model_scalar(table_row.get("comment")):
        visible["description"] = description
    columns = {row.get("name"): row for row in table_row.get("columns", [])}
    field_descriptions = {field: comment for field in resource.ai_fields
                          if (row := columns.get(field)) is not None and (comment := model_scalar(row.get("comment")))}
    if field_descriptions:
        visible["field_descriptions"] = field_descriptions
    return visible
