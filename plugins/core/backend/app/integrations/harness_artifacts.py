"""Shared ownership and file lifecycle for generated ERP AI metadata."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.framework.plugin import loaded_plugin_manifests
from app.framework.ai_catalog import ai_providers

CORE_OWNER = "core"


def route_owner(route) -> str:
    owners = {tag.removeprefix("plugin:") for tag in route.tags if tag.startswith("plugin:")}
    owners.update(tag.removeprefix("metadata:") for tag in route.tags if tag.startswith("metadata:"))
    if len(owners) > 1:
        raise ValueError("HTTP 接口不能同时属于多个能力包")
    return next(iter(owners), CORE_OWNER)


def selected_owners(plugins=None) -> tuple[str, ...]:
    shared = sorted({provider.metadata_key for owner, provider in ai_providers()
                     if owner is None and provider.metadata_key != CORE_OWNER})
    available = (CORE_OWNER, *shared, *(item.key for item in loaded_plugin_manifests()))
    if len(available) != len(set(available)):
        raise ValueError("能力包 key 不能与公共能力元数据分组重复")
    if plugins is None:
        return available
    if not plugins or set(plugins) - set(available):
        raise ValueError("只能选择 core、已加载的 shared_* 分组或能力包")
    return tuple(owner for owner in available if owner in plugins)


def artifact_path(directory: Path, owner: str) -> Path:
    if owner not in selected_owners():
        raise ValueError("未加载的能力包不能读写元数据快照")
    return directory / f"{owner}.generated.json"


def read_artifact(path: Path, *, owner: str, version: int) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or source.get("version") != version or source.get("owner") != owner:
        raise ValueError(f"元数据快照格式或归属无效：{path}")
    return source


def publish_artifacts(directory: Path, documents: dict[str, dict]) -> None:
    """Serialize all selected documents before publishing; unrelated owners are untouched."""
    prepared = [(artifact_path(directory, owner), json.dumps(document, ensure_ascii=False, indent=2) + "\n")
                for owner, document in documents.items()]
    directory.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for path, content in prepared:
            temporary = path.with_suffix(f".{uuid4().hex}.tmp")
            staged.append((temporary, path))
            temporary.write_text(content, encoding="utf-8")
        for temporary, path in staged:
            temporary.replace(path)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
