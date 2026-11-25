"""Move declared source ownership into a plugin, without SQL or migration rewrites."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from app.framework.plugin_manifest import read_plugin_manifest, read_frontend_manifest
from app.framework.plugin_sources import plugin_source_path

TEXT = {".ts", ".tsx", ".js", ".vue", ".scss", ".css"}
REFERENCE = re.compile(r'''(["'])(@/[^"'\n]+|\.{1,2}/[^"'\n]+)\1''')


def relocate_plugin(root: Path, key: str, *, dry_run=False) -> dict:
    """Preflight every move; preserve import names, baselines, versions and local edits."""
    root = root.resolve()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError("插件标识无效")
    manifest_path = root / "plugins" / key / "plugin.toml"
    manifest = read_plugin_manifest(manifest_path)
    if manifest.source_layout == "contained":
        return dict(plugin_key=key, source_layout="contained", changed_files=0, database_changed=False)
    frontend = read_frontend_manifest(manifest_path.parent / manifest.frontend_manifest)
    roots = [f"backend/app/modules/{name}" for name in manifest.module_names]
    roots += [f"web/src/views/{name}" for name in frontend["web_view_roots"]]
    roots += sorted({f"miniprogram/src/{PurePosixPath(page).parent}" for page in frontend["miniapp_pages"]})
    files = set(manifest.package_files)
    for logical in roots:
        directory = root / logical
        if not directory.is_dir() or directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise ValueError(f"缺少源码目录或路径越界：{logical}")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"源码不能为链接：{path}")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.add(path.relative_to(root).as_posix())
    contained = replace(manifest, source_layout="contained")
    moves = {}
    for logical in sorted(files):
        source = root / logical
        target = plugin_source_path(root, contained, logical)
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f"缺少源码或路径越界：{logical}")
        if source == target:
            continue
        if target.exists():
            raise ValueError(f"目标已存在，拒绝覆盖：{target.relative_to(root)}")
        moves[source] = target

    def candidate(logical):
        path = root / logical
        return next((value for value in [path, *(Path(str(path) + suffix) for suffix in (".ts", ".tsx", ".vue", ".js", ".json", ".scss")), *(path / ("index" + suffix) for suffix in (".ts", ".vue", ".tsx"))] if value.is_file()), None)

    writes = {}
    originals = {}
    # Rewrite inbound frontend imports as well as imports leaving a moved page.
    sources = set(moves)
    for base in (root / "web/src", root / "miniprogram/src", root / "plugins"):
        sources.update(path for path in base.rglob("*") if path.suffix in TEXT and "node_modules" not in path.parts)
    for source in sorted(sources):
        if source.suffix not in TEXT:
            continue
        logical = source.relative_to(root).as_posix()
        if logical.startswith("plugins/"):
            parts = logical.split("/", 2)
            logical = parts[2]
        side = next((side for side in ("web", "miniprogram") if logical.startswith(side + "/src/")), None)
        if not side:
            continue
        before = source.read_text(encoding="utf-8")

        def reference(match):
            value = match[2]
            if "${" in value or "*" in value:
                return match[0]
            value_path, separator, query = value.partition("?")
            referenced = (root / side / "src" / value_path[2:]) if value_path.startswith("@/") else (root / logical).parent / value_path
            referenced = referenced.resolve()
            if not referenced.is_relative_to(root):
                return match[0]
            target = candidate(referenced.relative_to(root))
            if target is None:
                return match[0]
            destination = moves.get(target, target)
            if value_path.startswith(".") and source in moves and target in moves:
                return match[0]  # Relative imports inside the same moved tree remain valid.
            if destination != target:
                new_reference = "@plugins/" + destination.relative_to(root / "plugins").as_posix()
            elif source in moves and value_path.startswith(".") and not target.is_relative_to(manifest_path.parent):
                base = root / side / "src"
                if not target.is_relative_to(base):
                    return match[0]
                new_reference = "@/" + target.relative_to(base).as_posix()
            else:
                return match[0]
            if target.suffix in {".ts", ".tsx", ".js"} and not value_path.endswith(target.suffix):
                new_reference = new_reference[:-len(target.suffix)]
            return match[1] + new_reference + (separator + query if separator else "") + match[1]

        after = REFERENCE.sub(reference, before)
        if after != before:
            writes[moves.get(source, source)] = after.encode("utf-8")
            originals[source] = source.read_bytes()
    original_manifest = manifest_path.read_bytes()
    text = original_manifest.decode("utf-8")
    if re.search(r"(?m)^source_layout\s*=", text):
        text = re.sub(r"(?m)^source_layout\s*=.*$", 'source_layout = "contained"', text)
    else:
        text = 'source_layout = "contained"\n' + text
    writes[manifest_path] = text.encode("utf-8")
    originals[manifest_path] = original_manifest
    receipt_path = root / ".plugin-lock.json"
    if receipt_path.is_file():
        receipt_before = receipt_path.read_bytes()
        receipt = json.loads(receipt_before)
        for record in receipt.get("plugins", {}).values():
            # Include inbound imports in other installed plugins. Mechanical
            # edits become installed content only when the file was pristine;
            # pre-existing developer edits retain their overwrite protection.
            files = {}
            for name, digest in record.get("files", {}).items():
                source = root / name
                target = moves.get(source, source)
                if target in writes and source in originals:
                    if digest == hashlib.sha256(originals[source]).hexdigest():
                        digest = hashlib.sha256(writes[target]).hexdigest()
                files[target.relative_to(root).as_posix()] = digest
            record["files"] = files
        if receipt.get("plugins"):
            originals[receipt_path] = receipt_before
            writes[receipt_path] = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    report = dict(plugin_key=key, source_layout="contained", moved_files=len(moves), rewritten_files=len(writes), dry_run=dry_run, database_changed=False, migration_changed=False)
    if dry_run:
        return report
    moved = []
    try:
        for source, target in moves.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            moved.append((source, target))
        for path, content in writes.items():
            path.write_bytes(content)
    except Exception:
        for source, target in reversed(moved):
            target.rename(source)
        for path, content in originals.items():
            path.write_bytes(content)
        raise
    # Only prune empty source directories inside the checked workspace; never delete data.
    for logical in sorted(roots, key=len, reverse=True):
        directory = root / logical
        for path in sorted(directory.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return report
