"""建库与种子数据。

步骤：
1. 升级 public（登录认证表与租户目录）；
2. 开通或补齐默认租户（t_<DEFAULT_TENANT_NO>，默认 t_default）：建 schema、升级到最新、内置字典、权限、菜单、内置管理员；
3. 升级其他已登记的租户，并补齐字典、权限、菜单；
4. --with-demo：为默认租户加载各模块的演示数据（app/modules/<模块>/demo_seed.py 中的 seed_demo）。

可以重复执行。

已经完成过建库、仅需补齐目录和模块开通数据时，可使用 ``--skip-upgrade``。
该参数不会执行 Alembic，也不会修改迁移版本表，不能用于空数据库或需要结构升级的环境。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

DEV_ADMIN_PASSWORD = "Admin@123456"  # 仅开发环境：README 中的本地管理员密码


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="升级数据库结构并开通默认租户（幂等）")
    parser.add_argument(
        "--with-demo",
        action="store_true",
        help="为默认租户加载演示组织、业务数据和固定密码账号；禁止在生产环境使用",
    )
    parser.add_argument("--skip-seed", action="store_true", help="只升级 public 与已登记租户的结构，不生成数据")
    parser.add_argument(
        "--skip-upgrade",
        action="store_true",
        help="跳过 public/tenant Alembic，仅同步已初始化数据库的目录与模块开通数据",
    )
    parser.add_argument(
        "--modules",
        default=None,
        help="只运行这些能力包 key 或 app/modules 目录名的开通步骤与演示数据（逗号分隔）；能力包会带上依赖，开发调试用，如 sample_app 或 system",
    )
    parser.add_argument(
        "--profile",
        choices=("core", "custom"),
        default=None,
        help="core 仅底座；custom 按 deployment.json 加载；默认读取 deployment.json",
    )
    parser.add_argument("--skip-other-tenants", action="store_true", help="只处理默认租户，不升级其他已登记的租户")
    args = parser.parse_args()
    if args.skip_seed and args.skip_upgrade:
        parser.error("--skip-seed 与 --skip-upgrade 不能同时使用")
    return args


def _admin_password(settings) -> str:
    if settings.init_admin_password:
        return settings.init_admin_password
    if settings.app_env == "production":
        raise RuntimeError("生产环境请通过 INIT_ADMIN_PASSWORD 配置默认租户管理员的初始密码")
    return DEV_ADMIN_PASSWORD


async def _run(args: argparse.Namespace) -> None:
    from app.core.config import get_settings
    from app.db.connection import shutdown_database, startup_database
    from app.framework.catalog import iter_module_attr
    from app.framework.plugin import expand_module_selection
    from app.framework.db.session import get_session_context, shutdown_sqlmodel_database, startup_sqlmodel_database
    from app.framework.db.tenant import use_tenant_schema
    from app.integrations.redis_client import shutdown_redis, startup_redis
    from app.modules.system.tenant_template import (
        TenantSpec,
        list_tenants,
        provision_tenant,
        sync_existing_tenant,
        upgrade_public_schema,
        upgrade_tenant_schema,
    )

    settings = get_settings()
    if args.skip_upgrade:
        print("skipping public/tenant Alembic upgrades (existing initialized database only)")
    else:
        print("upgrading public")
        upgrade_public_schema()

    await startup_database()
    await startup_sqlmodel_database()
    await startup_redis()
    try:
        if args.skip_seed:
            for tenant in await list_tenants(active_only=False):
                print(f"upgrading {tenant.schema_name}")
                upgrade_tenant_schema(tenant.schema_name)
            return

        spec = TenantSpec(
            tenant_no=settings.default_tenant_no,
            tenant_name=settings.default_tenant_name,
            org_no=settings.default_tenant_no,
            org_name=settings.default_tenant_name,
            admin_email=settings.init_admin_email,
            admin_password=_admin_password(settings),
        )
        modules = expand_module_selection({item.strip() for item in args.modules.split(",") if item.strip()}) if args.modules else None
        print(f"provisioning {settings.default_tenant_schema}")
        ctx = await provision_tenant(
            spec,
            upgrade_schema=not args.skip_upgrade,
            modules=modules,
        )

        for tenant in [] if args.skip_other_tenants else await list_tenants():
            if tenant.id == ctx.tenant.id:
                continue
            print(f"upgrading {tenant.schema_name}")
            await sync_existing_tenant(tenant, upgrade_schema=not args.skip_upgrade)

        if args.with_demo:
            with use_tenant_schema(ctx.schema):
                # 各模块用 DEMO_ORDER 声明先后（组织、人员在前，业务在后）
                for module in sorted(iter_module_attr("demo_seed", modules), key=lambda item: getattr(item, "DEMO_ORDER", 100)):
                    seed = getattr(module, "seed_demo", None)
                    if seed is None:
                        continue
                    print(f"seeding demo: {module.__name__}")
                    async with get_session_context() as session:
                        await seed(session, ctx)
                        await session.commit()
    finally:
        await shutdown_redis()
        await shutdown_sqlmodel_database()
        await shutdown_database()


def main() -> None:
    args = parse_args()
    if args.profile:
        os.environ["ERP_DEPLOYMENT_PROFILE"] = args.profile
    os.chdir(BACKEND_DIR)
    asyncio.run(_run(args))
    print("bootstrap complete")


if __name__ == "__main__":
    main()
