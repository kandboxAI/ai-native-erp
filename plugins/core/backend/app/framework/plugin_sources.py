"""Resolve plugin source directories while preserving public Python import names.

Published migration directories retain their existing locations and revisions.
Source ownership is declared by manifests, never inferred from directory order.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.framework.plugin_manifest import read_frontend_manifest, read_plugin_manifests

ROOT = Path(__file__).resolve().parents[5]


def plugin_source_path(root: Path, manifest, logical: str) -> Path:
    """Map a repository-relative source path; keep historical migrations in place."""
    parts = PurePosixPath(logical)
    if parts.is_absolute() or ".." in parts.parts or "\\" in logical:
        raise ValueError(f"插件源码路径无效：{logical}")
    contained = manifest.source_layout == "contained" and logical.startswith(("backend/app/", "web/src/", "miniprogram/src/"))
    target = root / (f"plugins/{manifest.key}" if contained else "") / logical
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError(f"插件源码路径越界或为链接：{logical}")
    return target


def source_path(root: Path, logical: str) -> Path:
    """Resolve an owned logical path, with legacy/core files at their original path."""
    for manifest in read_plugin_manifests(root):
        prefixes = [f"backend/app/modules/{name}/" for name in manifest.module_names]
        if manifest.frontend_manifest:
            frontend = read_frontend_manifest(root / "plugins" / manifest.key / manifest.frontend_manifest)
            prefixes += [f"web/src/views/{name}/" for name in frontend["web_view_roots"]]
            prefixes += [f"miniprogram/src/{PurePosixPath(page).parent}/" for page in frontend["miniapp_pages"]]
        if logical in manifest.package_files or any((logical + "/").startswith(prefix) for prefix in prefixes):
            return plugin_source_path(root, manifest, logical)
    return root / logical


def _orphaned_bytecode_directory(path: Path) -> bool:
    """Git can remove a package while leaving its ignored __pycache__ behind.

    Ignore only that exact residue, never source, adjacent files or links.
    Declared packages are still required to have their real __init__.py.
    """
    if not path.is_dir() or path.is_symlink() or path.is_junction():
        return False
    children = list(path.iterdir())
    if len(children) != 1 or children[0].name != "__pycache__":
        return False
    cache = children[0]
    if not cache.is_dir() or cache.is_symlink() or cache.is_junction():
        return False
    return all(item.is_file() and not item.is_symlink() and not item.is_junction()
               and item.suffix == ".pyc" for item in cache.iterdir())


def module_namespace_paths(existing, namespace: str = "modules", root: Path = ROOT) -> list[str]:
    """Expose contained modules under app.modules without copying or sys.path edits."""
    result = list(existing)
    owners = {}
    for manifest in read_plugin_manifests(root):
        for name in manifest.module_names:
            if name in owners:
                raise ValueError(f"模块归属重复：{name}")
            owners[name] = manifest.key
        if manifest.source_layout != "contained":
            continue
        directory = root / "plugins" / manifest.key / "backend/app" / namespace
        if not directory.is_dir():
            if namespace == "modules":
                raise ValueError(f"{manifest.key}: 缺少独立后端源码目录")
            continue
        if directory.is_symlink() or not directory.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"{manifest.key}: 插件模块目录不能为链接或越界")
        if namespace == "modules":
            declared = set(manifest.module_names)
            entries = [path for path in directory.iterdir() if not path.name.startswith((".", "__"))
                       and not (path.name not in declared and _orphaned_bytecode_directory(path))]
            actual = {path.name for path in entries if path.is_dir()}
            invalid = [path.name for path in entries if not path.is_dir() or path.is_symlink() or not (path / "__init__.py").is_file()]
            if invalid:
                raise ValueError(f"{manifest.key}: 后端目录只能包含 module_names 声明的 Python 包：{', '.join(sorted(invalid))}")
            if actual != declared:
                raise ValueError(f"{manifest.key}: 后端目录必须与声明的 module_names 一致")
            for name in actual:
                if (root / "plugins/core/backend/app/modules" / name / "__init__.py").exists():
                    raise ValueError(f"{manifest.key}: 模块同时存在于底座目录与插件目录：{name}")
        elif namespace == "integrations":
            actual = {path.name for path in directory.iterdir() if not path.name.startswith((".", "__"))}
            if actual - {manifest.key}:
                raise ValueError(f"{manifest.key}: 集成目录只能包含所属插件的命名空间")
            if (root / "plugins/core/backend/app/integrations" / manifest.key / "__init__.py").exists():
                raise ValueError(f"{manifest.key}: 集成同时存在于底座目录与插件目录")
        result.append(str(directory))
    return result
