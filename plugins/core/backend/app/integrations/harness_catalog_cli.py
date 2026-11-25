"""Independent, read-only schema inventory partitioned by AI resource ownership."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import asyncpg

from app.core.config import get_settings, tenant_schema_name
from app.framework.db.tenant import validate_tenant_schema

from .harness_artifacts import artifact_path, publish_artifacts, read_artifact, selected_owners
from .harness_schema_catalog import SNAPSHOT_DIR, SNAPSHOT_VERSION, load_snapshot, resource_owners, validate_shard
from .harness_relation_repository import attach_constraints, read_constraints
from .harness_query_repository import RESOURCES

LEGACY_PATH = Path(__file__).with_name("harness_schema.generated.json")
_SCHEMA_SQL = """
SELECT c.relname AS table_name,
       obj_description(c.oid, 'pg_class') AS table_comment,
       a.attname AS column_name, format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       col_description(c.oid, a.attnum) AS column_comment
FROM pg_catalog.pg_namespace AS n
JOIN pg_catalog.pg_class AS c ON c.relnamespace = n.oid
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
WHERE n.nspname = $1 AND c.relkind IN ('r', 'p')
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

# 已完成结构与数据迁移、仅为回退保留的旧后勤表。它们不能继续进入 Harness
# 元数据目录，否则同一业务对象会同时暴露旧、新两套表定义。
DEPRECATED_TABLES = frozenset(
    {
        "can_ingredient_profile",
        "can_procurement_plan",
        "can_recipe",
        "can_recipe_ingredient",
        "log_equipment_disposal",
        "log_repair_order",
        "log_repair_progress",
        "patrol_photo",
        "patrol_point",
        "patrol_record",
    }
)


def snapshot_from_rows(rows: list[Any]) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        if (
            row["table_name"] in DEPRECATED_TABLES
            or row["table_name"].startswith(("alembic_", "auth_"))
        ):
            continue
        if not tables or tables[-1]["name"] != row["table_name"]:
            tables.append({
                "name": row["table_name"], "comment": row["table_comment"] or "", "columns": [],
            })
        tables[-1]["columns"].append({
            "name": row["column_name"], "data_type": row["data_type"],
            "nullable": row["nullable"], "comment": row["column_comment"] or "",
        })
    if not tables:
        raise RuntimeError("No database tables found; verify the database URL and schema")
    return {"version": SNAPSHOT_VERSION, "tables": tables}


