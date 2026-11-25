"""Versioned source bundles. Import source/config only; never execute plugin or SQL."""
from __future__ import annotations

from contextlib import contextmanager
import ast
import hashlib
import json
import os
import re
from dataclasses import replace
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from app.framework.plugin_manifest import read_plugin_manifest, read_frontend_manifest, resolve_plugin_manifests, active_plugin_manifests, canonical_plugin_keys, migration_locations, is_generated_ai_snapshot
from app.framework.plugin_sources import plugin_source_path, module_namespace_paths
from app.framework.plugin_settings import is_private_plugin_configuration
from app.framework.plugin_manifest import miniapp_registrations, merge_miniapp_registrations

HEADER = "erp-plugin-package.json"
SKIP = {"__pycache__", "node_modules", ".git", ".venv", "dist"}


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _safe(name):
    if not isinstance(name, str):
        raise ValueError("插件包路径必须是字符串")
    path = PurePosixPath(name)
    if not isinstance(name, str) or not name or path.is_absolute() or path.as_posix() != name or any(part in {"", ".", ".."} or ":" in part or "\\" in part or part.endswith((".", " ")) for part in path.parts):
        raise ValueError(f"插件包路径无效：{name}")
    return path


def _roots(root, manifest):
    frontend = read_frontend_manifest(root / "plugins" / manifest.key / manifest.frontend_manifest) if manifest.frontend_manifest else {}
    core = json.loads((Path(__file__).with_name("core_manifest.json")).read_text(encoding="utf-8"))
    mini = json.loads((Path(__file__).with_name("miniapp_core.json")).read_text(encoding="utf-8"))
    web_roots = frontend.get("web_view_roots", [])
    mini_roots = {str(PurePosixPath(page).parent) for page in frontend.get("miniapp_pages", [])}
    if set(web_roots) & set(core["web_view_roots"]) or mini_roots & {str(PurePosixPath(page).parent) for page in mini["pages"]}:
        raise ValueError("业务插件不能拥有底座页面目录")
    roots = [f"plugins/{manifest.key}"]
    if manifest.source_layout == "legacy":
        roots.extend([*(f"backend/app/modules/{name}" for name in manifest.module_names), *(f"web/src/views/{name}" for name in web_roots), *(f"miniprogram/src/{name}" for name in mini_roots)])
    roots.extend("plugins/core/backend/" + location for location in migration_locations(manifest))
    return roots, frontend


def _owned(name, roots, extra):
    return name in extra or any(name.startswith(prefix + "/") for prefix in roots)


def _private_configuration(name, manifest):
    return is_private_plugin_configuration(name, manifest.key, manifest.configuration)


def miniapp_pages_path(root: Path) -> Path:
    path = root / "plugins/core/miniprogram/src/pages.json"
    return path if path.is_file() else root / "miniprogram/src/pages.json"


def _source_manifest(manifest, content):
    """Normalize legacy manifests in the bundle, preserving the source checkout."""
    files = tuple(name for name in manifest.package_files if not is_generated_ai_snapshot(name))
    if files == manifest.package_files:
        return manifest, content
    text, count = re.subn(r"(?m)^package_files\s*=\s*\[[\s\S]*?\]",
        lambda _: "package_files = " + json.dumps(files, ensure_ascii=False),
        content.decode("utf-8"), count=1)
    if count != 1:
        raise ValueError("无法移除旧清单中的环境快照声明")
    return replace(manifest, package_files=files), text.encode("utf-8")


