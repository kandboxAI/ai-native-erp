from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel
from pgvector.sqlalchemy import Vector

config = context.config
BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
ENV_FILE_PATH = BACKEND_DIR / ".env"

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


# 迁移范围由 alembic.ini 的节名决定：public（认证表与租户目录）或 tenant（某个租户 schema 中的业务表）。
# tenant 共用一张 alembic_version：解析 core 和本地保留的所有插件历史。
# deployment 只选择本次升级目标与加载模型；历史可见不等于升级该分支。
SECTION = config.config_ini_section
if SECTION not in ("public", "tenant", "tenant_core"):
    raise RuntimeError("请指定 public、tenant_core 或通过 plugin_cli 指定插件迁移范围")
SCOPE = "public" if SECTION == "public" else "tenant"
if SECTION == "tenant_core":
    os.environ["ERP_DEPLOYMENT_PROFILE"] = "core"


def load_tenant_schema() -> str:
    """租户 schema：-x schema=t_xxx，未指定时为默认租户（t_<DEFAULT_TENANT_NO>）。迁移中不得写死。"""
    from app.core.config import get_settings
    from app.framework.db.tenant import validate_tenant_schema

    schema = context.get_x_argument(as_dictionary=True).get("schema") or get_settings().default_tenant_schema
    return validate_tenant_schema(schema)


TARGET_SCHEMA = "public" if SCOPE == "public" else load_tenant_schema()
# public 迁移的版本表也以 auth_ 开头，保持 public 中只有认证类对象
VERSION_TABLE = "auth_alembic_version" if SCOPE == "public" else "alembic_version"
VERSION_TABLE = config.attributes.get("model_version_table", VERSION_TABLE)


def load_database_url() -> str:
    env_database_url = os.getenv("DATABASE_URL")
    if env_database_url:
        return env_database_url

    if ENV_FILE_PATH.exists():
        for raw_line in ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != "DATABASE_URL":
                continue
            value = value.strip()
            if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                value = value[1:-1]
            if " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            return value

    raise RuntimeError("未找到 DATABASE_URL，请先在 backend/.env 或环境变量中配置。")


def build_sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return database_url
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return database_url


from app.framework.db.registry import import_all_models  # noqa: E402

import_all_models()
if SCOPE == "tenant" and not config.attributes.get("environment_migrations"):
    from app.framework.plugin_migrations import normalize_revision_dependencies

    normalize_revision_dependencies(context.script)
    # Direct CLI maintenance must also avoid upgrading every retained branch.
    try:
        destination = context.get_revision_argument()
    except KeyError:  # current/check/revision have no upgrade destination
        destination = None
    if isinstance(destination, tuple) and len(destination) > 1:
        raise RuntimeError("租户迁移禁止使用全局 heads；请明确指定 core@head 或 <插件key>@head")
# ERP indexes are tenant ai_resource_* models, collected with the other modules.
target_metadata = [SQLModel.metadata]
config.set_main_option("sqlalchemy.url", build_sync_database_url(load_database_url()))
PLUGIN_AUTOGENERATE_KEY = config.attributes.get("plugin_autogenerate_key", "core") if SCOPE == "tenant" else None
IS_AUTOGENERATE = config.attributes.get("scoped_autogenerate", False) or getattr(config.cmd_opts, "autogenerate", False)
if IS_AUTOGENERATE and not config.attributes.get("environment_migrations"):
    raise RuntimeError("增量迁移请使用 scripts/erp.py db revision；共享目录仅保留基线及已发布历史")
OWNED_TABLES = None
if PLUGIN_AUTOGENERATE_KEY:
    from app.framework.plugin_migrations import require_core_manifests, table_owners
    require_core_manifests()
    OWNED_TABLES = {name for name, owner in table_owners().items() if owner == PLUGIN_AUTOGENERATE_KEY}


