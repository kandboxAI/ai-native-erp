"""读取内置能力包清单并校验部署组合；只处理元数据，不导入业务代码。"""

from __future__ import annotations

import re
import json
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.framework.plugin_settings import PluginConfiguration, read_plugin_configuration

PLUGIN_DIR = Path(__file__).resolve().parents[5] / "plugins"
_KEY = re.compile(r"[a-z][a-z0-9_]*\Z")


_AI_SKILL_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_VERSION = re.compile(r"\d+(?:\.\d+){1,2}\Z")
_REQUIREMENT = re.compile(r"([a-z][a-z0-9_]*)(?:>=(\d+(?:\.\d+){1,2}))?\Z")
_CORE_MODULE_NAMES = frozenset(json.loads(Path(__file__).with_name("core_manifest.json").read_text(encoding="utf-8"))["module_names"])
_CORE_TABLE_PREFIXES = ("auth_", "sys_", "wf_", "ntf_", "file_", "doc_", "kb_", "ai_", "int_", "audit_")
_FIELDS = frozenset({"key", "name", "layer", "version", "requires", "module_codes", "module_names", "table_prefixes", "routers", "menu_keys", "miniapp_menu_keys", "migration_location", "migration_base", "ai_skill_keys", "ai_providers", "ai_context_providers", "frontend_manifest", "package_files", "replaces", "source_layout", "configuration"})
_REQUIRED = _FIELDS - {"menu_keys", "miniapp_menu_keys", "migration_location", "migration_base", "ai_skill_keys", "ai_providers", "ai_context_providers", "frontend_manifest", "package_files", "replaces", "source_layout", "configuration"}


def is_generated_ai_snapshot(name: str) -> bool:
    """Identify current and archived environment snapshots, never their source policy."""
    return bool(re.fullmatch(
        r"backend/app/integrations/harness_(?:http|schema)/[a-z][a-z0-9_]*\.generated\.json"
        r"|plugins/[a-z][a-z0-9_]*/legacy/[a-z][a-z0-9_]*/harness_(?:http|schema)\.generated\.json",
        name,
    ))


@dataclass(frozen=True)
class PluginManifest:
    key: str
    name: str
    layer: str
    version: str
    requires: tuple[str, ...]
    module_codes: tuple[str, ...]
    module_names: tuple[str, ...]
    table_prefixes: tuple[str, ...]
    routers: tuple[str, ...]
    menu_keys: tuple[str, ...] = ()
    miniapp_menu_keys: tuple[str, ...] = ()
    migration_location: str | None = None
    ai_skill_keys: tuple[str, ...] = ()
    ai_providers: tuple[str, ...] = ()
    ai_context_providers: tuple[str, ...] = ()
    frontend_manifest: str | None = None
    migration_base: str = "core"
    package_files: tuple[str, ...] = ()
    replaces: tuple[str, ...] = ()
    source_layout: str = "legacy"
    configuration: PluginConfiguration | None = None


def _string_list(document: dict, field: str, path: Path) -> tuple[str, ...]:
    value = document[field]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{path}: {field} 必须是字符串数组")
    if len(value) != len(set(value)):
        raise ValueError(f"{path}: {field} 不能重复")
    return tuple(value)


