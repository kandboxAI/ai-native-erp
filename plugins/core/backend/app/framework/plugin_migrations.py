"""Core-based plugin migration contracts and Alembic configuration (no DB I/O)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

from app.framework.db.registry import import_all_models
from app.framework.db.tenant import validate_tenant_schema
from app.framework.deployment import CORE_MODULES
from app.framework.plugin import loaded_plugin_manifests, tenant_version_locations

BACKEND_DIR = Path(__file__).resolve().parents[2]


def immediate_revision_dependencies(script: ScriptDirectory, dependencies) -> tuple[str, ...]:
    """Keep the dependency frontier, omitting ancestors of another dependency.

    For example, app -> (core, stock, facilities) only needs facilities when
    facilities already depends on stock and stock depends on core. Keeping all
    three makes Alembic try to delete version rows already consumed by earlier
    dependency branches.
    """
    if not dependencies:
        return ()
    revisions = script.get_revisions(dependencies)
    ancestors = set()
    for revision in revisions:
        ancestors.update(
            parent.revision for parent in script.iterate_revisions(revision.revision, "base")
            if parent.revision != revision.revision
        )
    return tuple(dict.fromkeys(revision.revision for revision in revisions if revision.revision not in ancestors))


def normalize_revision_dependencies(script: ScriptDirectory) -> None:
    """Adapt old redundant dependency declarations in memory, preserving files.

    Revision IDs, down_revision, migration functions and reachable dependencies
    stay unchanged. Clone Script objects so Alembic rebuilds its graph without
    cached edges from the original map. This also supports already installed
    plugin packages without rewriting their migration history.
    """
    from alembic.script import Script
    from alembic.script.revision import RevisionMap

    revisions = list(script.walk_revisions())
    dependencies = {
        revision.revision: immediate_revision_dependencies(script, revision.dependencies)
        for revision in revisions
    }
    if all(set(dependencies[revision.revision]) == {
        item.revision for item in script.get_revisions(revision.dependencies or ())
    } for revision in revisions):
        return
    normalized = []
    for revision in revisions:
        clone = Script(revision.module, revision.revision, revision.path)
        clone.dependencies = dependencies[revision.revision] or None
        normalized.append(clone)
    script.revision_map = RevisionMap(lambda: iter(normalized))


def table_owners(manifests=None) -> dict[str, str]:
    """Use the defining Python module, not a shared prefix such as md_."""
    import_all_models()
    manifests = loaded_plugin_manifests() if manifests is None else manifests
    modules = {module: item.key for item in manifests for module in item.module_names}
    owners = {}
    for mapper in SQLModel._sa_registry.mappers:
        table = mapper.local_table
        if table.schema is not None:
            continue
        module = mapper.class_.__module__.split(".")
        if module[:2] != ["app", "modules"] or len(module) < 3:
            raise ValueError(f"租户模型缺少模块归属：{table.name}")
        owner = "core" if module[2] in CORE_MODULES else modules.get(module[2])
        if owner is None:
            raise ValueError(f"租户模型来自未加载或未声明的模块：{table.name} ({module[2]})")
        if table.name in owners and owners[table.name] != owner:
            raise ValueError(f"表归属重复：{table.name}")
        owners[table.name] = owner
    return owners


def require_core_manifests():
    manifests = loaded_plugin_manifests()
    if any(item.migration_base != "core" for item in manifests):
        raise ValueError("本命令仅用于 core 新插件；当前存在 migration_base=tenant 的历史插件。请按接入文档准备新清单和新迁移目录，不能直接升级新库。")
    return manifests


def plugin_migration_config(schema: str, plugin_key: str | None = None, *, include_local_legacy: bool = True) -> Config:
    """Resolve all retained histories; deployment only controls targets and models."""
    schema = validate_tenant_schema(schema)
    manifests = require_core_manifests()
    if plugin_key and plugin_key not in {"core", *(item.key for item in manifests)}:
        raise ValueError(f"当前 deployment.json 未加载插件：{plugin_key}")
    config = Config(str(BACKEND_DIR / "alembic.ini"), ini_section="tenant")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("version_locations", "\n".join(str(BACKEND_DIR / location) for location in tenant_version_locations()
        if include_local_legacy or not location.startswith(".local-migrations/")))
    config.cmd_opts = SimpleNamespace(x=[f"schema={schema}"])
    config.attributes["plugin_autogenerate_key"] = plugin_key or "core"
    return config


def tenant_upgrade_targets(plugin_keys: set[str] | None = None) -> tuple[str, ...]:
    """Explicit targets, in dependency order; never use the global `heads`."""
    manifests = require_core_manifests()
    available = {item.key for item in manifests}
    if plugin_keys is not None and (missing := plugin_keys - available):
        raise ValueError(f"当前部署未装载能力包：{', '.join(sorted(missing))}")
    if plugin_keys is not None:
        plugin_keys = set(plugin_keys)
        by_key = {item.key: item for item in manifests}
        pending = list(plugin_keys)
        while pending:
            for spec in by_key[pending.pop()].requires:
                key = spec.split(">=", 1)[0]
                if key not in plugin_keys:
                    plugin_keys.add(key)
                    pending.append(key)
    return tuple(dict.fromkeys(("core@head", *(f"{key}@head" for item in manifests
        if item.migration_location and (plugin_keys is None or item.key in plugin_keys)
        for key in (*getattr(item, "replaces", ()), item.key)))))


def check_revision_prerequisites(script: ScriptDirectory, current, targets) -> None:
    """Check only the revision being generated and its dependencies, read-only.

    All current heads must resolve, including inactive plugins. Uninstalled or
    inactive branches need not be at their newest local revision.
    """
    def reachable(references):
        # A branch and its explicit dependency may overlap; walk each once.
        return {item.revision for head in script.get_revisions(references)
                for item in script.iterate_revisions(head.revision, "base")}

    applied = reachable(current)
    required = reachable(targets)
    if missing := required - applied:
        raise ValueError(f"请先升级目标分支及依赖后生成迁移，缺少版本：{', '.join(sorted(missing))}")


def split_deferred_foreign_keys(migration) -> None:
    """将 use_alter 和引用尚未创建表的外键移到建表完成之后。"""
    from alembic.operations import ops
    from sqlalchemy import ForeignKeyConstraint

    deferred = []
    created = set()

    def table_key(operation):
        return f"{operation.schema}.{operation.table_name}" if operation.schema else operation.table_name

    def create_tables(container):
        for operation in container.ops:
            if isinstance(operation, ops.CreateTableOp):
                yield table_key(operation)
            elif isinstance(operation, ops.OpContainer):
                yield from create_tables(operation)

    new_tables = set(create_tables(migration.upgrade_ops))

    def needs_defer(constraint):
        if not isinstance(constraint, ForeignKeyConstraint):
            return False
        targets = {element.target_fullname.rsplit(".", 1)[0] for element in constraint.elements}
        return constraint.use_alter or bool(targets & (new_tables - created))

    def visit(container):
        for operation in container.ops:
            if isinstance(operation, ops.CreateTableOp):
                # 自引用可内联；循环引用中指向稍后新建表的一侧必须拆出。
                created.add(table_key(operation))
                constraints = sorted((item for item in operation.columns
                                      if needs_defer(item)),
                                     key=lambda item: item.name or "")
                if constraints:
                    removed = {id(item) for item in constraints}
                    operation.columns = [item for item in operation.columns
                                         if id(item) not in removed]
                    deferred.extend(ops.CreateForeignKeyOp.from_constraint(item) for item in constraints)
            elif isinstance(operation, ops.OpContainer):
                visit(operation)

    visit(migration.upgrade_ops)
    migration.upgrade_ops.ops.extend(deferred)
    # 先拆外键再删表；不修改已有迁移、模型元数据或存量外键差异。
    migration.downgrade_ops.ops[:0] = [operation.reverse() for operation in reversed(deferred)]


def compare_declared_checks(migration, migration_context) -> None:
    """比较显式接管的 CHECK 和按名称声明退役的 CHECK；其余约束保持不动。

    Alembic不比较CHECK定义。等价反射文本由模型显式列出，避免通过去掉
    括号、类型转换等方式错误地把不同业务表达式当作相同约束。
    """
    import re
    from alembic.operations import ops
    from sqlalchemy import CheckConstraint, inspect
    from sqlalchemy.schema import conv

    def signature(sql):
        # 仅忽略引号之外的空白；保留字面量、括号、操作符及类型转换。
        return tuple(re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[^\s'\"]+", str(sql)))

    metadata = migration_context.opts["target_metadata"]
    metadata = metadata if isinstance(metadata, (list, tuple)) else [metadata]
    inspector = inspect(migration_context.connection)
    include = migration_context.opts.get("include_object")
    existing = {}
    for source in metadata:
        for table in source.tables.values():
            if include and not include(table, table.name, "table", False, None):
                continue
            checks = [c for c in table.constraints if isinstance(c, CheckConstraint) and c.name]
            declared = [c for c in checks if c.info.get("compare_check")]
            retired_names = table.info.get("retired_check_constraints", ())
            if isinstance(retired_names, (str, bytes)):
                raise ValueError(f"退役 CHECK 必须按名称列表声明：{table.name}")
            retired = set(retired_names)
            if retired & {str(constraint.name) for constraint in checks}:
                raise ValueError(f"CHECK 不能同时声明接管与退役：{table.name}")
            if not (declared or retired) or not inspector.has_table(table.name, schema=table.schema):
                continue  # 新表由CreateTableOp完整创建。
            key = (table.schema, table.name)
            if key not in existing:
                existing[key] = {c["name"]: c for c in inspector.get_check_constraints(
                    table.name, schema=table.schema) if c.get("name")}
            changes = []
            for name in sorted(retired):
                old = existing[key].get(name)
                if old is None:
                    continue
                # 仅处理所属模型明确列出的名字；保留反射定义供审核和降级脚本使用。
                old_op = ops.CreateCheckConstraintOp(conv(name), table.name, old["sqltext"], schema=table.schema)
                if include and not include(old_op.to_constraint(), name, "check_constraint", True, None):
                    continue
                changes.append(old_op.reverse())
            for constraint in sorted(declared, key=lambda c: str(c.name)):
                if include and not include(constraint, constraint.name, "check_constraint", False, None):
                    continue
                old = existing[key].get(str(constraint.name))
                accepted = [str(constraint.sqltext), *constraint.info.get("check_sql_equivalents", ())]
                if old and signature(old["sqltext"]) in {signature(sql) for sql in accepted}:
                    continue
                if old:
                    old_op = ops.CreateCheckConstraintOp(str(constraint.name), table.name,
                        old["sqltext"], schema=table.schema)
                    changes.append(old_op.reverse())
                changes.append(ops.CreateCheckConstraintOp.from_constraint(constraint))
            if changes:
                migration.upgrade_ops.ops.append(ops.ModifyTableOps(table.name, changes, schema=table.schema))
                # 先还原约束，再撤销本轮新增列。
                migration.downgrade_ops.ops.insert(0, ops.ModifyTableOps(table.name,
                    [op.reverse() for op in reversed(changes)], schema=table.schema))


def model_difference_summary(upgrade_ops) -> tuple[str, ...]:
    """仅包含操作种类和对象名称；不输出默认值、表达式或业务数据。"""
    labels = []
    for operation in upgrade_ops.ops:
        if hasattr(operation, "ops"):
            labels.extend(model_difference_summary(operation))
            continue
        table = getattr(operation, "table_name", None) or getattr(operation, "source_table", None)
        name = (getattr(operation, "column_name", None) or getattr(operation, "constraint_name", None)
                or getattr(operation, "index_name", None))
        column = getattr(operation, "column", None)
        if name is None and column is not None:
            name = column.name
        target = ".".join(str(item) for item in (table, name) if item is not None)
        labels.append(f"{type(operation).__name__}: {target}" if target else type(operation).__name__)
    return tuple(labels)


def generate_scoped_revision(config: Config, plugin_key: str, message: str):
    """Explicit autogenerate using Alembic's public comparison/rendering APIs.

    Alembic command.revision requires every local branch head to be installed.
    Here the complete graph remains available for historical resolution, while
    readiness and table comparison are restricted to the requested plugin.
    No version rows are changed and no upgrade/downgrade operations are run.
    """
    from alembic import util
    from alembic.autogenerate import produce_migrations, render_python_code
    from alembic.migration import MigrationContext
    from alembic.runtime.environment import EnvironmentContext

    options = revision_options(config, plugin_key)
    config.attributes["plugin_autogenerate_key"] = plugin_key
    script = ScriptDirectory.from_config(config)
    rendered = {}

    def compare(current, migration_context):
        targets = [*options["depends_on"]]
        if options["head"] != "base":
            targets.append(options["head"])
        check_revision_prerequisites(script, current, tuple(targets))
        migration = produce_migrations(migration_context, migration_context.opts["target_metadata"])
        compare_declared_checks(migration, migration_context)
        split_deferred_foreign_keys(migration)
        if config.attributes.get("environment_migrations"):
            rendered["has_changes"] = not migration.upgrade_ops.is_empty()
            config.attributes["model_differences"] = model_difference_summary(migration.upgrade_ops)
            if config.attributes.get("check_model_only") or not rendered["has_changes"]:
                return []
        render_contexts = {}
        original_render = migration_context.opts.get("render_item")

        def render_item(kind, object_, autogen_context):
            render_contexts[id(autogen_context)] = autogen_context
            return original_render(kind, object_, autogen_context) if original_render else False

        # Rendering needs only the dialect. The live EnvironmentContext's script
        # would make render_python_code require a second autogenerate metadata set.
        render_context = MigrationContext.configure(dialect=migration_context.dialect)
        for name, operations in (("upgrades", migration.upgrade_ops), ("downgrades", migration.downgrade_ops)):
            rendered[name] = render_python_code(operations, migration_context=render_context, render_item=render_item)
        rendered["imports"] = "\n".join(sorted({item for ctx in render_contexts.values() for item in ctx.imports}))
        return []

    previous = config.attributes.get("scoped_autogenerate", False)
    config.attributes["scoped_autogenerate"] = True
    try:
        with EnvironmentContext(config, script, fn=compare):
            script.run_env()
    finally:
        config.attributes["scoped_autogenerate"] = previous
    if config.attributes.get("environment_migrations"):
        has_changes = rendered.pop("has_changes")
        if config.attributes.get("check_model_only"):
            return has_changes
        if not has_changes:
            return None
    return script.generate_revision(
        util.rev_id(), message, head=options["head"], branch_labels=options["branch_label"],
        depends_on=options["depends_on"], version_path=options["version_path"], **rendered,
    )


def owns_migration_object(object_, type_: str, owned_tables: set[str]) -> bool:
    table = object_ if type_ == "table" else getattr(object_, "table", None)
    return table is None or table.name in owned_tables


def check_plugin_models(manifests, owners: dict[str, str]) -> None:
    for item in manifests:
        dependencies = {spec.split(">=", 1)[0] for spec in item.requires}
        for name, owner in owners.items():
            if owner != item.key:
                continue
            table = SQLModel.metadata.tables[name]
            # 专属子命名空间也包含同名根实体，不放宽到相似拼写的其他实体。
            if not (name.startswith(item.table_prefixes) or any(name == prefix[:-1] for prefix in item.table_prefixes)):
                raise ValueError(f"{item.key}: 表 {name} 不属于声明的 table_prefixes")
            if not table.comment or any(not column.comment for column in table.columns):
                raise ValueError(f"{item.key}: 表或字段缺少中文 COMMENT：{name}")
            for foreign_key in table.foreign_keys:
                target = foreign_key.column.table
                if target.schema == "public":
                    continue
                target_owner = owners.get(target.name)
                if target_owner not in {"core", item.key, *dependencies}:
                    raise ValueError(f"{item.key}: {name} 的外键引用未声明的依赖 {target.name} ({target_owner})")


def revision_options(config: Config, plugin_key: str) -> dict:
    """New independent branch depends on core and dependency heads; never legacy trunk."""
    if config.attributes.get("environment_migrations"):
        from app.framework.environment_migrations import local_revision_options
        return local_revision_options(config)
    script = ScriptDirectory.from_config(config)
    script.get_revision("core_0001")
    if plugin_key == "core":
        return {
            "head": "core@head", "branch_label": None, "depends_on": [],
            "version_path": str(BACKEND_DIR / "alembic/versions/core"),
        }
    manifests = {item.key: item for item in require_core_manifests()}
    item = manifests[plugin_key]
    if not item.migration_location:
        raise ValueError(f"{plugin_key}: 必须先声明独立 migration_location")
    directory = BACKEND_DIR / item.migration_location
    if not directory.is_dir():
        raise ValueError(f"迁移目录不存在：{directory}")
    dependencies = [script.get_revision("core@head").revision]
    for key in getattr(item, "replaces", ()):
        dependencies.append(script.get_revision(f"{key}@head").revision)
    for spec in item.requires:
        key = spec.split(">=", 1)[0]
        dependency = manifests[key]
        if dependency.migration_location:
            try:
                dependencies.append(script.get_revision(f"{key}@head").revision)
            except Exception as exc:
                raise ValueError(f"请先为依赖插件 {key} 创建迁移") from exc
    revisions = [revision for revision in script.walk_revisions() if plugin_key in revision.branch_labels]
    return {
        "head": f"{plugin_key}@head" if revisions else "base",
        "branch_label": None if revisions else plugin_key,
        # Package inspection requires an explicit core anchor on every root.
        # Alembic's runtime graph adapter removes that redundant edge safely.
        "depends_on": list(dict.fromkeys(["core_0001", *immediate_revision_dependencies(script, dependencies)])),
        "version_path": str(directory),
    }


def generate_initial_model_revision(config: Config, plugin_key: str, message: str):
    """Offline first branch for a new plugin. Never reflects a DB or rewrites history."""
    from alembic import util
    from alembic.operations import ops
    from alembic.autogenerate import render_python_code
    from sqlalchemy import MetaData
    from sqlalchemy.dialects.postgresql import JSONB
    options = revision_options(config, plugin_key)
    if options["head"] != "base":
        raise ValueError("--from-models 仅用于新插件初始迁移；已有分支请使用 --autogenerate 对照开发库")
    owners = table_owners()
    tables = [table for table in SQLModel.metadata.tables.values() if table.schema is None and owners.get(table.name) == plugin_key]
    if not tables:
        raise ValueError("没有本插件模型；空插件请使用不带 --from-models 的 revision")
    copied = MetaData(naming_convention=SQLModel.metadata.naming_convention)
    for table in tables:
        table.to_metadata(copied)
    operations = []
    # Create every table before adding FKs; audit and hierarchy cycles are valid.
    for original in sorted(tables, key=lambda table: table.name):
        table = copied.tables[original.name]
        for constraint in list(table.foreign_key_constraints):
            table.constraints.remove(constraint)
            for foreign_key in constraint.elements:
                table.foreign_keys.discard(foreign_key)
                foreign_key.parent.foreign_keys.discard(foreign_key)
        operations.append(ops.CreateTableOp.from_table(table))
        operations.extend(ops.CreateIndexOp.from_index(index) for index in sorted(table.indexes, key=lambda index: index.name))
    for table in sorted(tables, key=lambda table: table.name):
        operations.extend(ops.AddConstraintOp.from_constraint(fk) for fk in sorted(table.foreign_key_constraints, key=lambda fk: fk.name))
    upgrade = ops.UpgradeOps(operations)
    def render_type(kind, object_, context):
        if kind == "type" and isinstance(object_, JSONB):
            context.imports.add("from sqlalchemy.dialects import postgresql")
            return "postgresql.JSONB(astext_type=sa.Text())"
        return False
    script = ScriptDirectory.from_config(config)
    return script.generate_revision(
        util.rev_id(), message, head="base", branch_labels=plugin_key,
        depends_on=options["depends_on"], version_path=options["version_path"],
        upgrades=render_python_code(upgrade, render_item=render_type),
        downgrades=render_python_code(upgrade.reverse(), render_item=render_type),
        imports="from sqlalchemy.dialects import postgresql",
    )