def _migration_ready(contents, manifest):
    """Read revision literals without importing or running any packaged Python."""
    prefix = "plugins/core/backend/" + manifest.migration_location + "/" if manifest.migration_location else None
    sources = {name: data for name, data in contents.items() if prefix and name.startswith(prefix) and name.endswith(".py") and not name.endswith("/__init__.py")}
    if not sources:
        return False
    revisions, parents, roots = {}, set(), []
    for name, data in sources.items():
        tree = ast.parse(data, filename=name)
        fields = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {"revision", "down_revision", "branch_labels", "depends_on"}:
                fields[node.targets[0].id] = ast.literal_eval(node.value)
        revision = fields.get("revision")
        if not isinstance(revision, str) or not revision or revision in revisions or "down_revision" not in fields:
            raise ValueError(f"插件迁移版本声明无效：{name}")
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        if not {"upgrade", "downgrade"} <= functions:
            raise ValueError(f"插件迁移缺少 upgrade/downgrade：{name}")
        down = fields["down_revision"]
        down = () if down is None else (down,) if isinstance(down, str) else down
        if not isinstance(down, tuple) or any(not isinstance(value, str) for value in down):
            raise ValueError(f"插件迁移父版本无效：{name}")
        if not down:
            labels = fields.get("branch_labels") or ()
            dependencies = fields.get("depends_on") or ()
            labels = (labels,) if isinstance(labels, str) else labels
            dependencies = (dependencies,) if isinstance(dependencies, str) else dependencies
            if labels != (manifest.key,) or "core_0001" not in dependencies:
                raise ValueError("插件初始迁移必须独立分支并依赖 core_0001")
            roots.append(revision)
        revisions[revision] = down
        parents.update(down)
    if len(roots) != 1 or not parents <= revisions.keys() or len(revisions.keys() - parents) != 1:
        raise ValueError("插件迁移必须是完整的单头独立分支")
    visited, visiting = set(), set()
    def visit(revision):
        if revision in visiting:
            raise ValueError("插件迁移存在循环")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in revisions[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)
    for revision in revisions:
        visit(revision)
    from dataclasses import replace
    for key in manifest.replaces:
        previous = replace(manifest, key=key, migration_location=f"alembic/versions/plugins/{key}", replaces=())
        if not _migration_ready(contents, previous):
            raise ValueError(f"缺少已合并插件 {key} 的完整历史迁移")
    return True


def pack_plugin(root: Path, key: str, output: Path, *, source_only=False):
    root = root.resolve()
    manifest = read_plugin_manifest(root / "plugins" / key / "plugin.toml")
    from app.framework.plugin_manifest import read_plugin_manifests
    if key not in {item.key for item in read_plugin_manifests(root)}:
        raise ValueError(f"插件 {key} 已被合并，不能独立打包")
    if (root / "plugins" / key / "suite.toml").is_file():
        from app.framework.plugin_suite import read_suite
        read_suite(root / "plugins" / key / "suite.toml")
    manifest_name = f"plugins/{key}/plugin.toml"
    manifest, manifest_content = _source_manifest(manifest, (root / manifest_name).read_bytes())
    roots, frontend = _roots(root, manifest)
    contents = {}
    for prefix in roots:
        directory = root / prefix
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"缺少插件目录或不能打包链接：{prefix}")
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if set(relative.parts) & SKIP or path.suffix == ".pyc" or _private_configuration(relative.as_posix(), manifest) or is_generated_ai_snapshot(relative.as_posix()):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"插件文件不能越界或使用链接：{relative}")
            if path.is_file():
                contents[_safe(relative.as_posix()).as_posix()] = path.read_bytes()
    for name in manifest.package_files:
        path = plugin_source_path(root, manifest, _safe(name).as_posix())
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"package_files 缺少文件或越界：{name}")
        contents[path.relative_to(root).as_posix()] = path.read_bytes()
    contents[manifest_name] = manifest_content
    migration_ready = _migration_ready(contents, manifest)
    if not migration_ready and not source_only:
        raise ValueError("尚无本插件迁移；先生成并审核迁移，或用 --source-only 导出待开发源码包")
    page_source = json.loads(miniapp_pages_path(root).read_text(encoding="utf-8"))
    pages = miniapp_registrations(page_source)
    registrations = [pages.get(page, {"path": page}) for page in frontend.get("miniapp_pages", [])]
    header = dict(format_version=1, plugin_key=manifest.key, version=manifest.version, migration_ready=migration_ready, files={name: _digest(content) for name, content in sorted(contents.items())}, miniapp_pages=registrations)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(HEADER, _json(header))
        for name, content in sorted(contents.items()):
            archive.writestr(name, content)
    return dict(plugin_key=key, version=manifest.version, files=len(contents), migration_ready=migration_ready, output=str(output))


