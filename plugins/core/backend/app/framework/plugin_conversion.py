"""Mechanical legacy source conversion in an isolated core tree. No database I/O."""
from __future__ import annotations

import ast
from dataclasses import fields
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import tomllib

from app.framework.plugin_manifest import read_plugin_manifest, resolve_plugin_manifests, is_generated_ai_snapshot
from app.framework.plugin_settings import is_private_plugin_configuration, read_plugin_configuration
from app.framework.plugin_package import pack_plugin, install_package, _safe

REFERENCES = re.compile(r'''(["'])((?:@/|\./|\.\./)[^"'\n]+)\1''')
SUFFIXES = ('.ts', '.vue', '.tsx', '.js', '.mjs', '.scss', '.css', '.json', '.svg', '.png')
TEXT = {'.vue', '.ts', '.tsx', '.js', '.mjs', '.scss', '.css'}
SKIP = {'__pycache__', '.git', '.venv', 'node_modules', 'dist'}


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def _set_toml(source, name, value):
    # All converted fields are top-level scalars or string lists.
    tree = tomllib.loads(source)
    if name in tree:
        pattern = rf'(?m)^{re.escape(name)}\s*=\s*(?:\[[\s\S]*?\]|[^\n]*)'
        source, count = re.subn(pattern, lambda _: f'{name} = {json.dumps(value, ensure_ascii=False)}', source, count=1)
        if count != 1:
            raise ValueError(f'不能自动修改 TOML 字段：{name}')
    else:
        source += f'\n{name} = {json.dumps(value, ensure_ascii=False)}\n'
    return source


def _resolve(base):
    return next((path for path in (base, *(Path(str(base) + suffix) for suffix in SUFFIXES), *(base / ('index' + suffix) for suffix in SUFFIXES)) if path.is_file()), None)


