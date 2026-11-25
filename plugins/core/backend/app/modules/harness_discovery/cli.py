"""Explicit deployment catalog index maintenance; never invoked by startup or Alembic."""
import argparse
import asyncio
import json

from app.core.config import get_settings
from app.framework.db.session import startup_sqlmodel_database, shutdown_sqlmodel_database
from app.framework.db.tenant import use_tenant_schema, validate_tenant_schema
from sqlalchemy.exc import DBAPIError
from app.integrations.erp_discovery.adapter import ErpDiscoveryAdapter
from resource_discovery.catalog import normalize_catalog
from resource_discovery.indexing import build_index
from resource_discovery.providers import EmbeddingClient

from .repository import IndexSchemaError, create_store
from .service import discovery_settings


async def run(command: str, schema: str | None = None) -> None:
    settings = discovery_settings(get_settings())
    adapter = ErpDiscoveryAdapter()
    if command in ("check", "build-index"):
        from app.integrations.harness_metadata_cli import check_metadata
        if check_metadata():
            raise ValueError("AI 元数据尚未同步或校验未通过，未发布索引")
    if command == "check":
        print(f"Approved catalog valid: {len(normalize_catalog(adapter.compile_catalog()))} definitions; namespace={adapter.namespace}")
        return
    if not schema:
        raise ValueError("索引操作必须通过 --schema 指定目标租户")
    schema = validate_tenant_schema(schema)
    with use_tenant_schema(schema):
        store = create_store()
        print(f"目标租户：{schema}；namespace={adapter.namespace}")
        await startup_sqlmodel_database()
        try:
            # Validate the real tenant tables before spending any embedding requests.
            await store.initialize()
            if command == "init":
                print("租户索引表结构校验通过；未创建或修改数据库对象。")
            elif command == "status":
                print(json.dumps(await store.index_status(), ensure_ascii=False, default=str))
            else:
                revision = await build_index(adapter, settings, store, EmbeddingClient(settings))
                print(f"Published metadata to pgvector; tenant={schema}; namespace={adapter.namespace}; revision={revision}")
        finally:
            await shutdown_sqlmodel_database()


def failure_message(error):
    if isinstance(error, IndexSchemaError):
        return str(error)
    if isinstance(error, DBAPIError):
        original = error.orig
        state = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
        hints = {"42P01": "目标租户缺少索引表，请检查该租户迁移", "42703": "索引字段与迁移不一致",
                 "42501": "数据库账号缺少索引表或 schema 的访问权限", "42704": "缺少 pgvector 类型或扩展",
                 "42883": "缺少向量操作符或函数，请检查 pgvector 扩展与 search_path"}
        return f"数据库索引操作失败（{type(error).__name__}，SQLSTATE={state or 'unknown'}）：{hints.get(state, '请核对连接、租户迁移和索引表结构')}。"
    return f"索引命令失败（{type(error).__name__}）；请核对 --schema、元数据检查结果及 embedding 配置。"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independent approved Harness discovery index command")
    parser.add_argument("command", choices=("check", "init", "build-index", "status"))
    parser.add_argument("--schema", help="init/build-index/status 必须指定目标租户 schema；check 不访问数据库")
    args = parser.parse_args(argv)
    if args.command != "check" and not args.schema:
        print("请用 --schema t_<实际租户编号> 指定目标租户；索引存放在该租户的 ai_resource_* 表中。")
        return 1
    try:
        asyncio.run(run(args.command, args.schema))
    except Exception as error:
        print(failure_message(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