def read_plugin_manifest(path: Path) -> PluginManifest:
    try:
        with path.open("rb") as file:
            document = tomllib.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"缺少能力包清单：{path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"能力包清单不是有效 TOML：{path}") from exc
    if not isinstance(document, dict) or not _REQUIRED <= document.keys() or document.keys() - _FIELDS:
        raise ValueError(f"{path}: 能力包清单字段不完整或包含未知字段")
    for field in ("key", "name", "layer", "version"):
        if not isinstance(document[field], str) or not document[field]:
            raise ValueError(f"{path}: {field} 必须是非空字符串")
    if not _KEY.fullmatch(document["key"]) or document["key"] != path.parent.name:
        raise ValueError(f"{path}: key 必须与能力包目录名一致且使用小写 snake_case")
    # L1 中可选的知识能力也复用同一租户开通机制，身份、权限等核心底座仍始终加载。
    if document["layer"] not in {"L1", "L2", "L3"} or not _VERSION.fullmatch(document["version"]):
        raise ValueError(f"{path}: layer 或 version 不合法")
    requires = _string_list(document, "requires", path)
    source_layout = document.get("source_layout", "legacy")
    if source_layout not in {"legacy", "contained"}:
        raise ValueError(f"{path}: source_layout 必须为 legacy 或 contained")
    if any(_REQUIREMENT.fullmatch(item) is None for item in requires):
        raise ValueError(f"{path}: requires 必须为能力包 key 或 key>=最低版本")
    replaces = _string_list(document, "replaces", path) if "replaces" in document else ()
    if any(not _KEY.fullmatch(key) or key in {"core", document["key"]} for key in replaces):
        raise ValueError(f"{path}: replaces 只能声明其他业务插件 key，不能接管 core 或自身")
    if set(replaces) & {spec.split(">=", 1)[0] for spec in requires}:
        raise ValueError(f"{path}: replaces 与 requires 不能重叠")
    module_codes = _string_list(document, "module_codes", path)
    module_names = _string_list(document, "module_names", path)
    table_prefixes = _string_list(document, "table_prefixes", path)
    routers = _string_list(document, "routers", path)
    if set(module_names) & _CORE_MODULE_NAMES:
        raise ValueError(f"{path}: 插件不能声明拥有底座模块")
    reserved_prefixes = []
    for prefix in table_prefixes:
        for core_prefix in _CORE_TABLE_PREFIXES:
            if not prefix.startswith(core_prefix):
                continue
            # Optional L1 extensions may own a narrower AI namespace, while the
            # generic ai_ / kb_ namespace itself remains reserved by the core.
            if document["layer"] == "L1" and core_prefix in {"ai_", "kb_"} and prefix != core_prefix:
                continue
            reserved_prefixes.append(prefix)
            break
    if reserved_prefixes:
        raise ValueError(f"{path}: 插件不能声明底座或认证表前缀")
    menu_keys = _string_list(document, "menu_keys", path) if "menu_keys" in document else ()
    miniapp_menu_keys = _string_list(document, "miniapp_menu_keys", path) if "miniapp_menu_keys" in document else ()
    ai_skill_keys = _string_list(document, "ai_skill_keys", path) if "ai_skill_keys" in document else ()
    if any(not _AI_SKILL_KEY.fullmatch(item) for item in ai_skill_keys):
        raise ValueError(f"{path}: ai_skill_keys 必须使用小写短横线分隔的技能标识")
    ai_providers = _string_list(document, "ai_providers", path) if "ai_providers" in document else ()
    ai_context_providers = _string_list(document, "ai_context_providers", path) if "ai_context_providers" in document else ()
    for reference in (*ai_providers, *ai_context_providers):
        match = re.fullmatch(r"app\.modules\.([a-z][a-z0-9_]*)(?:\.[a-z][a-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*", reference)
        if match is None or match.group(1) not in module_names:
            raise ValueError(f"{path}: ai_providers 只能引用 module_names 中模块的提供器")
    if not module_codes or not module_names or not table_prefixes:
        raise ValueError(f"{path}: module_codes、module_names 和 table_prefixes 不能为空")
    if any(not _KEY.fullmatch(item) for item in (*module_codes, *module_names)):
        raise ValueError(f"{path}: 模块标识必须使用小写 snake_case")
    if any(not item.endswith("_") or not _KEY.fullmatch(item[:-1]) for item in table_prefixes):
        raise ValueError(f"{path}: 表前缀必须使用小写 snake_case 并以 _ 结尾")
    for router in routers:
        match = re.fullmatch(r"app\.modules\.([a-z][a-z0-9_]*)(?:\.[a-z][a-z0-9_]*)*:[a-z][a-z0-9_]*", router)
        if match is None or match.group(1) not in module_names:
            raise ValueError(f"{path}: routers 只能引用 module_names 中模块的路由：{router}")
    migration_location = document.get("migration_location")
    package_files = _string_list(document, "package_files", path) if "package_files" in document else ()
    for filename in package_files:
        if not re.fullmatch(rf"(?:web|miniprogram)/src/api/{re.escape(document['key'])}[A-Za-z0-9_]*\.ts|backend/app/integrations/{re.escape(document['key'])}/(?:__init__|[a-z][a-z0-9_]*)\.py|backend/app/integrations/harness_(?:http|schema)/{re.escape(document['key'])}\.generated\.json", filename):
            raise ValueError(f"{path}: package_files 仅支持本插件 API、集成模块和 AI 快照：{filename}")
    migration_base = document.get("migration_base", "core")
    if migration_base != "core":
        raise ValueError(f"{path}: 开源底座的 migration_base 必须为 core；旧插件需先准备独立分支")
    frontend_manifest = document.get("frontend_manifest")
    if frontend_manifest is not None:
        if frontend_manifest != "frontend.json":
            raise ValueError(f"{path}: frontend_manifest 当前须引用插件自身的 frontend.json")
        read_frontend_manifest(path.parent / frontend_manifest)
    if migration_location is not None and (
        not isinstance(migration_location, str)
        or migration_location != f"alembic/versions/plugins/{document['key']}"
    ):
        raise ValueError(f"{path}: migration_location 必须是 alembic/versions/plugins/<本插件key>")
    configuration = read_plugin_configuration(path.parent, document["key"], document["configuration"]) if "configuration" in document else None
    return PluginManifest(
        key=document["key"], name=document["name"], layer=document["layer"],
        version=document["version"], requires=requires, module_codes=module_codes,
        module_names=module_names, table_prefixes=table_prefixes, routers=routers,
        menu_keys=menu_keys,
        miniapp_menu_keys=miniapp_menu_keys,
        migration_location=migration_location,
        ai_skill_keys=ai_skill_keys,
        ai_providers=ai_providers,
        ai_context_providers=ai_context_providers,
        frontend_manifest=frontend_manifest,
        migration_base=migration_base,
        package_files=package_files,
        replaces=replaces,
        source_layout=source_layout,
        configuration=configuration,
    )