async def read_database_snapshot(schema: str) -> dict[str, Any]:
    # Only pg_catalog metadata; schema is bound, never interpolated.
    schema = validate_tenant_schema(schema)
    dsn = get_settings().database_url
    for driver in ("+asyncpg", "+psycopg2", "+psycopg"):
        dsn = dsn.replace(f"postgresql{driver}://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        rows = await connection.fetch(_SCHEMA_SQL, schema)
        return attach_constraints(snapshot_from_rows(rows), await read_constraints(connection, schema), schema=schema)
    finally:
        await connection.close()


def missing_approved_fields(snapshot: dict[str, Any], plugins=None) -> list[str]:
    owners = resource_owners()
    selected = selected_owners(plugins)
    tables = {row["name"]: {column["name"] for column in row["columns"]} for row in snapshot["tables"]}
    return sorted(f"{name}.{field}" for name, resource in RESOURCES.items()
                  if owners[name] in selected for field in resource.ai_fields
                  if field not in tables.get(name, set()))


def partition_snapshot(snapshot: dict, plugins=None) -> dict[str, dict]:
    """发布已登记资源的模型字段；跨包外键证据仍保存在来源分片。"""
    owners = resource_owners()
    documents = {}
    for owner in selected_owners(plugins):
        tables = []
        for source in sorted(snapshot["tables"], key=lambda row: row["name"]):
            name = source["name"]
            if owners.get(name) != owner:
                continue
            fields = set(RESOURCES[name].ai_fields)
            table = {key: source[key] for key in ("name", "comment", "primary_key", "unique_keys", "foreign_keys")}
            table["columns"] = [column for column in source["columns"] if column["name"] in fields]
            # Other-package targets stay here; runtime requires both approved endpoints.
            table["foreign_keys"] = [fk for fk in table["foreign_keys"] if set(fk["fields"]) <= fields]
            tables.append(table)
        document = {"version": SNAPSHOT_VERSION, "owner": owner, "tables": tables}
        validate_shard(document, owner)
        documents[owner] = document
    return documents


async def run(mode: str, schema: str | None = None, output: Path | None = None, plugins=None) -> int:
    if mode not in ("sync", "check"):
        raise ValueError("Unknown schema maintenance mode")
    selected_owners(plugins)  # Reject invalid selections before opening a connection.
    schema = validate_tenant_schema(schema or default_schema())
    snapshot = await read_database_snapshot(schema)
    missing = missing_approved_fields(snapshot, plugins)
    if missing:
        print(f"Approved Harness fields missing from database: {', '.join(missing)}", file=sys.stderr)
        return 1  # Never replace working artifacts with an incomplete inventory.
    documents = partition_snapshot(snapshot, plugins)
    directory = output if output is not None else SNAPSHOT_DIR
    if mode == "sync":
        publish_artifacts(directory, documents)
        load_snapshot.cache_clear()
        print(f"结构快照已同步：{', '.join(documents)}；请审核差异，未修改字段授权。")
        return 0
    errors = []
    for owner, document in documents.items():
        path = artifact_path(directory, owner)
        if not path.exists() or read_artifact(path, owner=owner, version=SNAPSHOT_VERSION) != document:
            errors.append(owner)
    if errors:
        print(f"结构快照缺失或与目标数据库不一致：{', '.join(errors)}", file=sys.stderr)
        return 1
    print("所选能力的结构快照与目标数据库一致。")
    return 0


def split_legacy(source: Path, output: Path, plugins=None) -> int:
    """One-time offline conversion: preserve observed facts, never invent missing tables."""
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    if snapshot.get("version") not in (2, 3) or not isinstance(snapshot.get("tables"), list):
        raise ValueError("只能拆分包含约束证据的 v2/v3 结构快照")
    documents = partition_snapshot(snapshot, plugins)
    missing = missing_approved_fields(snapshot, plugins)
    # Incomplete packages need a real database sync, not a pretend empty snapshot.
    missing_owners = {resource_owners()[item.split(".", 1)[0]] for item in missing}
    complete = {owner: document for owner, document in documents.items() if owner not in missing_owners}
    publish_artifacts(output, complete)
    load_snapshot.cache_clear()
    print(f"旧快照离线拆分完成：{', '.join(complete)}。")
    if missing_owners:
        print(f"未生成不完整快照：{', '.join(sorted(missing_owners))}；请从已迁移的目标租户同步。")
    return 0


def default_schema() -> str:
    return tenant_schema_name(get_settings().default_tenant_no)


def repartition_existing(source: Path, output: Path, plugins=None) -> int:
    """Reassign existing observed facts after plugin consolidation, without DB I/O."""
    tables = {}
    for path in sorted(source.glob("*.generated.json")):
        owner = path.name.removesuffix(".generated.json")
        document = read_artifact(path, owner=owner, version=SNAPSHOT_VERSION)
        for table in document.get("tables", []):
            name = table["name"]
            if name in tables and tables[name] != table:
                raise ValueError(f"已有结构快照证据冲突，请从目标库重新同步：{name}")
            tables[name] = table
    snapshot = {"version": SNAPSHOT_VERSION, "tables": list(tables.values())}
    if missing := missing_approved_fields(snapshot, plugins):
        raise ValueError(f"已有快照缺少已批准字段，请在迁移后同步目标租户：{', '.join(missing)}")
    publish_artifacts(output, partition_snapshot(snapshot, plugins))
    load_snapshot.cache_clear()
    print("已有结构快照已按当前归属重新分片；未读取数据库，未补造结构证据。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按能力包生成或检查 Harness 结构快照")
    parser.add_argument("mode", choices=("sync", "check", "split-legacy", "repartition"))
    parser.add_argument("--schema", default=None, help="目标租户 schema；省略时使用配置的默认租户")
    parser.add_argument("--plugin", action="append", dest="plugins", help="core、已加载 shared_* 分组或插件；可重复；默认全部")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_DIR, help="输出目录")
    parser.add_argument("--source", type=Path, default=None, help="split-legacy 的旧文件，或 repartition 的已有分片目录")
    args = parser.parse_args(argv)
    try:
        if args.mode == "split-legacy":
            return split_legacy(args.source or LEGACY_PATH, args.output, args.plugins)
        if args.mode == "repartition":
            return repartition_existing(args.source or SNAPSHOT_DIR, args.output, args.plugins)
        return asyncio.run(run(args.mode, args.schema, args.output, args.plugins))
    except (OSError, asyncpg.PostgresError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        # Database driver diagnostics can include connection details.
        print(f"Harness 结构快照操作失败（{type(exc).__name__}）；请核对目标连接、归属声明与快照格式。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
