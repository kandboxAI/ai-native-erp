"""离线导入：默认预览。必须显式指定目标库名、租户与组织才可写入。"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.engine import make_url
from app.core.config import get_settings
from app.framework.db.tenant import use_tenant_schema
from app.framework.db.session import startup_sqlmodel_database, shutdown_sqlmodel_database
from .import_service import import_workbook


async def run(args):
    settings = get_settings()
    database = make_url(settings.database_url).database
    if args.database != database:
        raise ValueError("--database 与当前连接的实际数据库不匹配")
    print(json.dumps({"database": database, "schema": args.schema, "org_id": str(args.org_id), "apply": args.apply}), flush=True)
    if args.apply:
        await startup_sqlmodel_database()
    try:
        with use_tenant_schema(args.schema):
            result = await import_workbook(args.source, args.org_id, apply=args.apply)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False), flush=True)
    finally:
        if args.apply:
            await shutdown_sqlmodel_database()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--org-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