@contextmanager
def _read_bundle(root, package):
    temporary_root = (root / "plugins/core/backend/.generated/plugin-packages").resolve()
    if not temporary_root.is_relative_to(root):
        raise ValueError("暂存路径越界")
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inspect-", dir=temporary_root) as temporary:
        stage = Path(temporary).resolve()
        if not stage.is_relative_to(temporary_root):
            raise ValueError("暂存路径越界")
        with zipfile.ZipFile(package) as archive:
            items = archive.infolist()
            names = [item.filename for item in items]
            if len(items) > 5000 or sum(item.file_size for item in items) > 100 * 1024 * 1024 or len({name.casefold() for name in names}) != len(names):
                raise ValueError("插件包过大或有重复文件")
            if HEADER not in names:
                raise ValueError("缺少插件包描述文件")
            header = json.loads(archive.read(HEADER))
            if not isinstance(header, dict) or set(header) != {"format_version", "plugin_key", "version", "migration_ready", "files", "miniapp_pages"} or header["format_version"] != 1 or type(header["migration_ready"]) is not bool or not isinstance(header["files"], dict):
                raise ValueError("插件包描述格式无效")
            if set(names) != {HEADER, *header["files"]}:
                raise ValueError("插件包文件列表不一致")
            for name, expected in header["files"].items():
                relative = _safe(name)
                content = archive.read(name)
                if _digest(content) != expected:
                    raise ValueError(f"文件校验失败：{name}")
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        # Only parse metadata; installing a bundle does not import its Python code.
        key = header["plugin_key"]
        if not isinstance(key, str) or not key.isascii() or not key.replace("_", "").isalnum() or not key[0].islower():
            raise ValueError("插件标识无效")
        manifest = read_plugin_manifest(stage / "plugins" / key / "plugin.toml")
        if (stage / "plugins" / key / "suite.toml").is_file():
            from app.framework.plugin_suite import read_suite
            read_suite(stage / "plugins" / key / "suite.toml")
        roots, frontend = _roots(stage, manifest)
        if manifest.version != header["version"] or any(not _owned(name, roots, manifest.package_files) for name in header["files"]):
            raise ValueError("插件包版本或文件归属无效，禁止覆盖底座")
        if any(_private_configuration(name, manifest) for name in header["files"]):
            raise ValueError("插件包不能包含实际环境配置，只能携带声明的配置模板")
        for extra in manifest.package_files:
            if plugin_source_path(stage, manifest, extra).relative_to(stage).as_posix() not in header["files"]:
                raise ValueError(f"插件包缺少声明的文件：{extra}")
        for prefix in roots:
            if not (stage / prefix).is_dir():
                raise ValueError(f"插件包缺少目录：{prefix}")
        if manifest.source_layout == "contained":
            module_namespace_paths([], root=stage)
            module_namespace_paths([], namespace="integrations", root=stage)
        registrations = header["miniapp_pages"]
        if not isinstance(registrations, list) or any(not isinstance(item, dict) or not {"path"} <= item.keys() or item.keys() - {"path", "style", "subpackage_root"} for item in registrations) or [item["path"] for item in registrations] != frontend.get("miniapp_pages", []):
            raise ValueError("插件包移动页面登记不一致")
        merge_miniapp_registrations({'pages': []}, registrations)
        for page in frontend.get("miniapp_pages", []):
            if not plugin_source_path(stage, manifest, f"miniprogram/src/{page}.vue").is_file():
                raise ValueError(f"插件包缺少移动页面：{page}")
        migration_ready = _migration_ready({name: (stage / name).read_bytes() for name in header["files"]}, manifest)
        if migration_ready != header["migration_ready"]:
            raise ValueError("迁移状态与源码不一致")
        # Old archives are still hash/ownership checked above. Their environment
        # snapshots must never overwrite metadata generated by the installing host.
        manifest_name = f"plugins/{manifest.key}/plugin.toml"
        manifest, content = _source_manifest(manifest, (stage / manifest_name).read_bytes())
        (stage / manifest_name).write_bytes(content)
        header = {**header, "files": {
            name: _digest(content) if name == manifest_name else value
            for name, value in header["files"].items() if not is_generated_ai_snapshot(name)
        }}
        yield stage, manifest, frontend, header


def inspect_package(root: Path, package: Path):
    with _read_bundle(root.resolve(), package) as (_, manifest, _, header):
        return dict(plugin_key=manifest.key, version=manifest.version, requires=list(manifest.requires), files=len(header["files"]), migration_ready=header["migration_ready"])