def _in_scope(table_schema: str | None) -> bool:
    """public 迁移只管 schema="public" 的表；tenant 迁移只管未写 schema 的业务表。"""
    if SCOPE == "public":
        return table_schema == "public"
    return table_schema in (None, TARGET_SCHEMA)


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    if type_ == "table" and OWNED_TABLES is not None and name not in OWNED_TABLES:
        return False
    if type_ == "schema":
        return name == "public" if SCOPE == "public" else name in (None, TARGET_SCHEMA)
    return _in_scope(parent_names.get("schema_name"))


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    if OWNED_TABLES is not None:
        from app.framework.plugin_migrations import owns_migration_object
        if not owns_migration_object(object_, type_, OWNED_TABLES):
            return False
    if getattr(object_, "info", {}).get("skip_autogenerate"):
        return False
    table = object_ if type_ == "table" else getattr(object_, "table", None)
    if table is not None and not reflected:
        model_schema = table.schema
        if SCOPE == "public" and model_schema != "public":
            return False
        if SCOPE == "tenant" and model_schema is not None:
            return False
    if type_ == "table" and reflected and compare_to is None:
        # 不删除模型中不存在的整表
        return False
    return True


def render_item(type_, object_, autogen_context):
    """Keep generated vector columns importable in standalone migration files."""
    if type_ == "type" and isinstance(object_, Vector):
        autogen_context.imports.add("from app.framework.db.types import PublicVector")
        return f"PublicVector({object_.dim!r})" if object_.dim is not None else "PublicVector()"
    if type_ == "type" and object_.__class__.__name__ == "JSONB":
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB(astext_type=sa.Text())"
    return False


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        version_table=VERSION_TABLE,
        version_table_schema=TARGET_SCHEMA,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def _reject_legacy_version_tables(connection) -> None:
    """能力包分支曾使用独立版本表（如 mes_alembic_version）。未合并前继续升级会重复建表，直接拒绝。"""
    if config.attributes.get("allow_legacy_version_tables"):
        return
    from app.framework.plugin import legacy_version_tables

    found = connection.exec_driver_sql(
        "select tablename from pg_tables where schemaname = %(schema)s and tablename = any(%(names)s)",
        {"schema": TARGET_SCHEMA, "names": list(legacy_version_tables())},
    ).scalars().all()
    if found:
        raise RuntimeError(
            f"{TARGET_SCHEMA} 中仍有旧的能力包版本表 {', '.join(found)}；"
            f"请先确认目标库后运行 scripts/merge_plugin_version_tables.py --schema {TARGET_SCHEMA} --apply 合并到 alembic_version"
        )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # 连接建立时就设定 search_path（SQLAlchemy 在首次连接时缓存默认 schema）：
        # tenant 迁移只含该租户 schema，未写 schema 的业务表建到这里；指向 public 的外键显式写 public，
        # public 不在 search_path 中，反射出的外键才会保留 schema 前缀。
        # public 迁移的连接只看 pg_catalog：认证表都显式写 public，同样避免反射时丢失外键的 schema 前缀。
        connect_args={"options": f"-csearch_path={TARGET_SCHEMA if SCOPE == 'tenant' else 'pg_catalog'}"},
    )

    with connectable.connect() as connection:
        if SCOPE == "tenant":
            if IS_AUTOGENERATE:
                if not connection.dialect.has_schema(connection, TARGET_SCHEMA):
                    raise RuntimeError("请先初始化开发租户的底座 schema，再生成插件迁移")
            else:
                connection.exec_driver_sql(f'create schema if not exists "{TARGET_SCHEMA}"')
            connection.commit()
            _reject_legacy_version_tables(connection)
            # The read-only legacy check opens a transaction. End it so the
            # migration context owns and commits its DDL transaction.
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            render_item=render_item,
            dont_mutate=IS_AUTOGENERATE,
            version_table=VERSION_TABLE,
            version_table_schema=TARGET_SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
