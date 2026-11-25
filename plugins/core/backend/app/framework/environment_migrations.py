"""Per-database model differences; generated files never belong to a source package.

Legacy baselines/version tables are left untouched. Each schema/scope has its own
local Alembic graph, starting from the physical schema, not a shared revision head.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class ModelMigrationRequired(ValueError):
    """Safe operator guidance, with no SQL, connection URL or business values."""


def environment_directory(schema: str, database_url: str | None = None) -> Path:
    from app.framework.db.tenant import validate_tenant_schema

    if schema != "public":
        validate_tenant_schema(schema)
    if database_url is None:
        from app.core.config import get_settings
        database_url = get_settings().database_url
    url = make_url(database_url)
    if not url.database:
        raise ValueError("数据库连接没有指定库名")
    # Passwords, usernames and URL options never enter paths or marker files.
    identity = json.dumps([url.host or url.query.get("host"), url.port or url.query.get("port") or 5432, url.database], ensure_ascii=True)
    database_key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return BACKEND_DIR / ".local-migrations" / database_key / schema


def environment_active(schema: str) -> bool:
    return (environment_directory(schema) / "model-mode.json").is_file()


def mark_environment(config: Config) -> None:
    directory = Path(config.attributes["environment_directory"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model-mode.json").write_text(
        '{"format_version":1,"mode":"model-diff"}\n', encoding="utf-8"
    )


def environment_config(schema: str, scope: str, *, database_url: str | None = None) -> Config:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", scope):
        raise ValueError("迁移范围必须是 public、core 或插件 key")
    public = scope == "public"
    if public != (schema == "public"):
        raise ValueError("public 范围必须使用 public schema；租户范围必须使用 t_ schema")
    directory = environment_directory(schema, database_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"), ini_section="public" if public else "tenant")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("version_locations", str(directory / scope))
    config.set_main_option("path_separator", "newline")
    config.cmd_opts = SimpleNamespace(x=[] if public else [f"schema={schema}"])
    # This graph never references or edits the shared historical version table.
    suffix = scope if len(scope) <= 24 else scope[:15] + "_" + hashlib.sha256(scope.encode()).hexdigest()[:8]
    config.attributes.update(
        environment_migrations=True,
        environment_directory=str(directory),
        plugin_autogenerate_key=None if public else scope,
        model_version_table="auth_model_version" if public else f"sys_model_{suffix}_version",
    )
    return config


def local_revision_options(config: Config) -> dict:
    directory = Path(config.get_main_option("version_locations"))
    directory.mkdir(parents=True, exist_ok=True)
    script = ScriptDirectory.from_config(config)
    if len(script.get_heads()) > 1:
        raise ValueError("本环境范围存在多个迁移头，请先整理本地迁移；不要删除已执行文件")
    return {"head": "head" if script.get_heads() else "base", "branch_label": None,
            "depends_on": [], "version_path": str(directory)}


def selected_scopes(plugin_keys: set[str] | None = None) -> tuple[str, ...]:
    from app.framework.plugin_migrations import require_core_manifests

    manifests = require_core_manifests()
    available = {item.key: item for item in manifests}
    wanted = set(available) if plugin_keys is None else set(plugin_keys)
    if missing := wanted - {"public", "core", *available}:
        raise ValueError(f"当前部署未加载插件：{', '.join(sorted(missing))}")
    if wanted == {"public"}:
        return ("public",)
    pending = list(wanted - {"public", "core"})
    while pending:
        for spec in available[pending.pop()].requires:
            key = spec.split(">=", 1)[0]
            if key not in wanted:
                wanted.add(key)
                pending.append(key)
    return ("public", "core", *(item.key for item in manifests if item.key in wanted))


def generate_environment_revision(schema: str, scope: str, message: str):
    from app.framework.plugin_migrations import generate_scoped_revision

    config = environment_config("public" if scope == "public" else schema, scope)
    result = generate_scoped_revision(config, scope, message)
    mark_environment(config)
    return result


def upgrade_environment_scope(schema: str, scope: str) -> None:
    from app.framework.plugin_migrations import generate_scoped_revision

    config = environment_config("public" if scope == "public" else schema, scope)
    command.upgrade(config, "head")
    # Do not mark a plugin version installed when its current models do not fit.
    config.attributes["check_model_only"] = True
    if generate_scoped_revision(config, scope, "check models"):
        differences = config.attributes.get("model_differences", ())
        summary = "\n剩余结构差异：\n" + "\n".join(f"  {item}" for item in differences[:12]) if differences else ""
        if len(differences) > 12:
            summary += f"\n  ……共 {len(differences)} 项"
        raise ModelMigrationRequired(
            f"{scope} 的目标库与当前模型不一致；请先执行 scripts/erp.py db revision "
            f"--plugin {scope} --schema {schema}，审核文件后再 db upgrade。{summary}"
        )
    mark_environment(config)


def current_environment_scope(schema: str, scope: str) -> None:
    config = environment_config("public" if scope == "public" else schema, scope)
    command.current(config)


def run_workflow(action: str, schema: str, plugin_keys: set[str] | None, message: str) -> None:
    for scope in selected_scopes(plugin_keys):
        print(f"→ {scope}", flush=True)
        if action == "revision":
            result = generate_environment_revision(schema, scope, message)
            print(f"待审核：{result.path}" if result else "模型与目标库一致，无需生成迁移。")
        elif action == "upgrade":
            upgrade_environment_scope(schema, scope)
        else:
            current_environment_scope(schema, scope)


def migration_error_message(exc: Exception) -> str:
    """只输出稳定错误码与对象名，不输出 SQL、绑定参数或驱动的行内容。"""
    if type(exc) is ValueError or isinstance(exc, ModelMigrationRequired):
        return str(exc)
    original = getattr(exc, "orig", exc)
    code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    reasons = {"23502": "必填字段缺少存量数据回填", "23503": "外键引用不匹配",
               "23505": "唯一键重复", "23514": "数据不满足检查约束"}
    fields = []
    if isinstance(code, str) and re.fullmatch(r"[0-9A-Z]{5}", code):
        fields.append(f"SQLSTATE={code}")
    diag = getattr(original, "diag", None)
    for key in ("schema_name", "table_name", "column_name", "constraint_name"):
        value = getattr(diag, key, None)
        if isinstance(value, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
            fields.append(f"{key}={value}")
    detail = f"；{'，'.join(fields)}" if fields else ""
    reason = reasons.get(code, "请检查目标结构和本环境迁移文件")
    return f"环境迁移失败（{type(exc).__name__}{detail}）：{reason}；不要删除版本记录或 stamp。"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("revision", "upgrade", "current"))
    parser.add_argument("--schema", required=True)
    parser.add_argument("--plugin", action="append")
    parser.add_argument("--message", default="sync current models")
    args = parser.parse_args(argv)
    try:
        run_workflow(args.action, args.schema, set(args.plugin) if args.plugin else None, args.message)
        return 0
    except Exception as exc:
        # Driver exceptions may contain credentials or business values.
        print(migration_error_message(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