def install_package(root: Path, package: Path, *, deploy=False, dry_run=False, source_only=False):
    root = root.resolve()
    with _read_bundle(root, package) as (stage, manifest, frontend, header):
        installed_path = root / "plugins" / manifest.key / "plugin.toml"
        if installed_path.is_file():
            installed = read_plugin_manifest(installed_path)
            if installed.source_layout != manifest.source_layout:
                raise ValueError(f"{manifest.key}: 源码布局不同；旧目录请先执行 scripts/erp.py relocate {manifest.key}，不允许直接覆盖或退回旧布局")
        if not header["migration_ready"] and not source_only:
            raise ValueError("这是待开发源码包，尚无迁移；使用 --source-only 仅导入源码，不能直接给租户开通")
        candidates = active_plugin_manifests([read_plugin_manifest(path) for path in (root / "plugins").glob("*/plugin.toml") if path.parent.name != manifest.key] + [manifest])
        modules, views, mobile, extras = {}, {}, {}, {}
        for item in candidates:
            source_root = stage if item.key == manifest.key else root
            _, definition = _roots(source_root, item)
            for values, mapping in ((item.module_names, modules), (definition.get("web_view_roots", []), views), ({str(PurePosixPath(page).parent) for page in definition.get("miniapp_pages", [])}, mobile), (item.package_files, extras)):
                for value in values:
                    if value in mapping:
                        raise ValueError(f"插件归属冲突：{value} ({mapping[value]}, {item.key})")
                    mapping[value] = item.key
        deployment_path = root / "deployment.json"
        deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
        if set(deployment) != {"format_version", "plugins"} or deployment["format_version"] != 1 or not isinstance(deployment["plugins"], list) or len(set(deployment["plugins"])) != len(deployment["plugins"]):
            raise ValueError("当前部署配置无效")
        selected = set(deployment["plugins"])
        available = {item.key: item for item in candidates}
        closure = {manifest.key}
        def dependencies(key):
            if key not in available:
                raise ValueError(f"请先导入依赖插件：{key}")
            for spec in available[key].requires:
                dependency = spec.split(">=", 1)[0]
                if dependency not in closure:
                    closure.add(dependency)
                    dependencies(dependency)
        dependencies(manifest.key)
        resolve_plugin_manifests(closure | selected, tuple(candidates))
        if deploy:
            selected |= closure
            selected = set(canonical_plugin_keys(selected, candidates))
        receipt_path = root / ".plugin-lock.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"format_version": 1, "plugins": {}}
        if not isinstance(receipt, dict) or receipt.get("format_version") != 1 or not isinstance(receipt.get("plugins"), dict):
            raise ValueError("插件安装记录格式无效")
        previous = receipt["plugins"].get(manifest.key, {}).get("files", {})
        approved_previous = {name: digest for key in manifest.replaces
                             for name, digest in receipt["plugins"].get(key, {}).get("files", {}).items()}
        approved_previous.update(previous)
        if any((root / name).exists() for name in previous.keys() - header["files"].keys()
               if not is_generated_ai_snapshot(name)):
            raise ValueError("新版本移除了已安装文件，请先明确处理这些旧文件；导入器不会自动删除源码")
        writes, before = {}, {}
        for name, digest in header["files"].items():
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"目标不能越界或为链接：{name}")
            old = path.read_bytes() if path.is_file() else None
            if old is not None and _digest(old) not in {digest, approved_previous.get(name)}:
                raise ValueError(f"目标有未登记或本地修改的文件，不覆盖：{name}")
            if old is None or _digest(old) != digest:
                writes[path] = (stage / name).read_bytes()
                before[path] = old
        pages_path = miniapp_pages_path(root)
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        existing = set(miniapp_registrations(pages))
        additions = [item for item in header["miniapp_pages"] if item["path"] not in existing]
        pages_changed = merge_miniapp_registrations(pages, header["miniapp_pages"])
        receipt["plugins"][manifest.key] = dict(version=manifest.version, migration_ready=header["migration_ready"], files=header["files"])
        configs = {receipt_path: _json(receipt)}
        if pages_changed:
            configs[pages_path] = _json(pages)
        if deploy:
            configs[deployment_path] = _json(dict(format_version=1, plugins=sorted(selected)))
        for path, content in configs.items():
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("配置文件路径越界或为链接")
            before[path] = path.read_bytes() if path.exists() else None
            if before[path] != content:
                writes[path] = content
        report = dict(plugin_key=manifest.key, version=manifest.version, dry_run=dry_run, source_files=len(header["files"]), changed_files=len(writes), registered_pages=[item["path"] for item in additions], deployed=deploy, migration_ready=header["migration_ready"], database_changed=False)
        if dry_run:
            return report
        applied = []
        try:
            for path, content in writes.items():
                if (path.read_bytes() if path.exists() else None) != before[path]:
                    raise ValueError(f"导入期间目标被修改：{path.relative_to(root)}")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".plugin-import-tmp")
                with temporary.open("xb") as output:
                    try:
                        output.write(content)
                    except Exception:
                        output.close()
                        temporary.unlink()
                        raise
                try:
                    os.replace(temporary, path)
                except Exception:
                    temporary.unlink()
                    raise
                applied.append(path)
        except Exception:
            for path in reversed(applied):
                if before[path] is None:
                    path.unlink()
                else:
                    path.write_bytes(before[path])
            raise
        return report
