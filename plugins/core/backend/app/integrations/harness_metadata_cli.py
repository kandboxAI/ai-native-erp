"""Unified metadata maintenance, separate from migrations and vector model calls."""
from __future__ import annotations

import argparse
import asyncio

from . import harness_catalog_cli as schema_cli, harness_http_cli as http_cli
from .harness_artifacts import selected_owners
from .harness_schema_catalog import load_snapshot, snapshot_errors


def check_metadata(plugins=None) -> int:
    """Offline check: completeness, contracts, semantics, fields, relations and metrics."""
    errors = snapshot_errors(plugins=plugins)
    for error in errors:
        print(error)
    http_code = http_cli.run("check", plugins=plugins)
    # Validate semantic source even if artifacts are incomplete; do not mask defects.
    from .erp_discovery.catalog import compile_catalog
    documents = compile_catalog()
    print(f"资源、语义与查询目录已校验：{len(documents)} 条定义。")
    return 1 if errors or http_code else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="统一同步/检查 AI 元数据；不迁移数据库、不调用向量模型")
    parser.add_argument("command", choices=("sync", "check"))
    parser.add_argument("--schema", help="目标租户；sync 必须指定，check 省略时只做离线检查")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--plugin", action="append", dest="plugins", help="core、已加载 shared_* 分组或插件；可重复；默认全部")
    selection.add_argument("--suite", help="统一处理套件及全部依赖与 core；须已选入 deployment")
    args = parser.parse_args(argv)
    try:
        if args.suite:
            from app.framework.plugin_suite import ROOT, suite_plan
            _, manifests = suite_plan(ROOT, args.suite)
            args.plugins = ["core", *(item.key for item in manifests)]
        selected_owners(args.plugins)
        if args.command == "sync" and not args.schema:
            print("sync 必须通过 --schema 明确目标租户；请先核对数据库连接。")
            return 1
        if args.schema:
            code = asyncio.run(schema_cli.run(args.command, args.schema, plugins=args.plugins))
            if code:
                return code
        if args.command == "sync" and http_cli.run("sync", plugins=args.plugins):
            return 1
        load_snapshot.cache_clear()
        return check_metadata(args.plugins)
    except Exception as error:
        print(f"AI 元数据维护失败（{type(error).__name__}）；请核对归属声明、语义及生成文件。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