def _validate_branding(branding: object, path: Path) -> None:
    """与管理端清单校验保持一致；品牌只允许展示字段。"""
    text_fields = {"title", "subtitle", "english_name", "mark", "assistant_name", "description"}
    asset_fields = {"logo", "header_logo", "favicon", "miniapp_logo", "miniapp_assistant_avatar"}
    login_text_fields = {"school_name", "english_name", "welcome_title", "subtitle", "tagline", "background_alt", "ai_note"}

    def fail() -> None:
        raise ValueError(f"{path}: branding 展示配置无效")

    def asset(value: object) -> bool:
        return isinstance(value, str) and (value == "" or (
            value == value.strip() and not re.search(r"[\s<>\"'\\?#]", value)
            and not value.startswith("//") and ".." not in value.split("/")
            and (re.fullmatch(r"https://[^/]+(?:/.*)?", value) is not None or ":" not in value)
        ))

    def strings(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)

    if not isinstance(branding, dict) or not isinstance(branding.get("title"), str) or not branding["title"].strip():
        fail()
    for key, value in branding.items():
        if key in text_fields:
            if not isinstance(value, str) or not value.strip():
                fail()
        elif key in asset_fields:
            if not asset(value):
                fail()
        elif key == "login":
            if not isinstance(value, dict):
                fail()
            for field, content in value.items():
                if field in login_text_fields:
                    if not isinstance(content, str) or not content.strip():
                        fail()
                elif field == "background":
                    if not asset(content):
                        fail()
                elif field == "help_lines":
                    if not strings(content):
                        fail()
                elif field == "steps":
                    if not isinstance(content, list) or any(
                        not isinstance(step, dict)
                        or not {"title", "lines"} <= set(step) <= {"title", "lines", "icon"}
                        or ("icon" in step and (not isinstance(step["icon"], str)
                            or not re.fullmatch(r"ri:[a-z0-9]+(?:-[a-z0-9]+)*", step["icon"])))
                        or not isinstance(step["title"], str) or not step["title"].strip()
                        or not strings(step["lines"]) for step in content
                    ):
                        fail()
                else:
                    fail()
        else:
            fail()


