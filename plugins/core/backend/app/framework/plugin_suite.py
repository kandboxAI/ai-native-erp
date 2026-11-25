"""Source delivery suites: resolve existing plugins without adding runtime ownership."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
import zipfile

from app.framework.plugin_manifest import read_plugin_manifest, resolve_plugin_manifests, read_plugin_manifests

ROOT = Path(__file__).resolve().parents[5]
HEADER = "erp-suite-package.json"


@dataclass(frozen=True)
class PluginSuite:
    key: str
    name: str
    version: str
    plugins: tuple[str, ...]
    desktop: dict | None = None


def read_suite(path: Path) -> PluginSuite:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(data) - {"format_version", "key", "name", "version", "plugins", "desktop"} or not {"format_version", "key", "name", "version", "plugins"} <= set(data) or data["format_version"] != 1:
        raise ValueError("套件声明字段无效")
    if data["key"] != path.parent.name or not re.fullmatch(r"[a-z][a-z0-9_]*", data["key"]):
        raise ValueError("套件 key 必须与拥有插件目录一致")
    if not isinstance(data["name"], str) or not data["name"].strip() or not re.fullmatch(r"\d+(?:\.\d+){1,2}", data["version"]):
        raise ValueError("套件名称或版本无效")
    plugins = data["plugins"]
    if not isinstance(plugins, list) or not plugins or any(not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in plugins) or len(set(plugins)) != len(plugins) or data["key"] not in plugins:
        raise ValueError("套件必须声明唯一的根插件，并包含拥有插件")
    owner = read_plugin_manifest(path.with_name("plugin.toml"))
    if owner.version != data["version"]:
        raise ValueError("套件版本必须与拥有插件版本一致")
    desktop = data.get("desktop")
    if desktop is not None:
        required = {"product_name", "app_id", "artifact_prefix"}
        if not isinstance(desktop, dict) or not required <= desktop.keys() or desktop.keys() - required - {"icon"}:
            raise ValueError("套件 desktop 字段无效")
        if any(not isinstance(value, str) or not value.strip() or value != value.strip() or any(ord(char) < 32 for char in value) for value in desktop.values()):
            raise ValueError("套件 desktop 配置必须是非空文本")
        if re.search(r'[<>:"/\\|?*]', desktop["product_name"]) or len(desktop["product_name"]) > 80:
            raise ValueError("客户端名称不能含文件路径字符，长度最多 80")
        if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", desktop["app_id"]):
            raise ValueError("客户端 app_id 必须是反向域名格式")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", desktop["artifact_prefix"]):
            raise ValueError("安装包前缀必须是小写英文、数字或连字符")
        if "icon" in desktop:
            icon = Path(desktop["icon"])
            if icon.is_absolute() or ".." in icon.parts or "\\" in desktop["icon"] or ":" in desktop["icon"] or icon.suffix.lower() != ".png":
                raise ValueError("客户端图标必须是插件内的相对 PNG 路径")
    return PluginSuite(data["key"], data["name"], data["version"], tuple(plugins), desktop)


def suite_plan(root: Path, key: str) -> tuple[PluginSuite, tuple]:
    if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError("套件 key 无效")
    root = root.resolve()
    suite = read_suite(root / "plugins" / key / "suite.toml")
    candidates = read_plugin_manifests(root)
    available = {item.key: item for item in candidates}
    closure = set()

    def visit(plugin_key):
        if plugin_key in closure:
            return
        if plugin_key not in available:
            raise ValueError(f"套件缺少源码插件：{plugin_key}；请使用完整套件包导入")
        closure.add(plugin_key)
        for requirement in available[plugin_key].requires:
            visit(requirement.split(">=", 1)[0])

    for plugin_key in suite.plugins:
        visit(plugin_key)
    return suite, resolve_plugin_manifests(closure, candidates)


def deployed_suites() -> tuple[tuple[PluginSuite, tuple], ...]:
    from app.framework.plugin import loaded_plugin_manifests
    loaded = {item.key for item in loaded_plugin_manifests()}
    result = []
    for key in sorted(loaded):
        path = ROOT / "plugins" / key / "suite.toml"
        if path.is_file():
            suite, manifests = suite_plan(ROOT, key)
            if not {item.key for item in manifests} <= loaded:
                raise ValueError(f"套件 {key} 尚未全部选入部署")
            result.append((suite, manifests))
    return tuple(result)


def plan_report(root: Path, key: str) -> dict:
    suite, manifests = suite_plan(root, key)
    return {"suite_key": suite.key, "name": suite.name, "version": suite.version,
            "roots": list(suite.plugins), "plugins": [item.key for item in manifests],
            "database_changed": False}


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _apply(root, writes, before):
    """Preflight every destination, then atomically replace files; roll back on error."""
    for name in writes:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"套件目标路径越界或为链接：{name}")
        if (path.read_bytes() if path.exists() else None) != before[name]:
            raise ValueError(f"套件导入期间文件被修改：{name}")
    applied = []
    try:
        for name, content in writes.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, prefix=".suite-") as file:
                temporary = Path(file.name)
                file.write(content)
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            applied.append(name)
    except Exception:
        for name in reversed(applied):
            if before[name] is None:
                (root / name).unlink()
            else:
                (root / name).write_bytes(before[name])
        raise


def deploy_suite(root: Path, key: str, *, dry_run=False) -> dict:
    root = root.resolve()
    suite, manifests = suite_plan(root, key)
    name = "deployment.json"
    original = (root / name).read_bytes()
    data = json.loads(original)
    if set(data) != {"format_version", "plugins"} or data["format_version"] != 1 or not isinstance(data["plugins"], list):
        raise ValueError("当前部署配置无效")
    selected = set(data["plugins"]) | {item.key for item in manifests}
    candidates = read_plugin_manifests(root)
    selected = {item.key for item in resolve_plugin_manifests(selected, candidates)}
    report = {**plan_report(root, suite.key), "deployment_plugins": sorted(selected), "dry_run": dry_run}
    if not dry_run:
        _apply(root, {name: _json({"format_version": 1, "plugins": sorted(selected)})}, {name: original})
    return report


def pack_suite(root: Path, key: str, output: Path, *, source_only=False) -> dict:
    from app.framework.plugin_package import pack_plugin
    suite, manifests = suite_plan(root, key)
    # All nested packages must validate before an outer deliverable is created.
    with tempfile.TemporaryDirectory(prefix="erp-suite-") as directory:
        contents, entries = {}, []
        for manifest in manifests:
            name = f"{manifest.key}-{manifest.version}.zip"
            path = Path(directory) / name
            report = pack_plugin(root, manifest.key, path, source_only=source_only)
            content = path.read_bytes()
            contents[name] = content
            entries.append({"file": name, "plugin_key": manifest.key, "sha256": hashlib.sha256(content).hexdigest(),
                            "migration_ready": report["migration_ready"]})
        header = {"format_version": 1, "suite_key": suite.key, "version": suite.version, "packages": entries}
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(HEADER, _json(header))
            for name, content in contents.items():
                archive.writestr(name, content)
    return {**plan_report(root, key), "migration_ready": all(item["migration_ready"] for item in entries), "output": str(output)}


@contextmanager
def _read_suite_package(root, package):
    from app.framework.plugin_package import _read_bundle
    with tempfile.TemporaryDirectory(prefix="erp-suite-") as temporary, ExitStack() as stack:
        directory = Path(temporary)
        with zipfile.ZipFile(package) as archive:
            items = archive.infolist()
            if len(items) > 101 or sum(item.file_size for item in items) > 300 * 1024 * 1024 or len({item.filename.casefold() for item in items}) != len(items):
                raise ValueError("套件包过大或存在重复文件")
            header = json.loads(archive.read(HEADER))
            if set(header) != {"format_version", "suite_key", "version", "packages"} or header["format_version"] != 1 or not isinstance(header["packages"], list) or not header["packages"]:
                raise ValueError("套件包描述无效")
            entries = header["packages"]
            if any(not isinstance(item, dict) or set(item) != {"file", "plugin_key", "sha256", "migration_ready"} for item in entries):
                raise ValueError("套件包条目无效")
            if {item.filename for item in items} != {HEADER, *(item["file"] for item in entries)} or len({item["plugin_key"] for item in entries}) != len(entries) or len({item["file"] for item in entries}) != len(entries):
                raise ValueError("套件包清单不一致")
            bundles = []
            for entry in entries:
                name = entry["file"]
                if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*-\d+(?:\.\d+){1,2}\.zip", name):
                    raise ValueError("套件子包路径无效")
                content = archive.read(name)
                if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                    raise ValueError("套件子包校验失败")
                path = directory / name
                path.write_bytes(content)
                bundle = stack.enter_context(_read_bundle(root, path))
                if bundle[1].key != entry["plugin_key"] or bundle[3]["migration_ready"] != entry["migration_ready"]:
                    raise ValueError("套件子包声明不一致")
                bundles.append((path, bundle))
        owner = next((bundle for _, bundle in bundles if bundle[1].key == header["suite_key"]), None)
        if owner is None:
            raise ValueError("套件缺少拥有插件")
        suite = read_suite(owner[0] / "plugins" / header["suite_key"] / "suite.toml")
        manifests = tuple(bundle[1] for _, bundle in bundles)
        ordered = resolve_plugin_manifests({item.key for item in manifests}, manifests)
        # Require exactly the declared roots and transitive dependencies, no extra payload.
        available = {item.key: item for item in manifests}
        closure = set(suite.plugins)
        pending = list(closure)
        while pending:
            key = pending.pop()
            if key not in available:
                raise ValueError(f"套件缺少根插件：{key}")
            for requirement in available[key].requires:
                dependency = requirement.split(">=", 1)[0]
                if dependency not in closure:
                    closure.add(dependency)
                    pending.append(dependency)
        if closure != set(available) or suite.version != header["version"]:
            raise ValueError("套件包含未声明插件或版本不一致")
        by_key = {bundle[1].key: (path, bundle) for path, bundle in bundles}
        yield suite, [by_key[item.key] for item in ordered]


def install_suite(root: Path, package: Path, *, deploy=False, dry_run=False, source_only=False) -> dict:
    """Validate the entire import in isolation, then apply one reversible file transaction."""
    from app.framework.plugin_package import install_package, miniapp_pages_path
    root = root.resolve()
    with _read_suite_package(root, package) as (suite, bundles), tempfile.TemporaryDirectory(prefix="erp-suite-install-") as temporary:
        stage = Path(temporary)
        names = {"deployment.json", miniapp_pages_path(root).relative_to(root).as_posix(), ".plugin-lock.json"}
        for path in (root / "plugins").glob("*/plugin.toml"):
            item = read_plugin_manifest(path)
            names.add(path.relative_to(root).as_posix())
            if item.frontend_manifest:
                names.add(f"plugins/{item.key}/{item.frontend_manifest}")
        for _, (_, _, _, header) in bundles:
            names.update(header["files"])
        receipt = root / ".plugin-lock.json"
        if receipt.exists():
            for record in json.loads(receipt.read_bytes())["plugins"].values():
                names.update(record["files"])
        before = {}
        for name in names:
            from app.framework.plugin_package import _safe
            _safe(name)
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"套件目标路径越界或为链接：{name}")
            content = path.read_bytes() if path.is_file() else None
            before[name] = content
            if content is not None:
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        for path, _ in bundles:
            install_package(stage, path, source_only=source_only)
        if deploy:
            deploy_suite(stage, suite.key)
        writes = {name: (stage / name).read_bytes() for name in names
                  if (stage / name).is_file() and (stage / name).read_bytes() != before[name]}
        report = {"suite_key": suite.key, "version": suite.version, "plugins": [bundle[1].key for _, bundle in bundles],
                  "migration_ready": all(bundle[3]["migration_ready"] for _, bundle in bundles),
                  "changed_files": len(writes), "deployed": deploy, "dry_run": dry_run, "database_changed": False}
        if not dry_run:
            _apply(root, writes, before)
        return report
