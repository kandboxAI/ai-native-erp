"""User workflows for Windows/Linux. Reuse plugin installers and fail at the first error."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[5]


class StepFailed(Exception):
    def __init__(self, code):
        self.code = code


def _run(label, arguments, *, env=None, quiet=False):
    print(f"→ {label}", flush=True)
    child_env = dict(os.environ if env is None else env)
    # Normal workflows use deployment.json, not a stale terminal profile override.
    child_env.pop("ERP_DEPLOYMENT_PROFILE", None)
    child_env.pop("DEPLOYMENT_PROFILE", None)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", *arguments], cwd=ROOT / "plugins/core/backend", env=child_env, shell=False,
        stdout=subprocess.PIPE if quiet else None, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        if quiet and result.stdout:
            print(result.stdout)
        raise StepFailed(result.returncode)


def _check(source_only=False):
    args = ["-m", "app.framework.plugin_cli", "check"]
    if not source_only:
        args.append("--require-migrations")
    _run("检查当前部署的源码、依赖和迁移", args, quiet=True)
    print("源码与依赖检查通过。" if source_only else "源码、依赖与迁移检查通过。")


def _path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _selection(keys):
    from app.framework.plugin_manifest import read_plugin_manifests, resolve_plugin_manifests
    from app.framework.plugin_suite import suite_plan
    candidates = read_plugin_manifests(ROOT)
    available = {item.key: item for item in candidates}
    closure = set()

    def visit(key):
        if key in closure:
            return
        if key not in available:
            raise ValueError(f"缺少插件源码：{key}")
        closure.add(key)
        for spec in available[key].requires:
            visit(spec.split(">=", 1)[0])

    if "core" in keys:
        if keys != ["core"]:
            raise ValueError("core 只能单独选择")
        return (), candidates
    for key in keys:
        # Validate keys via the installed-manifest map before constructing a path.
        if key not in available:
            raise ValueError(f"缺少插件源码：{key}")
        if (ROOT / "plugins" / key / "suite.toml").is_file():
            _, manifests = suite_plan(ROOT, key)
            closure.update(item.key for item in manifests)
        else:
            visit(key)
    return resolve_plugin_manifests(closure, candidates), candidates


def use_plugins(args):
    from app.framework.plugin_manifest import resolve_plugin_manifests
    from app.framework.plugin_suite import _apply
    manifests, candidates = _selection(args.keys)
    path = ROOT / "deployment.json"
    before = path.read_bytes()
    current = json.loads(before)
    if set(current) != {"format_version", "plugins"} or type(current["format_version"]) is not int or current["format_version"] != 1 \
            or not isinstance(current["plugins"], list) or any(not isinstance(key, str) for key in current["plugins"]) \
            or len(current["plugins"]) != len(set(current["plugins"])):
        raise ValueError("当前 deployment.json 格式无效")
    if args.keys == ["core"] and not args.replace:
        raise ValueError("只运行底座请明确使用 use core --replace")
    selected = {item.key for item in manifests} | (set() if args.replace else set(current["plugins"]))
    ordered = resolve_plugin_manifests(selected, candidates)
    print("部署插件：" + (", ".join(item.key for item in ordered) or "core"))
    if args.dry_run:
        print("预览完成，未修改文件；尚未执行源码检查。")
        return
    content = (json.dumps({"format_version": 1, "plugins": [item.key for item in ordered]}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _apply(ROOT, {"deployment.json": content}, {"deployment.json": before})
    try:
        _check(args.source_only)
    except BaseException:
        # Restore only our own edit. Never overwrite a concurrent user edit.
        if path.read_bytes() == content:
            _apply(ROOT, {"deployment.json": before}, {"deployment.json": content})
            print("检查未完成，已恢复原部署配置。")
        else:
            print("部署配置已被其他操作修改，未覆盖；请核对 deployment.json。")
        raise
    print("部署选择及检查完成。请重启/重新构建前后端，再为目标租户开通。")


def install(args):
    from app.framework.plugin_package import install_package
    from app.framework.plugin_suite import HEADER, install_suite
    package = _path(args.package)
    with zipfile.ZipFile(package) as archive:
        suite = HEADER in archive.namelist()
    installer = install_suite if suite else install_package
    # Complete package safety/ownership preview first, including in dry-run mode.
    report = installer(ROOT, package, deploy=True, dry_run=True, source_only=args.source_only)
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print("→ 整包与文件冲突预检通过")
    installer(ROOT, package, deploy=True, dry_run=False, source_only=args.source_only)
    try:
        _check(args.source_only)
    except BaseException:
        print("源码已导入，装配检查未完成；请修复检查错误后重试 check，暂不为租户开通。")
        raise
    print("导入、部署选择及检查完成。请重启/重新构建前后端，然后在应用管理启用或升级。")


def pack(args):
    from app.framework.plugin_package import pack_plugin, inspect_package
    from app.framework.plugin_suite import pack_suite, _read_suite_package
    manifests, _ = _selection([args.key])
    owner = next(item for item in manifests if item.key == args.key)
    suite = (ROOT / "plugins" / args.key / "suite.toml").is_file()
    if args.output:
        output = _path(args.output)
    else:
        suffix = "-source" if args.source_only else ""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        output = ROOT / "dist" / ("suites" if suite else "plugins") / f"{owner.key}-{owner.version}{suffix}-{stamp}.zip"
    report = (pack_suite if suite else pack_plugin)(ROOT, args.key, output, source_only=args.source_only)
    if suite:
        with _read_suite_package(ROOT, output):
            pass
    else:
        inspect_package(ROOT, output)
    print(f"已生成：{report['output']}")
    print("出包及包结构校验完成；不代表业务测试或目标库验收通过。")


def _target(schema=None):
    from sqlalchemy.engine import make_url
    from app.core.config import get_settings
    from app.framework.db.tenant import validate_tenant_schema
    settings = get_settings()
    url = make_url(settings.database_url)
    schema = validate_tenant_schema(schema or settings.default_tenant_schema)
    if not url.database:
        raise ValueError("数据库连接没有指定库名")
    return {"host": url.host, "port": url.port or 5432, "database": url.database, "schema": schema}


def _confirm(args, target, description):
    print(description)
    # Only target identity; never print URL, userinfo, credentials or query parameters.
    print("目标：" + json.dumps(target, ensure_ascii=False))
    if args.database is not None and args.database != target["database"]:
        raise ValueError("--database 与实际配置的目标库名不匹配；未切换数据库连接")
    if args.yes:
        if args.database != target["database"]:
            raise ValueError("非交互执行须用 --database 明确匹配目标库名")
        return
    expected = target["database"] + "/" + target["schema"]
    if not sys.stdin.isatty():
        raise ValueError("非交互终端不能确认；请明确传入 --yes --database <目标库名>")
    if input(f"输入 {expected} 确认，其他输入取消：").strip() != expected:
        raise ValueError("操作已取消，未执行数据库或模型操作")


def initialize(args):
    target = _target()
    _confirm(args, target, "初始化当前配置的默认租户：执行 public/core 迁移并开通管理员，不加载业务插件或演示数据。")
    _run("初始化底座", ["scripts/bootstrap.py", "--profile", "core", "--skip-other-tenants"])


def ai_sync(args):
    # Scope/tenant syntax is checked before any read or index/model operation.
    from app.integrations.harness_artifacts import selected_owners
    from app.framework.plugin_suite import suite_plan
    if args.suite:
        _, manifests = suite_plan(ROOT, args.suite)
        selected_owners(["core", *(item.key for item in manifests)])
    elif args.plugin:
        selected_owners(["core", *args.plugin])
    target = _target(args.schema)
    _confirm(args, target, "同步元数据：读取目标租户并写本地快照。" + ("随后调用向量模型并写入完整部署的租户检索索引。" if args.index else "不调用向量模型。"))
    command = ["-m", "app.integrations.harness_metadata_cli", "sync", "--schema", target["schema"]]
    if args.suite:
        command += ["--suite", args.suite]
    elif args.plugin:
        command += ["--plugin", "core"]
        for key in args.plugin:
            command += ["--plugin", key]
    _run("同步并校验表结构、接口快照和语义目录", command)
    if args.index:
        _run("构建并发布当前完整部署的租户索引", ["-m", "app.modules.harness_discovery.cli", "build-index", "--schema", target["schema"]])


def database_workflow(args):
    from app.framework.environment_migrations import selected_scopes

    selected_scopes(set(args.plugin) if args.plugin else None)
    target = _target(args.schema)
    _confirm(args, target, {
        "revision": "对照目标库与当前模型生成本环境迁移；只生成文件，不执行迁移。",
        "upgrade": "执行本环境已审核的迁移，再检查当前模型是否匹配；不自动生成迁移。",
        "current": "读取本环境迁移版本；不修改数据库。",
    }[args.db_command])
    arguments = ["-m", "app.framework.environment_migrations", args.db_command, "--schema", target["schema"]]
    for key in args.plugin or []:
        arguments += ["--plugin", key]
    if args.db_command == "revision":
        arguments += ["--message", args.message]
    _run("环境数据库维护", arguments)


def development_sync(args):
    from app.framework.development_sync import require_development
    from app.framework.plugin import loaded_plugin_manifests

    require_development()
    available = {item.key for item in loaded_plugin_manifests()}
    if args.plugin and set(args.plugin) - {"core", *available}:
        raise ValueError("--plugin 必须是 core 或当前部署已加载的插件 key")
    target = _target(args.schema)
    _confirm(args, target, "开发同步：补齐底座和已启用插件的权限、菜单及必需配置；不执行迁移，不修改插件版本或启停状态。")
    arguments = ["-m", "app.framework.development_sync", "--schema", target["schema"]]
    for key in args.plugin or []:
        arguments += ["--plugin", key]
    _run("同步开发租户配置", arguments)


def _confirmation_options(parser):
    parser.add_argument("--yes", action="store_true", help="非交互确认；须同时提供匹配的 --database")
    parser.add_argument("--database", help="非交互确认的实际数据库名；不是切换连接")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python scripts/erp.py", description="在仓库根目录运行的 Windows/Linux 统一入口")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-pages", help="离线检查通用页面与接口的绑定，列出未绑定项")
    item = commands.add_parser("relocate", help="将已有插件源码移入自身目录；不迁移数据库")
    item.add_argument("plugin")
    item.add_argument("--dry-run", action="store_true")
    use = commands.add_parser("use", help="选择插件/套件，自动补齐依赖并检查；不操作数据库")
    use.add_argument("keys", nargs="+", help="插件或套件 key，可同时给多个；core 表示纯底座")
    use.add_argument("--replace", action="store_true", help="用所选组合替换部署；默认合并保留原组合")
    use.add_argument("--dry-run", action="store_true")
    use.add_argument("--source-only", action="store_true", help="仅检查待开发源码，允许缺迁移")
    item = commands.add_parser("install", help="自动识别套件/插件 ZIP，预检、导入、选入部署并检查")
    item.add_argument("package", help="ZIP 路径；相对路径以仓库根目录为准")
    item.add_argument("--dry-run", action="store_true")
    item.add_argument("--source-only", action="store_true")
    item = commands.add_parser("pack", help="自动识别套件/插件，打包并校验成品；默认时间戳文件名")
    item.add_argument("key")
    item.add_argument("--output", help="输出路径；相对路径以仓库根目录为准")
    item.add_argument("--source-only", action="store_true")
    item = commands.add_parser("check", help="离线检查当前部署；不访问数据库")
    item.add_argument("--source-only", action="store_true")
    item = commands.add_parser("init", help="确认目标后初始化默认租户的纯底座")
    _confirmation_options(item)
    item = commands.add_parser("serve", help="启动后端；不会自动初始化或升级数据库")
    item.add_argument("--host", default="127.0.0.1")
    item.add_argument("--port", type=int, default=8000)
    item.add_argument("--reload", action="store_true")
    db = commands.add_parser("db", help="以当前模型维护各自数据库；增量仅保存在本环境")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    for action in ("revision", "upgrade", "current"):
        item = db_commands.add_parser(action)
        item.add_argument("--schema", required=True)
        item.add_argument("--plugin", action="append", help="core、public 或业务插件；默认当前部署，自动带依赖")
        if action == "revision":
            item.add_argument("--message", default="sync current models")
        _confirmation_options(item)
    dev = commands.add_parser("dev", help="本地开发辅助；无需打包或递增版本")
    dev_commands = dev.add_subparsers(dest="dev_command", required=True)
    item = dev_commands.add_parser("sync", help="补齐已启用插件配置；不迁移、不修改版本或启停状态")
    item.add_argument("--schema", required=True)
    item.add_argument("--plugin", action="append", help="限定已启用插件及依赖；默认底座和租户所有已启用插件")
    _confirmation_options(item)
    ai = commands.add_parser("ai", help="Harness 元数据和检索索引维护")
    ai_commands = ai.add_subparsers(dest="ai_command", required=True)
    ai_commands.add_parser("check", help="离线检查当前部署 AI 元数据")
    item = ai_commands.add_parser("sync", help="一次同步快照，可选构建索引；会先确认目标库")
    item.add_argument("--schema", required=True)
    scope = item.add_mutually_exclusive_group()
    scope.add_argument("--suite")
    scope.add_argument("--plugin", action="append")
    item.add_argument("--index", action="store_true", help="同步后构建完整部署索引；调用模型并写数据库")
    _confirmation_options(item)
    args = parser.parse_args(argv)
    os.environ.pop("ERP_DEPLOYMENT_PROFILE", None)
    os.environ.pop("DEPLOYMENT_PROFILE", None)
    try:
        if args.command == "relocate":
            command = ["-m", "app.framework.plugin_cli", "relocate", "--plugin", args.plugin]
            if args.dry_run:
                command.append("--dry-run")
            _run("整理插件独立源码目录", command)
        elif args.command == "check-pages":
            _run("检查当前部署页面的后端能力契约", ["-m", "app.framework.plugin_cli", "check-pages"])
        elif args.command == "use":
            use_plugins(args)
        elif args.command == "install":
            install(args)
        elif args.command == "pack":
            pack(args)
        elif args.command == "check":
            _check(args.source_only)
        elif args.command == "init":
            initialize(args)
        elif args.command == "serve":
            command = ["-m", "uvicorn", "app.main:app", "--host", args.host, "--port", str(args.port)]
            if args.reload:
                from app.framework.plugin import loaded_plugin_manifests
                command.extend(["--reload", "--reload-dir", str(ROOT / "plugins/core/backend/app")])
                for manifest in loaded_plugin_manifests():
                    if manifest.source_layout == "contained":
                        command.extend(["--reload-dir", str(ROOT / "plugins" / manifest.key / "backend")])
            _run("启动后端", command)
        elif args.command == "db":
            database_workflow(args)
        elif args.command == "dev":
            development_sync(args)
        elif args.ai_command == "check":
            _run("离线检查 AI 元数据", ["-m", "app.integrations.harness_metadata_cli", "check"])
        else:
            ai_sync(args)
        return 0
    except StepFailed as exc:
        print("流程已停止，未执行后续步骤。", file=sys.stderr)
        return exc.code if exc.code > 0 else 1
    except (KeyboardInterrupt, EOFError):
        print("操作已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        # Validation errors may embed env input, including credentials.
        if type(exc) is ValueError:
            print(str(exc), file=sys.stderr)
        else:
            print(f"操作失败（{type(exc).__name__}）；请检查参数、配置或包文件。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
