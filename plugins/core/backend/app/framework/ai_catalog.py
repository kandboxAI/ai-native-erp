"""能力包声明 AI 资源；归属由部署加载器赋予，不依赖表名前缀。"""

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import import_module
from pathlib import Path
import re
from typing import Any, Callable

from app.framework.catalog import iter_module_attr
from app.framework.deployment import module_plugin_owner
from app.framework.plugin import loaded_plugin_manifests
from app.framework.plugin_manifest import builtin_plugin_manifests


@dataclass(frozen=True)
class AiQueryResourceDef:
    table_name: str
    permission: str
    fields: tuple[str, ...]  # 兼容已发布提供器；实际可查询字段由 ORM 模型生成。
    api_entity: str | None = None
    additional_filters: Callable[[Any, Any], tuple[Any, ...]] | None = None


@dataclass(frozen=True)
class AiProvider:
    domain: str
    resources: tuple[AiQueryResourceDef, ...]
    semantics_path: Path | None = None
    read_routes: tuple[tuple[str, str], ...] = ()
    inherit_http_policy: bool = False
    # Maintenance group for an unbundled shared module; never grants runtime access.
    metadata_key: str = "core"
    http_modules: tuple[str, ...] = ()
    write_routes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RegisteredAiResource:
    definition: AiQueryResourceDef
    domain: str
    plugin_key: str | None
    metadata_key: str = "core"


@lru_cache(maxsize=1)
def ai_providers() -> tuple[tuple[str | None, AiProvider], ...]:
    """固定底座沿用模块收集约定；可选能力包仅加载清单中的提供器。"""
    providers: list[tuple[str | None, AiProvider]] = []
    optional_modules = {name for item in builtin_plugin_manifests() for name in item.module_names}
    for module in iter_module_attr("ai_catalog", exclude=optional_modules):
        module_name = module.__name__.split(".")[2]
        if module_plugin_owner(module_name) is None:
            providers.append((None, module.PROVIDER))
    references: set[str] = set()
    for manifest in loaded_plugin_manifests():
        for reference in manifest.ai_providers:
            if reference in references:
                raise ValueError(f"重复的 AI 提供器：{reference}")
            references.add(reference)
            module_name, attribute = reference.split(":", 1)
            provider = getattr(import_module(module_name), attribute)
            if not isinstance(provider, AiProvider):
                raise ValueError(f"AI 提供器类型无效：{reference}")
            modules = provider.http_modules or (module_name.split(".")[2],)
            if not set(modules) <= set(manifest.module_names):
                raise ValueError(f"HTTP 策略模块不属于插件：{reference}")
            providers.append((manifest.key, replace(provider, http_modules=modules)))
    for _, provider in providers:
        if not isinstance(provider, AiProvider) or not provider.domain:
            raise ValueError("AI 提供器必须声明有效的 AiProvider")
        if not re.fullmatch(r"core|shared_[a-z][a-z0-9_]{0,55}", provider.metadata_key):
            raise ValueError("公共提供器元数据分组须为 core 或 shared_<模块key>")
    return tuple(providers)


@lru_cache(maxsize=1)
def registered_ai_resources() -> dict[str, RegisteredAiResource]:
    result: dict[str, RegisteredAiResource] = {}
    entities: set[str] = set()
    for plugin_key, provider in ai_providers():
        for definition in provider.resources:
            if definition.table_name in result:
                raise ValueError(f"AI 查询资源重复：{definition.table_name}")
            if definition.api_entity is not None:
                if definition.api_entity in entities:
                    raise ValueError(f"AI 接口实体重复：{definition.api_entity}")
                entities.add(definition.api_entity)
            result[definition.table_name] = RegisteredAiResource(definition, provider.domain, plugin_key,
                                                                plugin_key or provider.metadata_key)
    return result
