"""开发环境补齐租户配置；不执行迁移，不写插件版本或启停记录。"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re
import traceback

from app.auth.plugin_repository import repository
from app.core.config import get_settings
from app.framework.catalog import iter_module_attr, use_module_selection
from app.framework.db.session import get_session_context, startup_sqlmodel_database, shutdown_sqlmodel_database
from app.framework.db.tenant import use_tenant_schema, validate_tenant_schema
from app.framework.deployment import CORE_MODULES, effective_plugin_keys
from app.framework.plugin import loaded_plugin_manifests
from app.framework.tenant_plugins import _tenant_operation
from app.modules.system.development_repository import has_initialized_admin
from app.modules.system.tenant_template import sync_existing_tenant


def require_development() -> None:
    if get_settings().app_env.strip().lower() != "development":
        raise ValueError("dev sync 仅用于 APP_ENV=development；正式环境请按版本启用或升级插件")


def selected_modules(manifests, active: set[str], requested: set[str] | None = None):
    available = {item.key: item for item in manifests}
    if requested is not None and (missing := requested - {"core", *available}):
        raise ValueError(f"当前部署未加载插件：{', '.join(sorted(missing))}")
    selected = set(active) if requested is None else requested - {"core"}
    pending = list(selected)
    while pending:
        key = pending.pop()
        for spec in available[key].requires:
            dependency = spec.split(">=", 1)[0]
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    if missing := selected - active:
        raise ValueError(f"请先在应用管理完成插件的安装启用：{', '.join(sorted(missing))}；开发同步不会开通插件")
    keys = [item.key for item in manifests if item.key in selected]
    modules = set(CORE_MODULES)
    for key in keys:
        modules.update(available[key].module_names)
    return keys, modules


def check_models(schema: str, keys: list[str]) -> None:
    """只比较结构；在写配置前发现缺表/缺列，不生成或执行迁移。"""
    from app.framework.environment_migrations import environment_config
    from app.framework.plugin_migrations import generate_scoped_revision

    for scope in ("public", "core", *keys):
        config = environment_config("public" if scope == "public" else schema, scope)
        config.attributes["check_model_only"] = True
        if generate_scoped_revision(config, scope, "development sync model check"):
            raise ValueError(f"{scope} 的数据库与当前模型不一致，请先执行 db revision、审核并 db upgrade，再 dev sync")


def check_setup_imports(modules: set[str]) -> None:
    """在写配置前加载并校验开通声明，拒绝导入错误及重复定义。"""
    from app.modules.notification_center.tenant_setup import builtin_scene_specs
    from app.modules.workflow.design_models import default_designs

    with use_module_selection(modules):
        for attribute in ("tenant_setup", "notification_scenes", "workflow_defaults"):
            list(iter_module_attr(attribute, modules))
        builtin_scene_specs()
        default_designs(modules)


async def sync_development(schema: str, requested: set[str] | None = None) -> list[str]:
    require_development()
    schema = validate_tenant_schema(schema)
    manifests = loaded_plugin_manifests()
    # 在打开连接前拒绝拼错或部署外的插件。
    if requested is not None and requested - {"core", *(m.key for m in manifests)}:
        raise ValueError("--plugin 必须是 core 或当前部署已加载的插件 key")
    try:
        await startup_sqlmodel_database()
        async with get_session_context() as session:
            tenant = await repository.get_tenant_by_schema(session, schema)
        if tenant is None or not tenant.is_active:
            raise ValueError("目标租户不存在或已停用；新库请先 init")
        async with _tenant_operation(tenant.id):
            async with get_session_context() as session:
                active = effective_plugin_keys(await repository.active_keys(session, tenant.id))
            keys, modules = selected_modules(manifests, active, requested)
            check_setup_imports(modules)
            with use_tenant_schema(schema):
                async with get_session_context() as session:
                    if not await has_initialized_admin(session):
                        raise ValueError("目标租户缺少已初始化的根组织或内置管理员；请先完成底座初始化")
            await asyncio.to_thread(check_models, schema, keys)
            with use_module_selection(modules):
                context = await sync_existing_tenant(
                    tenant, upgrade_schema=False, modules=modules, mark_plugins_ready=False,
                    retire_missing_dict_items=False,
                )
            if context is None:
                raise ValueError("目标租户的根组织或管理员不可用，配置同步未完成")
            return keys
    finally:
        await shutdown_sqlmodel_database()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--plugin", action="append", help="仅同步指定已启用插件及依赖；默认底座和租户所有已启用插件")
    args = parser.parse_args(argv)
    try:
        keys = asyncio.run(sync_development(args.schema, set(args.plugin) if args.plugin else None))
    except Exception as exc:
        if type(exc) is ValueError:
            print(str(exc))
        else:
            print(f"开发同步失败（{type(exc).__name__}）；请检查数据库结构及模块配置；已完成的配置可能已保留，修复后可重试。")
            # 只输出可定位的模块名和调用位置，不输出 SQL、驱动消息、参数或源码行。
            name = getattr(exc, "name", None)
            if isinstance(name, str) and re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9.]*", name):
                print(f"导入模块：{name}")
            backend = Path(__file__).resolve().parents[2]
            for frame in traceback.extract_tb(exc.__traceback__):
                path = Path(frame.filename).resolve()
                if path.is_relative_to(backend):
                    print(f"  {path.relative_to(backend).as_posix()}:{frame.lineno} in {frame.name}")
        return 1
    print(f"已同步：{', '.join(['core', *keys])}。插件版本和启停状态保持不变；请重新登录刷新菜单与权限。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
