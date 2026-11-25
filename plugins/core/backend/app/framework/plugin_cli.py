"""New-plugin scaffolding, offline checks and explicitly invoked scoped migrations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from app.framework.plugin_sources import plugin_source_path

ROOT = Path(__file__).resolve().parents[5]


def check_plugins(*, require_migrations=False) -> dict:
    from alembic.script import ScriptDirectory
    from app.framework.plugin_migrations import require_core_manifests, table_owners, check_plugin_models, plugin_migration_config
    from app.framework.catalog import collect_catalog
    from app.modules.dictionary.builtin_dicts import builtin_dict_specs
    from app.framework.plugin_manifest import read_frontend_manifest, PLUGIN_DIR, migration_locations

    manifests = require_core_manifests()
    from app.framework.plugin_suite import deployed_suites
    deployed_suites()
    for item in manifests:
        for module in item.module_names:
            if not plugin_source_path(ROOT, item, f"backend/app/modules/{module}/__init__.py").is_file():
                raise ValueError(f"{item.key}: 缺少模块 {module}/__init__.py")
        if not item.migration_location or not (ROOT / "plugins/core/backend" / item.migration_location).is_dir():
            raise ValueError(f"{item.key}: 缺少独立迁移目录")
        for location in migration_locations(item):
            if not (ROOT / "plugins/core/backend" / location).is_dir():
                raise ValueError(f"{item.key}: 缺少保留的迁移目录 {location}")
    owners = table_owners(manifests)
    check_plugin_models(manifests, owners)
    catalog = collect_catalog()
    from app.framework.page_contracts import check_page_contracts
    page_contracts = check_page_contracts(catalog.menus)
    dictionaries = {spec["dict_code"]: spec for spec in builtin_dict_specs()}
    module_codes = {code for code, name in dictionaries["sys_module"]["items"]}
    permissions = {item.key: item for item in catalog.permissions}
    core_frontend = json.loads((ROOT / "plugins/core/backend/app/framework/core_manifest.json").read_text(encoding="utf-8"))
    view_owners = {root: "core" for root in core_frontend["web_view_roots"]}
    workflow_owners = {}
    from app.framework.plugin import iter_plugin_routers
    list(iter_plugin_routers())
    _check_menu_ownership(manifests, catalog.menus, permissions)
    for item in manifests:
        if not set(item.module_codes) <= module_codes:
            raise ValueError(f"{item.key}: 请在 dictionary_specs.py 向 sys_module 登记模块编码")
        for module_name in item.module_names:
            from importlib import import_module
            try:
                module = import_module(f"app.modules.{module_name}.catalog")
            except ModuleNotFoundError as exc:
                if exc.name == f"app.modules.{module_name}.catalog":
                    continue
                raise
            for permission in getattr(module, "PERMISSIONS", []):
                if permission.module_code not in item.module_codes:
                    raise ValueError(f"{item.key}: 权限模块编码未归属于本插件：{permission.key}")
            for menu in getattr(module, "MENUS", []):
                if menu.key not in item.menu_keys or menu.key not in {row.key for row in catalog.menus}:
                    raise ValueError(f"{item.key}: 菜单声明、权限或父菜单引用不完整：{menu.key}")
            for menu in getattr(module, "MINIAPP_MENUS", []):
                if menu.menu_key not in item.miniapp_menu_keys:
                    raise ValueError(f"{item.key}: 小程序菜单未声明归属：{menu.menu_key}")
        if item.frontend_manifest:
            frontend = read_frontend_manifest(PLUGIN_DIR / item.key / item.frontend_manifest)
            for business_type, route_name in frontend.get("workflow_routes", {}).items():
                if business_type in workflow_owners or route_name not in item.menu_keys:
                    raise ValueError(f"{item.key}: 审批跳转重复或未指向本插件菜单：{business_type}")
                workflow_owners[business_type] = item.key
            for view in frontend["web_view_roots"]:
                if view in view_owners:
                    raise ValueError(f"管理端页面目录归属重复：{view} ({view_owners[view]}, {item.key})")
                view_owners[view] = item.key
                if not plugin_source_path(ROOT, item, f"web/src/views/{view}").is_dir():
                    raise ValueError(f"{item.key}: 管理端页面目录不存在：{view}")
            for menu in catalog.menus:
                if menu.key not in item.menu_keys or not menu.component:
                    continue
                component = menu.component.removeprefix("/").removesuffix(".vue")
                if component.split("/")[0] not in frontend["web_view_roots"] or not any(plugin_source_path(ROOT, item, path).is_file() for path in (f"web/src/views/{component}.vue", f"web/src/views/{component}/index.vue")):
                    raise ValueError(f"{item.key}: 菜单组件不存在或不属于本插件：{component}")
            pages = json.loads((ROOT / "plugins/core/miniprogram/src/pages.json").read_text(encoding="utf-8"))
            from app.framework.plugin_manifest import miniapp_registrations
            registered = set(miniapp_registrations(pages))
            for page in frontend["miniapp_pages"]:
                if page not in registered or not plugin_source_path(ROOT, item, f"miniprogram/src/{page}.vue").is_file():
                    raise ValueError(f"{item.key}: 请创建小程序页面并登记到 plugins/core/miniprogram/src/pages.json：{page}")
    script = ScriptDirectory.from_config(plugin_migration_config("t_plugin_check", include_local_legacy=False))
    plugin_heads = {}
    for item in manifests:
        for key in getattr(item, "replaces", ()):
            script.get_revision(f"{key}@head")
        revisions = [revision for revision in script.walk_revisions() if item.key in revision.branch_labels]
        if not revisions:
            if require_migrations:
                raise ValueError(f"{item.key}: 尚无迁移；请先执行 revision 并审核，再执行 check --require-migrations")
            plugin_heads[item.key] = None
            continue
        head = script.get_revision(f"{item.key}@head")
        ancestors = {revision.revision for revision in script.iterate_revisions(head.revision, "base")}
        if "core_0001" not in ancestors:
            raise ValueError(f"{item.key}: 迁移分支未依赖 core_0001")
        plugin_heads[item.key] = head.revision
    return {"migration_base": "core", "plugins": [item.key for item in manifests], "plugin_heads": plugin_heads, "table_owners": owners, "permissions": len(permissions), "menus": len(catalog.menus), "page_contracts": page_contracts}


def _check_menu_ownership(manifests, menus, permissions):
    """Composite pages own their menus and may use a declared dependency's permission."""
    owners = {key: item for item in manifests for key in item.menu_keys}
    permission_owners = {code: item for item in manifests for code in item.module_codes}
    for menu in menus:
        permission = permissions.get(menu.permission_key)
        permission_owner = permission_owners.get(permission.module_code) if permission else None
        owner = owners.get(menu.key)
        if owner is None:
            if permission_owner:
                raise ValueError(f"{permission_owner.key}: 管理端菜单未声明归属：{menu.key}")
            continue
        allowed = {owner.key, *(spec.split('>=', 1)[0] for spec in owner.requires)}
        if permission_owner and permission_owner.key not in allowed:
            raise ValueError(f"{owner.key}: 菜单 {menu.key} 使用未声明依赖 {permission_owner.key} 的权限")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    relocate = commands.add_parser("relocate", help="将已有插件源码迁入自身目录；不操作数据库或修改迁移")
    relocate.add_argument("--plugin", required=True)
    relocate.add_argument("--dry-run", action="store_true")
    suite = commands.add_parser("suite", help="一次规划、选择部署、打包或导入整个业务套件；不访问数据库")
    suite_commands = suite.add_subparsers(dest="suite_command", required=True)
    for action in ("plan", "deploy", "pack"):
        item = suite_commands.add_parser(action)
        item.add_argument("--suite", required=True)
        if action == "deploy":
            item.add_argument("--dry-run", action="store_true")
        if action == "pack":
            item.add_argument("--output", type=Path, required=True)
            item.add_argument("--source-only", action="store_true")
    suite_install = suite_commands.add_parser("install")
    suite_install.add_argument("package", type=Path)
    suite_install.add_argument("--deploy", action="store_true")
    suite_install.add_argument("--dry-run", action="store_true")
    suite_install.add_argument("--source-only", action="store_true")
    scaffold = commands.add_parser("scaffold", help="生成未安装的空插件，不修改 deployment.json")
    scaffold.add_argument("--key", required=True)
    scaffold.add_argument("--name", required=True)
    scaffold.add_argument("--layer", choices=("L2", "L3"), default="L3")
    scaffold.add_argument("--requires", action="append", default=[])
    check = commands.add_parser("check", help="离线校验清单、模块、模型、目录及迁移树")
    check.add_argument("--require-migrations", action="store_true")
    commands.add_parser("check-pages", help="仅离线检查页面与当前接口的绑定，列出未绑定项；不判定业务实现状态")
    revision = commands.add_parser("revision", help="默认生成本环境增量；初始基线须显式 --from-models 或 --baseline")
    revision.add_argument("--plugin", required=True, help="core 或当前部署加载的插件 key")
    revision.add_argument("--schema", required=True)
    revision.add_argument("--message", required=True)
    revision_mode = revision.add_mutually_exclusive_group()
    revision_mode.add_argument("--autogenerate", action="store_true")
    revision_mode.add_argument("--from-models", action="store_true", help="离线从本插件模型生成新分支初始迁移；不读取数据库，仅用于全新插件")
    revision_mode.add_argument("--baseline", action="store_true", help="仅为没有业务表的新插件离线生成固定空基线")
    upgrade = commands.add_parser("upgrade", help="用户显式升级指定租户的插件分支，不启用插件")
    upgrade.add_argument("--plugin", required=True, help="core 或当前部署加载的插件 key")
    upgrade.add_argument("--schema", required=True)
    upgrade.add_argument("--legacy-history", action="store_true", help="仅兼容维护旧共享版本链；日常使用 db revision / db upgrade")
    pack = commands.add_parser("pack", help="打包已适配的业务源码，不访问数据库")
    pack.add_argument("--plugin", required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--source-only", action="store_true", help="允许导出尚无迁移的待开发源码包")
    inspect = commands.add_parser("inspect-package", help="只检查源码包、哈希和归属，不执行包内代码")
    inspect.add_argument("package", type=Path)
    install = commands.add_parser("install", help="导入源码和页面登记；不执行迁移或租户启用")
    install.add_argument("package", type=Path)
    install.add_argument("--deploy", action="store_true", help="同时选入 deployment.json 并补入已安装的依赖")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--source-only", action="store_true", help="仅导入待开发源码包，不代表可以开通租户")
    convert = commands.add_parser("convert", help="在隔离目录自动收集旧业务、转换清单、整理依赖、检查并出包；不改当前部署或数据库")
    convert.add_argument("--plugin", required=True)
    convert.add_argument("--source", type=Path, required=True, help="包含 plugins/<key>/plugin.toml 的旧仓库或备份根目录")
    convert.add_argument("--output", type=Path, help="ZIP 输出路径；默认 dist/plugins/<key>-<version>[-source].zip")
    convert.add_argument("--dry-run", action="store_true", help="只在隔离底座计算转换计划，不复制业务、不执行业务代码")
    convert.add_argument("--generate-initial", action="store_true", help="显式授权离线生成新插件初始迁移；不连接或升级数据库")
    args = parser.parse_args(argv)
    try:
        if args.command == "relocate":
            from app.framework.plugin_relocation import relocate_plugin
            print(json.dumps(relocate_plugin(ROOT, args.plugin, dry_run=args.dry_run), ensure_ascii=False, indent=2))
            return 0
        if args.command == "check-pages":
            from app.framework.catalog import collect_catalog
            from app.framework.page_contracts import check_page_contracts
            print(json.dumps(check_page_contracts(collect_catalog().menus), ensure_ascii=False, indent=2))
            return 0
        if args.command == "suite":
            from app.framework.plugin_suite import plan_report, deploy_suite, pack_suite, install_suite
            if args.suite_command == "plan":
                result = plan_report(ROOT, args.suite)
            elif args.suite_command == "deploy":
                result = deploy_suite(ROOT, args.suite, dry_run=args.dry_run)
            elif args.suite_command == "pack":
                result = pack_suite(ROOT, args.suite, args.output, source_only=args.source_only)
            else:
                result = install_suite(ROOT, args.package, deploy=args.deploy, dry_run=args.dry_run, source_only=args.source_only)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "convert":
            from app.framework.plugin_conversion import convert_plugin
            result = convert_plugin(ROOT, args.source, args.plugin, output=args.output, dry_run=args.dry_run, generate_initial=args.generate_initial)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["status"] in {"needs_code_changes", "needs_review"} else 0
        if args.command in {"pack", "inspect-package", "install"}:
            from app.framework.plugin_package import pack_plugin, inspect_package, install_package
            if args.command == "pack":
                result = pack_plugin(ROOT, args.plugin, args.output, source_only=args.source_only)
            elif args.command == "inspect-package":
                result = inspect_package(ROOT, args.package)
            else:
                result = install_package(ROOT, args.package, deploy=args.deploy, dry_run=args.dry_run, source_only=args.source_only)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "scaffold":
            from app.framework.plugin_scaffold import scaffold_plugin
            paths = scaffold_plugin(ROOT, args.key, args.name, args.layer, args.requires)
            print(f"已生成 {len(paths)} 个文件；未选入部署、未生成迁移、未访问数据库。")
            return 0
        # New model differences are local to the target database. --from-models
        # remains the explicit offline command for a distributable first baseline.
        if args.command == "revision" and not args.from_models and not args.baseline:
            from alembic import command
            from app.framework.environment_migrations import (
                selected_scopes, environment_config, generate_environment_revision, mark_environment,
            )
            selected_scopes({args.plugin})
            if args.autogenerate:
                result = generate_environment_revision(args.schema, args.plugin, args.message)
            else:
                config = environment_config("public" if args.plugin == "public" else args.schema, args.plugin)
                from app.framework.plugin_migrations import revision_options
                result = command.revision(config, message=args.message, **revision_options(config, args.plugin))
                mark_environment(config)
            print(f"本环境迁移：{result.path}；请审核后执行升级。" if result else "模型与目标库一致，无需生成迁移。")
            return 0
        if args.command == "upgrade" and not args.legacy_history:
            from app.framework.environment_migrations import run_workflow
            run_workflow("upgrade", args.schema, {args.plugin}, "")
            print("本环境结构检查通过；请继续在管理端升级或开通租户插件。")
            return 0
        report = check_plugins(require_migrations=args.command == "upgrade" or getattr(args, "require_migrations", False))
        if args.command == "check":
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        from alembic import command
        from app.framework.plugin_migrations import plugin_migration_config, revision_options
        config = plugin_migration_config(args.schema, args.plugin if args.command == "revision" else None,
                                         include_local_legacy=args.command != "revision")
        if args.plugin != "core" and args.plugin not in report["plugins"]:
            raise ValueError(f"当前部署未加载插件：{args.plugin}")
        print(f"目标租户：{args.schema}；插件：{args.plugin}；数据库连接由 backend/.env 或环境变量指定。")
        if args.command == "revision":
            if args.from_models:
                from app.framework.plugin_migrations import generate_initial_model_revision
                generated = generate_initial_model_revision(config, args.plugin, args.message)
                print(f"离线初始迁移：{generated.path}；仅生成文件，未读取或升级数据库。")
            else:
                options = revision_options(config, args.plugin)
                if options["head"] != "base" or args.plugin in report["table_owners"].values():
                    raise ValueError("--baseline 仅用于无业务表且尚无分支的新插件；有模型请使用 --from-models")
                command.revision(config, message=args.message, **options)
            print("迁移已生成，请审核归属、外键、约束和降级顺序；尚未执行升级。")
        else:
            from app.framework.plugin_migrations import tenant_upgrade_targets
            for target in tenant_upgrade_targets(set() if args.plugin == "core" else {args.plugin}):
                command.upgrade(config, target)
            print("指定分支及依赖已升级；未写入租户插件启用状态，请继续在管理端开通。")
        return 0
    except Exception as exc:
        print(f"插件命令失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
