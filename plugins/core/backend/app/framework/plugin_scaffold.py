"""Create an uninstalled plugin skeleton. Never overwrite an existing plugin."""
from __future__ import annotations

import json
import re
from pathlib import Path


def scaffold_plugin(root: Path, key: str, name: str, layer: str, requires: list[str], *, source_layout="contained") -> list[Path]:
    root = root.resolve()
    if source_layout not in {"legacy", "contained"}:
        raise ValueError("源码布局必须为 legacy 或 contained")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in {"core", "public", "tenant"}:
        raise ValueError("插件 key 必须为小写 snake_case，且不能使用 core/public/tenant")
    if layer not in {"L2", "L3"} or not name.strip() or any(char in name for char in "\n\r"):
        raise ValueError("名称必须为单行非空文本，layer 必须为 L2 或 L3")
    if len(requires) != len(set(requires)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*(?:>=\d+(?:\.\d+){1,2})?", spec) or spec.split(">=", 1)[0] == key for spec in requires):
        raise ValueError("依赖必须为 key 或 key>=版本，不能重复或引用自身")
    view = key.replace("_", "-")
    menu = "".join(part.capitalize() for part in key.split("_")) + "Root"
    paths = [root / f"plugins/{key}", root / "plugins/core/backend/app/modules" / key, root / "plugins/core/backend/alembic/versions/plugins" / key, root / f"web/src/views/{view}", root / f"web/src/api/{key}.ts", root / f"miniprogram/src/pages/{view}"]
    if any(path.exists() for path in paths):
        raise ValueError("目标插件、模块、页面、API 或迁移目录已存在；拒绝覆盖。旧业务请按 AI 插件接入规则改造")
    text = lambda value: json.dumps(value, ensure_ascii=False)
    files = {
        f"plugins/{key}/plugin.toml": f'''key = {text(key)}
name = {text(name)}
layer = {text(layer)}
version = "0.1.0"
requires = {text(requires)}
module_codes = [{text(key)}]
module_names = [{text(key)}]
table_prefixes = [{text(key + '_')}]
routers = ["app.modules.{key}.api:router"]
menu_keys = [{text(menu)}]
miniapp_menu_keys = ["{key}_entry"]
frontend_manifest = "frontend.json"
migration_base = "core"
migration_location = "alembic/versions/plugins/{key}"
ai_providers = []
ai_skill_keys = []
package_files = ["web/src/api/{key}.ts"]
configuration = {{ env_prefix = "{key.upper()}_", template = "config/.env.example", secret_keys = [] }}
''',
        f"plugins/{key}/config/.env.example": f'''# 复制到 plugins/core/backend/config/plugin/{key}.env，实际配置文件不提交、不随包发布。
{key.upper()}_REQUEST_TIMEOUT_SECONDS=30
''',
        f"plugins/{key}/frontend.json": json.dumps({"format_version": 1, "web_view_roots": [view], "miniapp_pages": [f"pages/{view}/index"], "miniapp_service_provider": "miniprogram/services.ts", "web_applications": [{"title": name, "summary": f"{name}业务入口", "icon": "ri:apps-2-line", "path": f"/{view}", "rootPath": f"/{view}", "tone": "blue"}]}, ensure_ascii=False, indent=2) + "\n",
        f"plugins/{key}/miniprogram/services.ts": f'''import type {{ RoleServiceOptions, RoleServiceItem }} from "@/config/pluginServices";
export function getRoleServiceItems(options: RoleServiceOptions): RoleServiceItem[] {{
  return options.permissions?.includes("{key}:access") ? [{{ title: {text(name)}, desc: "业务插件入口", icon: "用", tone: "blue", url: "/pages/{view}/index" }}] : [];
}}
''',
        f"backend/app/modules/{key}/__init__.py": "",
        f"backend/app/modules/{key}/models.py": '"""在这里定义本插件拥有的 SQLModel 表，复用 framework/db/models.py 字段工厂。当前无业务表。"""\n',
        f"backend/app/modules/{key}/config.py": f'''"""本插件配置类型、默认值与校验；环境文件由底座统一读取。"""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.framework.plugin_settings import load_plugin_settings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="{key.upper()}_", extra="ignore")
    request_timeout_seconds: int = Field(default=30, ge=1, le=300)

@lru_cache
def settings() -> Settings:
    return load_plugin_settings("{key}", Settings)
''',
        f"backend/app/modules/{key}/api.py": f'''from fastapi import APIRouter, Depends
from app.auth.dependencies import require_permissions
from app.core.response import success_response

router = APIRouter(prefix="/api/{key}", tags=[{text(key)}])

@router.get("/status")
def plugin_status(current_user=Depends(require_permissions(["{key}:access"]))):
    return success_response({{"plugin_key": "{key}", "status": "ready"}})
''',
        f"backend/app/modules/{key}/catalog.py": f'''from app.framework.catalog import PermissionDef, MenuDef, MiniappMenuDef

PERMISSIONS = [PermissionDef("{key}:access", {text('访问' + name)}, "{key}")]
MENUS = [MenuDef(key="{menu}", name={text(name)}, menu_type_code="menu", path="/{view}", component="{view}/index", permission_key="{key}:access", icon="ri:apps-2-line")]
MINIAPP_MENUS = [MiniappMenuDef(portal_code="standard", menu_key="{key}_entry", menu_name={text(name)}, path="/pages/{view}/index", group_key="applications", group_name="业务应用")]
''',
        f"backend/app/modules/{key}/dictionary_specs.py": f'''DICTIONARIES = []
DICT_ITEMS = {{"sys_module": [("{key}", {text(name)})]}}
''',
        f"backend/app/modules/{key}/tenant_setup.py": '''"""租户必需配置；幂等补齐，业务 SQL 放在所属 Repository。目录由框架同步。"""
async def setup_tenant(session, ctx):
    pass
''',
        f"backend/app/modules/{key}/demo_seed.py": '''"""演示数据仅通过 bootstrap --with-demo 显式加载。"""
async def seed_demo(session, ctx):
    pass
''',
        f"plugins/core/backend/alembic/versions/plugins/{key}/.gitkeep": "",
        f"web/src/api/{key}.ts": f'''import {{ http }} from "@/utils/http";
export const getPluginStatus = () => http.request<{{ code: number; message: string; data: {{ plugin_key: string; status: string }} }}>("get", "/api/{key}/status");
''',
        f"web/src/views/{view}/index.vue": f'''<script setup lang="ts">
import {{ ref, onMounted }} from "vue";
import {{ getPluginStatus }} from "@/api/{key}";
const status = ref("正在检查插件入口");
onMounted(async () => {{ try {{ const response = await getPluginStatus(); status.value = response.code === 0 ? "插件入口已接通" : response.message; }} catch {{ status.value = "入口不可访问，请检查租户启用状态和权限"; }} }});
</script>
<template><section class="p-6"><h1>{name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</h1><p>{{{{ status }}}}</p><el-empty description="业务功能待实现" /></section></template>
''',
        f"miniprogram/src/pages/{view}/index.vue": f'''<script setup lang="ts">
import {{ ref }} from "vue";
import {{ onShow }} from "@dcloudio/uni-app";
import {{ requestApi }} from "@/api/client";
const status = ref("正在检查插件入口");
onShow(async () => {{ try {{ await requestApi({{ path: "/api/{key}/status" }}); status.value = "插件入口已接通，业务功能待实现"; }} catch {{ status.value = "入口不可访问，请检查权限和租户启用状态"; }} }});
</script>
<template><view class="page-shell"><text>{{{{ status }}}}</text></view></template>
''',
    }
    for module, description in {"repository": "本插件 SQL / ORM 查询及持久化", "service": "业务规则及事务编排，调用所属 Repository", "schemas": "请求与响应协议", "public": "对其他插件公开的 Service 契约"}.items():
        files[f"backend/app/modules/{key}/{module}.py"] = f'"""{description}。"""\n'
    if source_layout == "contained":
        files = {(f"plugins/{key}/{path}" if path.startswith(("backend/app/", "web/src/", "miniprogram/src/")) else path):
                 content.replace(f'from "@/api/{key}"', f'from "@plugins/{key}/web/src/api/{key}"')
                 for path, content in files.items()}
        files[f"plugins/{key}/plugin.toml"] = 'source_layout = "contained"\n' + files[f"plugins/{key}/plugin.toml"]
    # Validate every destination before the first write. No deployment selection or DB changes.
    targets = [(root / path, content) for path, content in files.items()]
    if any(path.exists() or not path.resolve().is_relative_to(root) for path, _ in targets):
        raise ValueError("生成路径已存在或越界")
    for path, content in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return [path for path, _ in targets]
