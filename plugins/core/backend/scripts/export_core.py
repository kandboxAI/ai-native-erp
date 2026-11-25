"""Export an MIT core source tree. No database access, builds or dependency installs.

Only allowlisted backend modules and reachable frontend source files are copied.
Refuses existing destinations, local env files, symlinks and dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = Path(__file__).resolve().parents[4]
SKIP = {"__pycache__", "node_modules", ".git", ".venv", "dist", ".deployment-input",
        ".generated", ".local-migrations", ".private-plugins", ".pytest_cache", "storage", "legacy"}
TEXT = {".vue", ".ts", ".tsx", ".js", ".mjs", ".scss", ".css"}
LOCAL_REFERENCE = re.compile(r'''["']((?:@/|@build/|\./|\.\./)[^"'\n]+)["']''')


def release_markers() -> tuple[str, ...]:
    """读取发布者的本地标识清单，每行一个需排除的文本。"""
    configured = os.environ.get("ERP_RELEASE_MARKERS_FILE")
    path = Path(configured) if configured else REPO / "release-markers.local.txt"
    if not configured and not path.exists():
        return ()
    if not path.is_file():
        raise ValueError("ERP_RELEASE_MARKERS_FILE 必须指向本地文本文件")
    return tuple(line.strip().casefold() for line in path.read_text(encoding="utf-8-sig").splitlines()
                 if line.strip())


def check_public_source(directory: Path) -> None:
    """拒绝包含已知客户标识的发行文件；错误只报告路径，不打印文件内容。"""
    markers = release_markers()
    if not markers:
        return
    text_types = TEXT | {'.py', '.json', '.md', '.yml', '.yaml', '.toml', '.txt', '.html', '.svg', '.example', '.ps1', '.sh'}
    violations = []
    for path in directory.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        content = path.read_text(encoding="utf-8").casefold() if path.suffix in text_types else ""
        if any(marker in relative.casefold() or marker in content for marker in markers):
            violations.append(relative)
    if violations:
        raise ValueError(f'开源源码仍含客户标识：{", ".join(sorted(violations))}')


@lru_cache(maxsize=4)
def source_allowlist(root: Path) -> dict:
    policy = json.loads((root / "backend/scripts/core_source_allowlist.json").read_text(encoding="utf-8"))
    groups = {"backend_tests", "web_tests", "web_support", "web_assets", "web_styles", "web_shared_entries", "miniapp_support"}
    if policy.get("format_version") != 1 or set(policy) != groups | {"format_version"}:
        raise ValueError("开源导出白名单格式无效")
    seen = set()
    prefixes = {"backend_tests": ("backend/tests/",), "web_tests": ("web/tests/",),
        "web_support": ("web/build/", "web/types/", "web/locales/"),
        "web_assets": ("web/src/assets/",), "web_styles": ("web/src/style/",),
        "web_shared_entries": ("web/src/components/", "web/src/utils/", "web/src/api/", "web/src/composables/"),
        "miniapp_support": ("miniprogram/scripts/", "miniprogram/src/styles/", "miniprogram/src/static/")}
    for group in groups:
        if not isinstance(policy[group], list):
            raise ValueError(f"白名单必须是文件列表：{group}")
        for name in policy[group]:
            if not isinstance(name, str) or not name.startswith(prefixes[group]):
                raise ValueError(f"白名单文件不属于声明范围：{group}")
            path = Path(name)
            if (not isinstance(name, str) or path.is_absolute() or path.as_posix() != name
                    or '..' in path.parts or ':' in name or '\\' in name or name in seen):
                raise ValueError(f"白名单路径无效或重复：{name}")
            seen.add(name)
    return policy


def copy_reviewed(destination: Path, *groups: str) -> None:
    policy = source_allowlist(ROOT)
    for group in groups:
        for relative in policy[group]:
            source = ROOT / relative
            if not source.is_file():
                raise ValueError(f"白名单文件缺失：{relative}")
            copy_file(source, destination / relative)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_file(source: Path, target: Path) -> None:
    relative = source.absolute().relative_to(ROOT)
    for path in (source, *source.parents):
        if path == ROOT.parent:
            break
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"不能导出符号链接或目录联接：{source}")
    if (set(relative.parts) & SKIP or source.name.endswith(('.pyc', '.generated.json'))
            or (source.name.startswith('.env') and relative.as_posix() != 'backend/.env.core.example')):
        raise ValueError(f"本地文件不能进入源码发行版：{relative}")
    guarded = ("backend/tests/", "web/tests/", "web/src/assets/", "web/src/style/",
               "web/build/", "web/types/", "web/locales/", "miniprogram/scripts/",
               "miniprogram/src/styles/", "miniprogram/src/static/")
    if relative.as_posix().startswith(guarded):
        reviewed = {name for key, names in source_allowlist(ROOT).items() if key != 'format_version' for name in names}
        if relative.as_posix() not in reviewed:
            raise ValueError(f"静态资源或测试尚未登记开源白名单：{relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_repo_file(name: str, target: Path) -> None:
    """复制仓库根目录的发行文件；它们位于 plugins/core 源码树之外。"""
    source = REPO / name
    if not source.is_file():
        raise ValueError(f"发行文件缺失：{name}")
    for path in (source, *source.parents):
        if path == REPO.parent:
            break
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"不能导出符号链接或目录联接：{source}")
    if source.name.startswith(".env") or source.suffix == ".pyc":
        raise ValueError(f"本地文件不能进入源码发行版：{name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_tree(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if set(relative.parts) & SKIP or path.name.startswith(".env"):
            continue
        if path.is_symlink():
            raise ValueError(f"不能导出符号链接：{path}")
        if path.is_file() and path.name != "demo_seed.py":
            copy_file(path, target / relative)


def copy_reachable(source: Path, target: Path, entries: list[Path], *, overlays: Path | None = None) -> None:
    """Follow literal local imports; glob entries are supplied explicitly by caller.

    A copied core page may not pull an industry page through a relative import.
    Unresolvable runtime URLs/glob patterns are not imports and are ignored.
    """
    queue = list(entries)
    seen = set()
    while queue:
        path = queue.pop().resolve()
        if path in seen or not path.is_file():
            continue
        if not path.is_relative_to(source):
            raise ValueError(f"前端底座依赖越界：{path}")
        seen.add(path)
        relative = path.relative_to(source)
        actual = overlays / relative if overlays and (overlays / relative).is_file() else path
        copy_file(actual, target / relative)
        if path.suffix not in TEXT:
            continue
        for reference in LOCAL_REFERENCE.findall(actual.read_text(encoding="utf-8")):
            reference = reference.split("?", 1)[0]
            if "*" in reference or "${" in reference:
                continue
            if reference.startswith("@build/"):
                continue  # build directory is exported separately
            base = source / reference[2:] if reference.startswith("@/") else path.parent / reference
            candidates = [base, *(Path(str(base) + suffix) for suffix in (".ts", ".tsx", ".js", ".vue", ".json")), *(base / ("index" + suffix) for suffix in (".ts", ".tsx", ".js", ".vue"))]
            resolved = next((item for item in candidates if item.is_file()), None)
            if resolved is not None:
                queue.append(resolved)


def copy_shared_web(destination: Path) -> None:
    """复制底座公共前端入口及其字面依赖闭包，不包含核心页面入口。"""
    web = ROOT / "web"
    entries = []
    for name in source_allowlist(ROOT)["web_shared_entries"]:
        entry = ROOT / name
        if not entry.is_file():
            raise ValueError(f"公共前端入口缺失：{name}")
        entries.append(entry)
    copy_reachable(web / "src", destination / "web/src", entries)


def _export_core_tree(destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists() or destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("导出目标必须是尚不存在的新目录，且不能是仓库或仓库的上级目录")
    manifest = json.loads((ROOT / "backend/app/framework/core_manifest.json").read_text(encoding="utf-8"))
    destination.mkdir(parents=True)
    for name in ("LICENSE", "LICENSE_SCOPE.md", "AGENTS.md", "deployment.test.mjs", "deployment.mjs", "plugin-frontends.mjs", "plugin-manifests.mjs", "plugin-sources.mjs", "frontend-deployment.mjs", "product-branding.mjs", "branding-schema.mjs", "product-branding.d.ts"):
        copy_repo_file(name, destination / name)
    for name in ("erp.py", "erp.ps1", "erp.sh", "package_erp_client.py"):
        copy_repo_file(f"scripts/{name}", destination / "scripts" / name)
    write_json(destination / "deployment.json", {"format_version": 1, "plugins": []})
    branding = json.loads((REPO / "product-branding.json").read_text(encoding="utf-8"))
    write_json(destination / "product-branding.json", {"default": branding["default"]})
    (destination / ".gitignore").write_text(".env\n.env.local\n.env.production\n.env.*.local\n/branding/profiles/\n/release-markers.local.txt\nbackend/config/plugin/*.env\n.venv/\nnode_modules/\ndist/\n__pycache__/\n.pytest_cache/\n.deployment-input/\n.generated/\n.local-migrations/\n.private-plugins/\nstorage/\nbackend/app/integrations/harness_http/*.generated.json\nbackend/app/integrations/harness_schema/*.generated.json\nplugins/*/legacy/*/harness_http.generated.json\nplugins/*/legacy/*/harness_schema.generated.json\n", encoding="utf-8")

    # The export contains no business module or historical business migration.
    for name in ("auth", "core", "db", "framework", "middleware"):
        copy_tree(ROOT / "backend/app" / name, destination / "backend/app" / name)
    for name in ("__init__.py", "main.py"):
        copy_file(ROOT / "backend/app" / name, destination / "backend/app" / name)
    for name in manifest["module_names"]:
        copy_tree(ROOT / "backend/app/modules" / name, destination / "backend/app/modules" / name)
    for name in ("rbac_repository_utils.py", "shared.py"):
        copy_file(ROOT / "backend/app/modules" / name, destination / "backend/app/modules" / name)
    copy_file(ROOT / "backend/app/modules/__init__.py", destination / "backend/app/modules/__init__.py")
    for path in (ROOT / "backend/app/integrations").glob("*.py"):
        copy_file(path, destination / "backend/app/integrations" / path.name)
    copy_file(ROOT / "backend/app/integrations/harness_http_policy.json", destination / "backend/app/integrations/harness_http_policy.json")
    for name in ("erp_discovery",):
        copy_tree(ROOT / "backend/app/integrations" / name, destination / "backend/app/integrations" / name)
    # Harness snapshots belong to the target environment, not the source export.
    for name in ("resource_discovery", "resource_query"):
        copy_tree(ROOT / "backend" / name, destination / "backend" / name)
    for name in ("env.py", "script.py.mako"):
        copy_file(ROOT / "backend/alembic" / name, destination / "backend/alembic" / name)
    for name in ("public", "core"):
        copy_tree(ROOT / "backend/alembic/versions" / name, destination / "backend/alembic/versions" / name)
    for name in ("requirements.txt", "requirements-server-assistant.txt"):
        copy_file(ROOT / "backend" / name, destination / "backend" / name)
    # Keep the tenant section used by bootstrap, pointing to the independent core tree.
    ini = (ROOT / "backend/alembic.ini").read_text(encoding="utf-8")
    ini = ini[ini.index("[public]"):]
    ini = re.sub(r"\[tenant_mes\].*?(?=\[alembic\])", "", ini, flags=re.S)
    ini = ini.replace("alembic/versions/tenant", "alembic/versions/core")
    (destination / "backend/alembic.ini").write_text(ini, encoding="utf-8")
    for name in ("bootstrap.py", "export_core.py", "core_source_allowlist.json", "check_server_assistant.py", "install_server_assistant_sdk.py"):
        copy_file(ROOT / "backend/scripts" / name, destination / "backend/scripts" / name)
    copy_file(ROOT / "backend/.env.core.example", destination / "backend/.env.example")
    copy_file(ROOT / "backend/.env.core.example", destination / "backend/.env.core.example")

    # Frontend: positive page roots, plus their literal dependency closure.
    web = ROOT / "web"
    copy_reviewed(destination, "web_support", "web_tests", "web_assets", "web_styles")
    entries = [web / "src/main.ts", web / "src/router/modules/home.ts", web / "src/router/modules/error.ts", web / "src/router/modules/remaining.ts", web / "src/api/systemFile.ts"]
    # 插件可依赖底座未直接使用的公共能力；显式发布入口及其依赖闭包。
    for name in source_allowlist(ROOT)["web_shared_entries"]:
        entry = ROOT / name
        if not entry.is_file():
            raise ValueError(f"公共前端入口缺失：{name}")
        entries.append(entry)
    for name in manifest["web_view_roots"]:
        entries.extend((web / "src/views" / name).rglob("*.*"))
    copy_reachable(web / "src", destination / "web/src", entries)
    copy_file(web / "src/router/deployedViews.d.ts", destination / "web/src/router/deployedViews.d.ts")
    for name in ("favicon.ico", "logo.svg", "platform-config.json"):
        copy_file(web / "public" / name, destination / "web/public" / name)
    for name in ("vite.config.ts", "tsconfig.json", "postcss.config.js", "index.html", "LICENSE", "pnpm-lock.yaml", "pnpm-workspace.yaml", ".npmrc"):
        copy_file(web / name, destination / "web" / name)
    package = json.loads((web / "package.json").read_text(encoding="utf-8"))
    package["name"] = "erp-foundation-web"
    package["scripts"] = {"dev": "vite", "build": "vite build", "typecheck": "vue-tsc --noEmit --skipLibCheck", "preview": "vite preview", "test:auth": package["scripts"]["test:auth"], "test:routes": package["scripts"]["test:routes"]}
    package["scripts"]["test:routes"] = "node --test tests/core-export-routes.test.mjs"
    write_json(destination / "web/package.json", package)
    (destination / "web/.env").write_text("VITE_PORT=8848\nVITE_PUBLIC_PATH=/\nVITE_ROUTER_HISTORY=hash\nVITE_HIDE_HOME=false\nVITE_API_BASE_URL=http://127.0.0.1:8000\n", encoding="utf-8")

    mini = ROOT / "miniprogram"
    entries = [mini / "src/main.ts", mini / "src/deployment.d.ts", mini / "src/pages/xiaohang/index.vue"]
    for path in (mini / "core").rglob("*.*"):
        # Overlay paths need not exist in the industry source (e.g. generic api/index.ts).
        relative = path.relative_to(mini / "core")
        placeholder = mini / "src" / relative
        entries.append(placeholder if placeholder.is_file() else path)
    # Materialize the generic input in a separate temporary-free source tree.
    # First copy shared dependencies from entry pages whose paths exist in src.
    copy_reachable(mini / "src", destination / "miniprogram/src", [p for p in entries if p.is_relative_to(mini / "src")], overlays=mini / "core")
    copy_tree(mini / "core", destination / "miniprogram/core")
    copy_tree(mini / "core", destination / "miniprogram/src")
    # Shared imports required only by new overlay files (and the common navigation shell).
    for name in ("api/client.ts", "store/pluginAccess.ts", "config/pluginServices.ts", "config/pluginProviders.ts", "config/roleServices.ts", "utils/tabbar.ts"):
        copy_reachable(mini / "src", destination / "miniprogram/src", [mini / "src" / name], overlays=mini / "core")
    copy_reviewed(destination, "miniapp_support")
    # Frontend helper exports the canonical list, so no industry page manifest is copied.
    paths = json.loads((ROOT / "backend/app/framework/miniapp_core.json").read_text(encoding="utf-8"))["pages"]
    pages = json.loads((mini / "src/pages.json").read_text(encoding="utf-8"))
    pages["pages"] = [page for page in pages["pages"] if page["path"] in paths]
    groups = [{**group, 'pages': [page for page in group['pages'] if f"{group['root']}/{page['path']}" in paths]}
              for group in pages.pop('subPackages', pages.pop('subpackages', []))]
    groups = [group for group in groups if group['pages']]
    if groups:
        pages['subPackages'] = groups
    pages["tabBar"]["list"] = [tab for tab in pages["tabBar"]["list"] if tab["pagePath"] in paths]
    for tab in pages["tabBar"]["list"]:
        if tab["pagePath"] == "pages/xiaohang/index": tab["text"] = branding["default"]["assistant_name"]
    pages["globalStyle"]["navigationBarTitleText"] = branding["default"]["title"]
    write_json(destination / "miniprogram/src/pages.json", pages)
    write_json(destination / "miniprogram/src/manifest.json", {"name": branding["default"]["title"], "appid": "", "description": branding["default"]["description"], "versionName": "1.0.0", "versionCode": "100", "mp-weixin": {"appid": "", "usingComponents": True}, "h5": {"title": branding["default"]["title"], "router": {"mode": "hash"}}})
    for name in ("index.html", "vite.config.ts", "tsconfig.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
        copy_file(mini / name, destination / "miniprogram" / name)
    package = json.loads((mini / "package.json").read_text(encoding="utf-8"))
    package.update(name="erp-foundation-miniprogram", description="管理底座移动端", license="MIT")
    package["scripts"] = {key: value for key, value in package["scripts"].items() if key in {"dev:h5", "build:h5", "build:mp-weixin", "typecheck"}}
    package["scripts"]["dev:mp-weixin"] = "node scripts/run-deployment.mjs -p mp-weixin"
    write_json(destination / "miniprogram/package.json", package)
    (destination / "miniprogram/.env.development").write_text("VITE_API_BASE_URL=http://127.0.0.1:8000\n", encoding="utf-8")
    (destination / "miniprogram/.env.production.example").write_text("VITE_API_BASE_URL=https://api.example.com\nWEIXIN_APPID=\n", encoding="utf-8")
    readme = (ROOT / "docs/core-open-source.md").read_text(encoding="utf-8").replace("](business-plugin-integration.md)", "](docs/business-plugin-integration.md)").replace("](open-source-conversion.md)", "](docs/open-source-conversion.md)").replace("](foundation-platform/", "](docs/foundation-platform/")
    for name in ("plugin-commands.md", "business-suites.md", "harness-sync.md", "plugin-development.md", "database-workflow.md", "developer-quickstart.md", "desktop-packaging.md"):
        readme = readme.replace(f"]({name})", f"](docs/{name})")
    readme = readme.replace("](../plugins/README.md)", "](plugins/README.md)")
    readme = readme.replace("](../LICENSE_SCOPE.md)", "](LICENSE_SCOPE.md)").replace("](open-source-release.md)", "](docs/open-source-release.md)")
    (destination / "README.md").write_text(readme, encoding="utf-8")
    foundation_documents = (
        "README.md", "core-architecture.md", "current-layered-architecture.md",
        "current-foundation-platform-design.md", "current-plugin-architecture.md", "core-database-design.md",
        "core-table-catalog.md", "database-naming-convention.md", "directory-naming-convention.md", "file-attachment-design.md",
    )
    for name in (
        "business-plugin-integration.md", "business-suites.md", "plugin-commands.md", "plugin-development.md", "harness-sync.md", "business-plugin-development-example.md", "plugin-script-conversion.md",
        "plugin-ai-onboarding.md", "legacy-business-plugin-porting.md", "business-plugin-reference.md",
        "core-open-source.md", "open-source-release.md", "desktop-packaging.md", "mes-plugin-integration.md", "open-source-conversion.md", "validation.md", "database-workflow.md", "developer-quickstart.md", "plugin-source-layout.md", "plugin-configuration.md",
        *("foundation-platform/" + name for name in foundation_documents),
    ):
        copy_file(ROOT / "docs" / name, destination / "docs" / name)
    copy_repo_file("plugins/README.md", destination / "plugins/README.md")
    copy_file(ROOT / "backend/pytest.ini", destination / "backend/pytest.ini")
    copy_reviewed(destination, "backend_tests")
    for name in ("docker-compose.yml",):
        copy_repo_file(name, destination / name)
    (destination / "THIRD_PARTY_NOTICES.md").write_text("管理端基于 vue-pure-admin，保留 web/LICENSE 中 pure-admin 的 MIT 声明。其余依赖各自保留原许可证；依赖未随本源码包分发。\n", encoding="utf-8")
    # The development repository keeps all designs together; core exports carry
    # only the explicit shared set. Explain omitted references instead of leaving
    # AGENTS and the design index with clickable links to absent industry files.
    for document in (destination / "README.md", destination / "AGENTS.md", destination / "plugins/README.md", *(destination / "docs").rglob("*.md")):
        def exported_link(match):
            label, reference = match.groups()
            if reference.startswith(("#", "http://", "https://", "mailto:")):
                return match.group(0)
            path = reference.split("#", 1)[0]
            if (document.parent / path).is_file():
                return match.group(0)
            return f"{label}（开发仓库/插件中的 `{reference}`，未随纯底座分发）"
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", exported_link, document.read_text(encoding="utf-8"))
        document.write_text(text, encoding="utf-8")
    check_public_source(destination)
    files = {str(path.relative_to(destination)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.rglob("*")) if path.is_file()}
    write_json(destination / "source-manifest.json", {"format_version": 1, "license": "MIT", "plugins": [],
        "allowlist_sha256": hashlib.sha256((ROOT / "backend/scripts/core_source_allowlist.json").read_bytes()).hexdigest(), "files": files})
    return destination


def export_core(destination: Path) -> Path:
    destination = destination.absolute()
    if destination.exists() or destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("导出目标必须是尚不存在的新目录，且不能是仓库或仓库的上级目录")
    if destination.is_relative_to(ROOT) and not destination.is_relative_to(ROOT / 'dist'):
        raise ValueError("仓库内仅允许导出到 dist/，避免将发行物写入源码目录")
    for parent in destination.parents:
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("导出目标不能经过符号链接或目录联接")
    source_allowlist(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 先在独立新目录完成导出；失败不留下貌似完整的可发布目录。
    with tempfile.TemporaryDirectory(prefix='.core-export-', dir=destination.parent) as temporary:
        staging = _export_core_tree(Path(temporary) / 'source')
        staging.rename(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/core-source")
    args = parser.parse_args()
    print(export_core(args.output))