def read_frontend_manifest(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    fields = {"format_version", "web_view_roots", "miniapp_pages", "miniapp_service_provider"}
    if not isinstance(document, dict) or not fields <= set(document) or set(document) - fields - {"web_applications", "web_workbench", "web_calendar_provider", "workflow_routes", "branding", "web_sidebar"} or type(document["format_version"]) is not int or document["format_version"] != 1:
        raise ValueError(f"{path}: 前端清单格式无效")
    if "branding" in document:
        _validate_branding(document["branding"], path)
    for field, pattern in (("web_view_roots", r"[a-z][a-z0-9-]*"), ("miniapp_pages", r"pages/[a-z][a-z0-9-]*/[a-z][a-z0-9-]*")):
        values = _string_list(document, field, path)
        if any(not re.fullmatch(pattern, value) for value in values):
            raise ValueError(f"{path}: {field} 路径不合法")
    workflow_routes = document.get("workflow_routes", {})
    if not isinstance(workflow_routes, dict) or any(not _KEY.fullmatch(key) or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) for key, value in workflow_routes.items()):
        raise ValueError(f"{path}: workflow_routes 无效")
    provider = document["miniapp_service_provider"]
    calendar = document.get("web_calendar_provider")
    if calendar is not None and (not isinstance(calendar, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9/-]*\.ts", calendar) or not (path.parent / "web/src" / calendar).is_file()):
        raise ValueError(f"{path}: 工作台日程提供器必须是插件内已存在的 TS 文件")
    workbench = document.get("web_workbench")
    if workbench is not None and (not isinstance(workbench, str) or not re.fullmatch(r"[a-z][a-z0-9-]*/[a-z][a-z0-9/-]*", workbench) or workbench.split("/")[0] not in document["web_view_roots"]):
        raise ValueError(f"{path}: 工作台必须属于本插件页面目录")
    applications = document.get("web_applications", [])
    application_fields = {"title", "summary", "icon", "path", "rootPath", "tone"}
    if not isinstance(applications, list) or any(not isinstance(item, dict) or set(item) != application_fields or any(not isinstance(value, str) or not value for value in item.values()) for item in applications):
        raise ValueError(f"{path}: web_applications 必须声明完整的应用入口")
    if not isinstance(provider, str) or not re.fullmatch(r"miniprogram/[a-z][a-z0-9_-]*\.ts", provider) or not (path.parent / provider).is_file():
        raise ValueError(f"{path}: 小程序入口提供器必须是插件内已存在的 TS 文件")
    return document


@lru_cache(maxsize=1)
def builtin_plugin_manifests() -> tuple[PluginManifest, ...]:
    return read_plugin_manifests(PLUGIN_DIR.parent)


def active_plugin_manifests(manifests) -> tuple[PluginManifest, ...]:
    """A successor owns registration; retained predecessor manifests are historical."""
    manifests = tuple(manifests)
    replaced = {}
    for item in manifests:
        for key in item.replaces:
            if key in replaced and replaced[key] != item.key:
                raise ValueError(f"插件 {key} 被多个插件接管")
            replaced[key] = item.key
    if any(item.key in replaced and item.replaces for item in manifests):
        raise ValueError("不支持插件接管链或接管环，请先明确最终拥有者")
    return tuple(item for item in manifests if item.key not in replaced)


def read_plugin_manifests(root: Path) -> tuple[PluginManifest, ...]:
    return active_plugin_manifests(read_plugin_manifest(path) for path in sorted((root / "plugins").glob("*/plugin.toml")))


def canonical_plugin_keys(keys, manifests) -> frozenset[str]:
    keys = set(keys)
    for item in manifests:
        selected = keys & set(item.replaces)
        if selected and item.key not in keys:
            raise ValueError(f"插件 {', '.join(sorted(selected))} 已合并到 {item.key}，请明确选择 {item.key}")
        keys -= selected
    return frozenset(keys)


def recorded_plugin_keys(records, manifests) -> set[str]:
    """Merged plugins require an explicit successful upgrade before exposing new modules."""
    available = {item.key: item for item in manifests}
    return {row.plugin_key for row in records
            if row.provisioning_status_code == "ready" and row.is_active and row.plugin_key in available
            and (not available[row.plugin_key].replaces or row.installed_version == available[row.plugin_key].version)}


def migration_locations(manifest) -> tuple[str, ...]:
    return tuple(location for location in (manifest.migration_location, *(
        f"alembic/versions/plugins/{key}" for key in getattr(manifest, "replaces", ())
    )) if location)


def resolve_plugin_manifests(
    keys: set[str] | frozenset[str], manifests: tuple[PluginManifest, ...] | None = None,
) -> tuple[PluginManifest, ...]:
    """依赖先于使用方；缺失、版本不足与依赖环均拒绝加载。"""
    candidates = active_plugin_manifests(manifests) if manifests is not None else builtin_plugin_manifests()
    keys = canonical_plugin_keys(keys, candidates)
    available = {item.key: item for item in candidates}
    if len(available) != len(candidates):
        raise ValueError("能力包 key 重复")
    missing = keys - available.keys()
    if missing:
        raise ValueError(f"缺少能力包清单：{', '.join(sorted(missing))}")
    result: list[PluginManifest] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError(f"能力包依赖成环：{key}")
        if key in visited:
            return
        visiting.add(key)
        item = available[key]
        for spec in item.requires:
            match = _REQUIREMENT.fullmatch(spec)
            assert match is not None  # read_plugin_manifest 已验证；测试可直接传入清单
            dependency, minimum = match.groups()
            if dependency not in keys:
                raise ValueError(f"能力包 {key} 缺少依赖 {dependency}")
            other = available[dependency]
            if minimum is not None:
                current = tuple(map(int, other.version.split(".")))
                required = tuple(map(int, minimum.split(".")))
                width = max(len(current), len(required))
                if current + (0,) * (width - len(current)) < required + (0,) * (width - len(required)):
                    raise ValueError(f"能力包 {key} 要求 {dependency}>={minimum}，当前为 {other.version}")
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
        result.append(item)

    for key in sorted(keys):
        visit(key)
    for item in result:
        for spec in item.requires:
            dependency = available[spec.split(">=", 1)[0]]
            if item.layer == "L2" and dependency.layer == "L3":
                raise ValueError(f"L2 能力包 {item.key} 不能依赖 L3 能力包 {dependency.key}")
    skill_owners: dict[str, str] = {}
    for item in result:
        for skill_key in item.ai_skill_keys:
            owner = skill_owners.setdefault(skill_key, item.key)
            if owner != item.key:
                raise ValueError(f"AI 技能标识 {skill_key} 同时属于能力包 {owner} 和 {item.key}")
    return tuple(result)


def miniapp_registrations(document: dict) -> dict[str, dict]:
    """统一主包/分包完整路由，供源码检查和可导入包登记使用。"""
    result = {}
    for page in document['pages']:
        if page['path'] in result:
            raise ValueError('小程序主包与分包路由重复')
        result[page['path']] = {key: value for key, value in page.items() if key in {'path', 'style'}}
    for group in document.get('subPackages', document.get('subpackages', [])):
        root = group['root']
        if not isinstance(root, str) or not re.fullmatch(r'pages/[a-z][a-z0-9-]*', root):
            raise ValueError('小程序分包根目录无效')
        for page in group['pages']:
            path = f"{root}/{page['path']}"
            if path in result:
                raise ValueError('小程序主包与分包路由重复')
            result[path] = {**{key: value for key, value in page.items() if key == 'style'},
                            'path': path, 'subpackage_root': root}
    return result


def merge_miniapp_registrations(document: dict, registrations: list[dict]) -> bool:
    """保留已登记页面的自定义样式；升级时可将自有页面迁入声明的分包。"""
    before = json.dumps(document, sort_keys=True, ensure_ascii=False)
    existing = miniapp_registrations(document)
    for item in registrations:
        path, root = item['path'], item.get('subpackage_root')
        previous = existing.get(path)
        if previous and (not root or previous.get('subpackage_root') == root):
            continue
        if root:
            if not isinstance(root, str) or not re.fullmatch(r'pages/[a-z][a-z0-9-]*', root) or not path.startswith(root + '/'):
                raise ValueError('小程序分包登记路径无效')
            document['pages'] = [page for page in document['pages'] if page['path'] != path]
            groups = document.setdefault('subPackages', document.pop('subpackages', []))
            for group in groups:
                group['pages'] = [page for page in group['pages'] if f"{group['root']}/{page['path']}" != path]
            group = next((group for group in groups if group['root'] == root), None)
            if group is None:
                group = {'root': root, 'pages': []}
                groups.append(group)
            group['pages'].append({**{key: value for key, value in (previous or item).items() if key == 'style'},
                                   'path': path[len(root) + 1:]})
        elif previous is None:
            document['pages'].append({key: value for key, value in item.items() if key in {'path', 'style'}})
    miniapp_registrations(document)
    return json.dumps(document, sort_keys=True, ensure_ascii=False) != before