def source_plan(core: Path, source: Path, key: str):
    """Collect owned files and local frontend dependencies without importing legacy code."""
    core, source = core.resolve(), source.resolve()
    if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in {'core', 'public', 'tenant'}:
        raise ValueError('插件 key 必须为小写 snake_case，不能使用 core/public/tenant')
    manifest_path = source / f'plugins/{key}/plugin.toml'
    original = manifest_path.read_text(encoding='utf-8')
    metadata = tomllib.loads(original)
    configuration = read_plugin_configuration(manifest_path.parent, key, metadata["configuration"]) if "configuration" in metadata else None
    if metadata.get('source_layout') == 'contained':
        raise ValueError('此插件已使用独立源码目录，请直接 pack；convert 仅用于旧业务')
    if metadata.get('key') != key:
        raise ValueError('源插件 key 与目录不一致')
    if metadata.get('frontend_manifest') != 'frontend.json':
        raise ValueError('转换需要源插件的 frontend.json；全新业务先用 scaffold 生成')
    frontend = json.loads((manifest_path.parent / 'frontend.json').read_text(encoding='utf-8'))
    core_manifest = json.loads((core / 'backend/app/framework/core_manifest.json').read_text(encoding='utf-8'))
    if set(metadata['module_names']) & set(core_manifest['module_names']):
        raise ValueError('源插件不能声明拥有底座模块')
    prefixes = [f'plugins/{key}', *(f'backend/app/modules/{name}' for name in metadata['module_names']), *(f'web/src/views/{name}' for name in frontend['web_view_roots']), *(f'miniprogram/src/{PurePosixPath(page).parent}' for page in frontend['miniapp_pages'])]
    legacy = metadata.get('migration_base', 'tenant') != 'core'
    if not legacy and metadata.get('migration_location'):
        prefixes.append('backend/' + metadata['migration_location'])
        prefixes.extend(f'backend/alembic/versions/plugins/{key}' for key in metadata.get('replaces', []))
    contents, origins, edits, review = {}, {}, [], []

    def add_file(path, destination):
        _safe(destination)
        if is_private_plugin_configuration(path.relative_to(source).as_posix(), key, configuration) or set(path.relative_to(source).parts) & SKIP:
            raise ValueError(f'不能收集本地配置或依赖目录：{path}')
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError(f'源文件不能越界或为链接：{path}')
        data = path.read_bytes()
        if destination in contents and contents[destination] != data:
            raise ValueError(f'转换后文件名冲突：{destination}')
        contents[destination], origins[path.resolve()] = data, destination

    for prefix in dict.fromkeys(prefixes):
        _safe(prefix)
        directory = source / prefix
        if not directory.is_dir() or directory.is_symlink() or not directory.resolve().is_relative_to(source):
            raise ValueError(f'缺少声明的源码目录或目录越界：{prefix}')
        for path in sorted(directory.rglob('*')):
            if set(path.relative_to(directory).parts) & SKIP or is_private_plugin_configuration(path.relative_to(source).as_posix(), key, configuration) or path.suffix == '.pyc' or is_generated_ai_snapshot(path.relative_to(source).as_posix()):
                continue
            if path.is_file():
                add_file(path, path.relative_to(source).as_posix())
    for name in metadata.get('package_files', []):
        if is_generated_ai_snapshot(name):
            continue
        add_file(source / _safe(name), name)

    # Keep shared APIs on the current core contract; localize missing old helpers.
    extras = {name for name in metadata.get('package_files', []) if not is_generated_ai_snapshot(name)}
    pending, processed = list(origins), set()
    while pending:
        origin = pending.pop()
        if origin in processed or origin.suffix not in TEXT:
            continue
        processed.add(origin)
        destination = origins[origin]
        side = 'miniprogram' if destination.startswith(('miniprogram/', f'plugins/{key}/miniprogram/')) else 'web' if destination.startswith('web/') else None
        if side is None:
            continue
        old_src, new_src = source / side / 'src', core / side / 'src'
        text = contents[destination].decode('utf-8')
        replacements = {}
        for match in REFERENCES.finditer(text):
            reference = match.group(2)
            if any(token in reference for token in ('*', '${', '?')):
                review.append(dict(file=destination, reason=f'动态前端引用需确认随包可用：{reference}'))
                continue
            old_base = old_src / reference[2:] if reference.startswith('@/') else origin.parent / reference
            old = _resolve(old_base)
            if old is None:
                current_base = new_src / reference[2:] if reference.startswith('@/') else (core / destination).parent / reference
                if _resolve(current_base):
                    continue
                line = text[text.rfind('\n', 0, match.start()) + 1:text.find('\n', match.end()) if '\n' in text[match.end():] else len(text)]
                if re.search(r'\b(?:import|from|require)\b|@use', line):
                    review.append(dict(file=destination, reason=f'找不到静态依赖：{reference}'))
                continue
            old = old.resolve()
            if not old.is_relative_to(source):
                raise ValueError(f'前端引用越过源码根：{destination}: {reference}')
            target = origins.get(old)
            if target is None:
                relative = old.relative_to(source).as_posix()
                api = relative.startswith(f'{side}/src/api/') and old.suffix == '.ts'
                current = _resolve(new_src / old.relative_to(old_src)) if old.is_relative_to(old_src) else None
                if current:
                    # Preserve the current login/session/request infrastructure.
                    target = current.relative_to(core).as_posix()
                elif api:
                    stem = old.stem if old.stem.startswith(key) else key + old.stem[:1].upper() + old.stem[1:]
                    target = f'{side}/src/api/{stem}.ts'
                    extras.add(target)
                else:
                    view = frontend['web_view_roots'][0] if side == 'web' else str(PurePosixPath(frontend['miniapp_pages'][0]).parent).split('/', 1)[1]
                    base = old_src if old.is_relative_to(old_src) else source
                    target = f'{side}/src/' + (f'views/{view}' if side == 'web' else f'pages/{view}') + '/shared/' + old.relative_to(base).as_posix()
                if not current:
                    add_file(old, target)
                    pending.append(old)
                    edits.append(f'收集依赖：{relative} → {target}')
            target_path = core / target
            if target.startswith(f'{side}/src/'):
                updated = '@/' + target[len(f'{side}/src/'):]
            else:
                updated = os.path.relpath(target_path, (core / destination).parent).replace('\\', '/')
                if not updated.startswith('.'):
                    updated = './' + updated
            if Path(reference).suffix not in SUFFIXES and target_path.suffix in {'.ts', '.js', '.tsx'}:
                updated = updated.rsplit('.', 1)[0]
            if reference != updated:
                replacements[reference] = updated
        text = REFERENCES.sub(lambda match: match.group(1) + replacements.get(match.group(2), match.group(2)) + match.group(1), text)
        contents[destination] = text.encode('utf-8')

    # Older code stored business menus in another module's route_manifest.json.
    # Recover only entries whose components belong to this plugin, preserving keys/permissions.
    catalogs = [f'backend/app/modules/{name}/catalog.py' for name in metadata['module_names']]
    has_menus = False
    for name in catalogs:
        if name not in contents:
            continue
        for node in ast.parse(contents[name], filename=name).body:
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(target, ast.Name) and target.id == 'MENUS' for target in targets) and value is not None and not (isinstance(value, ast.List) and not value.elts):
                has_menus = True
    recovered = []
    if not has_menus:
        from app.framework.catalog import MenuDef
        allowed_fields = {field.name for field in fields(MenuDef)}
        seen_keys, seen_components = set(), set()
        root_key = ''.join(part.capitalize() for part in key.split('_')) + 'Root'
        root_path = '/' + frontend['web_view_roots'][0] if frontend['web_view_roots'] else '/' + key
        for path in sorted((source / 'backend/app/modules').glob('*/route_manifest.json')):
            rows = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(rows, list):
                continue
            for item in rows:
                if not isinstance(item, dict) or (item.get('component') or '').split('/')[0] not in frontend['web_view_roots'] or item.get('key') in seen_keys:
                    continue
                row = {name: value for name, value in item.items() if name in allowed_fields}
                row['parent_key'] = root_key
                if row.get('component') in seen_components:
                    row['is_visible'] = False  # Keep old aliases without duplicate visible menus.
                seen_components.add(row.get('component'))
                seen_keys.add(row['key'])
                recovered.append(row)
        if recovered:
            recovered.insert(0, dict(key=root_key, name=metadata['name'], menu_type_code='directory', path=root_path, icon='ri:apps-2-line'))
            module = metadata['module_names'][0]
            target = f'backend/app/modules/{module}/ported_menus.py'
            if target in contents:
                raise ValueError(f'自动目录文件已存在，拒绝覆盖：{target}')
            contents[target] = ('"""从旧路由声明提取的本插件目录；权限保持原标识。"""\nfrom app.framework.catalog import MenuDef\nMENUS = [MenuDef(**item) for item in ' + repr(recovered) + ']\n').encode('utf-8')
            target = f'backend/app/modules/{module}/catalog.py'
            text = contents.get(target, b'').decode('utf-8')
            if not re.search(r'(?m)^MENUS\s*(?::[^=]+)?=', text):
                text += '\nMENUS = []\n'
            contents[target] = (text + '\nfrom .ported_menus import MENUS as _PORTED_MENUS\nMENUS.extend(_PORTED_MENUS)\n').encode('utf-8')
            metadata['menu_keys'] = list(dict.fromkeys([*metadata.get('menu_keys', []), *(row['key'] for row in recovered)]))
            edits.append(f'从旧路由声明提取 {len(recovered) - 1} 个业务菜单，归入独立顶层目录')
            if not frontend.get('web_applications'):
                frontend['web_applications'] = [dict(title=metadata['name'], summary=metadata['name'] + '业务入口', icon='ri:apps-2-line', path=recovered[1]['path'], rootPath=root_path, tone='blue')]

    migration = f'alembic/versions/plugins/{key}'
    if legacy:
        edits.append('旧 tenant/mes 迁移不复制；改为 core 独立分支，待显式生成初始迁移')
    # Empty directories must survive source packaging.
    if not any(name.startswith(f'backend/{migration}/') for name in contents):
        contents[f'backend/{migration}/.gitkeep'] = b''
    converted = original
    for name, value in {'migration_base': 'core', 'migration_location': migration, 'package_files': sorted(extras), 'menu_keys': metadata.get('menu_keys', [])}.items():
        converted = _set_toml(converted, name, value)
    contents[f'plugins/{key}/plugin.toml'] = converted.encode('utf-8')
    contents[f'plugins/{key}/frontend.json'] = _json(frontend).encode('utf-8')

    for name, data in contents.items():
        if not name.endswith(('.py', '.ts', '.vue')):
            continue
        text = data.decode('utf-8')
        for pattern, reason in (
            (r'\bt_edu\b', '存在固定租户 schema，需改为租户上下文'),
            (r'get_deployment_profile\(\)\s*==\s*[\"\x27](?:edu|mes|edu_mes)[\"\x27]', '存在已取消的预置组合判断，需确认目录/入口逻辑'),
            (r'[\"\x27](?:teacher|principal|staff)[\"\x27]\s*,\s*[\"\x27]', '存在旧门户或角色语义，需确认是否适配 standard 门户'),
        ):
            for match in re.finditer(pattern, text):
                review.append(dict(file=name, line=text.count('\n', 0, match.start()) + 1, reason=reason))
        if '/shared/store/' in name:
            review.append(dict(file=name, reason='复制了旧本地 Store，需确认是否把模拟数据冒充服务端数据'))
    pages_source = source / 'miniprogram/src/pages.json'
    pages = json.loads(pages_source.read_text(encoding='utf-8'))['pages'] if pages_source.exists() else []
    registrations = {item['path']: item for item in pages}
    return dict(key=key, metadata=metadata, frontend=frontend, contents=contents, edits=edits, review=review,
                pages=[registrations.get(page, {'path': page}) for page in frontend['miniapp_pages']])


