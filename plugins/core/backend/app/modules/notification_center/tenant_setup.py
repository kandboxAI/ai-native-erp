"""通知中心的租户开通数据：内置通知场景、渠道、模板、接收人路由。

可重复执行：已有场景不覆盖租户改过的名称、模板与开关，只补齐缺少的渠道、模板与内置路由。
路由按权限（permission_key → sys_permission.id）或业务相关人（actor_key，发送方在 notify(actors=...) 中给出），
不按角色。引用的权限尚未开通时先跳过该路由，下次执行再补。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from .models import NtfRoute, NtfScene, NtfSceneChannel, NtfTemplate
from .repository import repository

logger = logging.getLogger(__name__)

PASS_THROUGH = {"title_template": "{title}", "content_template": "{content}"}

# 每项：scene_key、scene_name、module_code、severity_code、description、templates（channel → 模板）、routes
BUILTIN_SCENES: list[dict[str, Any]] = [
    {
        "scene_key": "workflow.task.pending",
        "inbox_category": "todo",
        "scene_name": "审批待办",
        "module_code": "workflow",
        "severity_code": "important",
        "description": "审批任务生成时通知审批人",
        "templates": {
            "in_app": {"title_template": "{task_title}", "content_template": "{applicant_name}提交的{business_name}等待您审批"},
        },
        "routes": [{"target_type_code": "actor", "actor_key": "approver"}],
    },
    {
        "scene_key": "workflow.instance.completed",
        "scene_name": "审批结果",
        "module_code": "workflow",
        "severity_code": "normal",
        "description": "审批通过或驳回后通知申请人",
        'templates': {
            'in_app': {'title_template': '{title}', 'content_template': '{content}'}
        }, 
        "routes": [{"target_type_code": "actor", "actor_key": "applicant"}],
    },
]


def builtin_scene_specs(only: set[str] | None = None):
    from app.framework.catalog import iter_module_attr
    specs = list(BUILTIN_SCENES)
    sources = {}
    for spec in specs:
        sources.setdefault(spec["scene_key"], []).append(__name__)
    for module in iter_module_attr("notification_scenes", only):
        for spec in module.SCENES:
            specs.append(spec)
            sources.setdefault(spec["scene_key"], []).append(module.__name__)
    for spec in specs:
        if spec.get('inbox_category', 'message') not in {'message', 'announcement', 'todo', 'alert', 'family'}:
            raise ValueError(f"通知场景 {spec['scene_key']} 的收件箱分类无效")
    duplicates = [f"{key}（{', '.join(owners)}）" for key, owners in sorted(sources.items()) if len(owners) > 1]
    if duplicates:
        raise ValueError("通知场景标识重复：" + "；".join(duplicates))
    return specs


def _route_key(target_type_code: str, permission_id: Any, actor_key: str | None) -> tuple:
    return (target_type_code, str(permission_id or ""), actor_key or "")


async def setup_tenant(session: AsyncSession, ctx: Any, *, only: set[str] | None = None) -> None:
    from app.framework.catalog import iter_module_attr

    retired = {key for module in iter_module_attr("notification_scenes", only)
               for key in getattr(module, "RETIRED_SCENE_KEYS", ())}
    if retired:
        await repository.purge_retired_scenes(session, retired)
    for spec in builtin_scene_specs(only):
        scene = await repository.scene_by_key(session, spec["scene_key"])
        if scene is None:
            scene = NtfScene(
                scene_key=spec["scene_key"],
                scene_name=spec["scene_name"],
                module_code=spec["module_code"],
                description=spec.get("description"),
                severity_code=spec.get("severity_code", "normal"),
                fallback_policy_code="none",
                is_active=True,
            )
            session.add(scene)
            await session.flush()

        channels = {row.channel_code for row in await repository.scene_channels(session, scene.id)}
        templates = {row.channel_code: row for row in await repository.scene_templates(session, scene.id)}
        for channel_code, template in spec["templates"].items():
            if channel_code not in channels:
                session.add(NtfSceneChannel(scene_id=scene.id, channel_code=channel_code, is_active=True))
            if channel_code not in templates:
                session.add(NtfTemplate(scene_id=scene.id, channel_code=channel_code, is_active=True, **template))
            else:
                previous = spec.get("previous_templates", {}).get(channel_code)
                current = templates[channel_code]
                if previous and all(getattr(current, key) == value for key, value in previous.items()):
                    current.title_template = template["title_template"]
                    current.content_template = template["content_template"]
                    session.add(current)

        existing = {
            _route_key(row.target_type_code, row.permission_id, row.actor_key) for row in await repository.scene_routes(session, scene.id)
        }
        for route in spec["routes"]:
            permission_id = None
            if route["target_type_code"] == "permission":
                permission = await repository.permission_by_key(session, route["permission_key"])
                if permission is None:
                    logger.info("通知场景 %s 的路由权限 %s 尚未开通，暂不配置", spec["scene_key"], route["permission_key"])
                    continue
                permission_id = permission.id
            key = _route_key(route["target_type_code"], permission_id, route.get("actor_key"))
            if key in existing:
                continue
            session.add(
                NtfRoute(
                    scene_id=scene.id,
                    target_type_code=route["target_type_code"],
                    permission_id=permission_id,
                    actor_key=route.get("actor_key"),
                    org_scope_code=route.get("org_scope_code", "none"),
                    is_active=True,
                )
            )
            existing.add(key)
    await session.flush()