def convert_plugin(root: Path, source: Path, key: str, *, output: Path | None = None, dry_run=False, generate_initial=False):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in {'core', 'public', 'tenant'}:
        raise ValueError('插件 key 必须为小写 snake_case，不能使用 core/public/tenant')
    root = root.resolve()
    if output is not None and Path(output).exists():
        raise ValueError('输出 ZIP 已存在，请使用新文件名；不会覆盖已有交付包')
    temporary_root = (root / 'backend/.generated/plugin-conversions').resolve()
    if not temporary_root.is_relative_to(root):
        raise ValueError('转换目录越界')
    temporary_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=key + '-', dir=temporary_root)) / 'project'
    exporter_path = root / 'backend/scripts/export_core.py'
    spec = importlib.util.spec_from_file_location('_plugin_core_export', exporter_path)
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    exporter.export_core(workspace)
    plan = source_plan(workspace, source, key)
    report = dict(plugin_key=key, workspace=str(workspace), dry_run=dry_run, files=len(plan['contents']),
                  automated=plan['edits'], review=plan['review'], database_changed=False, migration_generated=False,
                  checks=dict(backend='not_run', frontend='static_dependencies_only', frontend_build='not_run', database='not_run'))
    report_path = workspace.parent / 'conversion-report.json'
    def finish(status):
        report['status'] = status
        report['report'] = str(report_path)
        report_path.write_text(_json(report), encoding='utf-8')
        return report
    if dry_run:
        return finish('preview')
    # Stage only, never overwrite the caller's working source or deployment.
    for name, data in plan['contents'].items():
        path = workspace / _safe(name)
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'转换不能覆盖底座文件：{name}')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    read_plugin_manifest(workspace / f'plugins/{key}/plugin.toml')
    own = read_plugin_manifest(workspace / f'plugins/{key}/plugin.toml')
    available = {key: own}
    selected = {key}
    def add_dependencies(item):
        for spec in item.requires:
            dependency = spec.split('>=', 1)[0]
            if dependency not in available:
                path = root / f'plugins/{dependency}/plugin.toml'
                if not path.is_file():
                    raise ValueError(f'请先导入或转换依赖插件：{dependency}')
                available[dependency] = read_plugin_manifest(path)
            if dependency not in selected:
                selected.add(dependency)
                add_dependencies(available[dependency])
    add_dependencies(own)
    manifests = resolve_plugin_manifests(selected, tuple(available.values()))
    for item in manifests:
        if item.key == key:
            continue
        package = workspace.parent / f'dependency-{item.key}.zip'
        pack_plugin(root, item.key, package)
        install_package(workspace, package, deploy=True)
    pages = json.loads((workspace / 'miniprogram/src/pages.json').read_text(encoding='utf-8'))
    registered = {item['path'] for item in pages['pages']}
    pages['pages'].extend(item for item in plan['pages'] if item['path'] not in registered)
    (workspace / 'miniprogram/src/pages.json').write_text(_json(pages), encoding='utf-8')
    (workspace / 'deployment.json').write_text(_json(dict(format_version=1, plugins=sorted(selected))), encoding='utf-8')
    from app.framework.plugin_relocation import relocate_plugin
    relocate_plugin(workspace, key)
    environment = dict(os.environ, DATABASE_URL='postgresql://offline:offline@127.0.0.1:1/offline', JWT_SECRET='offline-plugin-conversion-' * 3, PYTHONIOENCODING='utf-8', PYTHONPATH=str(workspace / 'backend'))
    for name in ('ERP_DEPLOYMENT_PROFILE', 'DEPLOYMENT_PROFILE', 'FRONTEND_DEPLOYMENT_FILE'):
        environment.pop(name, None)
    def run(*arguments):
        process = subprocess.run([sys.executable, '-m', 'app.framework.plugin_cli', *arguments], cwd=workspace / 'backend', env=environment, capture_output=True, text=True, encoding='utf-8', timeout=120)
        return process.returncode, process.stdout, process.stderr
    code, stdout, stderr = run('check')
    if code:
        report['checks']['backend'] = 'failed'
        report['check_error'] = (stderr or stdout).strip()
        return finish('needs_code_changes')
    check = json.loads(stdout)
    report['checks']['backend'] = 'passed'
    if generate_initial and not check['plugin_heads'][key]:
        if plan['review']:
            report['check_error'] = '先处理 review 中的旧语义，再生成迁移'
            return finish('needs_code_changes')
        arguments = ['revision', '--plugin', key, '--schema', 't_plugin_build', '--message', f'initial {key} plugin']
        if key in check['table_owners'].values():
            arguments.append('--from-models')
        else:
            arguments.append('--baseline')
        code, stdout, stderr = run(*arguments)
        if code:
            report['check_error'] = (stderr or stdout).strip()
            return finish('needs_code_changes')
        report['migration_generated'] = True
        code, stdout, stderr = run('check', '--require-migrations')
        if code:
            report['check_error'] = (stderr or stdout).strip()
            return finish('needs_code_changes')
        check = json.loads(stdout)
    if plan['review']:
        return finish('needs_review')
    ready = bool(check['plugin_heads'][key])
    output = Path(output).resolve() if output else root / f'dist/plugins/{key}-{own.version}-{workspace.parent.name}{"" if ready else "-source"}.zip'
    packed = pack_plugin(workspace, key, output, source_only=not ready)
    report.update(package=packed['output'], migration_ready=ready)
    return finish('package_ready' if ready else 'source_only_needs_migration')
