"""通知中心业务编排。

其他模块发通知只调用 ``notify``（不提交事务，随业务一起提交）：

    from app.modules.notification_center.service import notify

    await notify(
        session,
        scene_key="leave_approved",
        recipients=[applicant_user_id],                 # 直接指定的 sys_user.id，可空
        actors={"homeroom_teacher": [teacher_user_id]},  # 路由中 actor 类型对应的业务相关人，可空
        business_type_code="student_leave",
        business_id=leave.id,
        payload={"title": "...", "content": "...", "student_name": "..."},
        org_id=leave.org_id,
        event_key=f"leave_approved:{leave.id}",
    )

接收人 = recipients ∪ 场景路由（ntf_route）解析结果：按用户、权限（permission_id）、角色（role_id，租户配置）、
业务相关人（actor_key）、全部用户；组织范围为 event_organization 时只取 org_id 组织的用户。代码不按角色编号判断。
"""

from __future__ import annotations

import json
import logging
import secrets
from string import Formatter
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastapi import status
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.db.tenant import use_tenant_schema

from .models import (
    NtfChannelBinding,
    NtfDeliveryLog,
    NtfEventLog,
    NtfNotification,
    NtfPreference,
    NtfRecipient,
    NtfScene,
    NtfTemplate,
)
from .repository import repository
from .scene_policies import is_critical_scene, is_in_app_only_scene, confirmation_deadline
from .schemas import (
    CHANNEL_IN_APP,
    CHANNEL_WECHAT_MINIAPP_SUBSCRIBE,
    CHANNEL_WECHAT_SERVICE,
    EXTERNAL_CHANNELS,
    ChannelBindingCreate,
    ChannelBindingItem,
    DeliveryLogItem,
    DeliveryLogListQuery,
    DeliveryProcessResult,
    EventLogItem,
    EventLogListQuery,
    HistoryItem,
    HistoryListQuery,
    MineItem,
    MineListQuery,
    NotifyResult,
    PreferenceItem,
    PreferenceWrite,
    PublishPayload,
    RecipientItem,
    RecipientListQuery,
    RouteItem,
    RouteWrite,
    SceneChannelItem,
    SceneConfig,
    SceneCreate,
    SceneItem,
    SceneListQuery,
    SceneUpdate,
    TemplateItem,
    WechatServiceBindCallbackResult,
    WechatServiceBindingStatusData,
    WechatServiceBindUrlData,
)

logger = logging.getLogger(__name__)

SEVERITIES = {"normal", "important", "urgent"}
FALLBACK_POLICIES = {"none", "all"}
ORG_SCOPES = {"none", "event_organization"}
CHANNELS = {CHANNEL_IN_APP, CHANNEL_WECHAT_SERVICE, CHANNEL_WECHAT_MINIAPP_SUBSCRIBE, "sms", "email"}
WECHAT_SERVICE_BIND_STATE_PREFIX = "wechat:official:bind_state:"
SCENE_FIELDS = {"scene_key", "scene_name", "module_code", "description", "severity_code", "fallback_policy_code", "is_active"}


def _bad_request(message: str) -> AppException:
    return AppException(message, status_code=status.HTTP_400_BAD_REQUEST)


# ───────── 模板渲染 ─────────
class _SafeContext(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render_template(template: str | None, context: dict[str, Any]) -> str | None:
    """{字段} 占位符替换；缺少的字段替换为空串，不支持属性访问与下标。"""
    if template is None:
        return None
    try:
        fields = {name for _, name, _, _ in Formatter().parse(template) if name}
    except ValueError:
        return template
    if not fields:
        return template
    safe = _SafeContext({key: "" if value is None else value for key, value in context.items()})
    try:
        return template.format_map({name: safe[name] for name in fields})
    except (KeyError, IndexError, ValueError, AttributeError):
        return template


def _wechat_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())[:200]


def notification_targets(payload, redirect_url):
    declared = payload.get("targets") if isinstance(payload, dict) else None
    declared = declared if isinstance(declared, dict) else {}
    targets = {}
    for key in ("web", "miniapp"):
        value = declared.get(key)
        if isinstance(value, str) and value:
            targets[key] = value
    # 旧通知继续按原地址解析，已有调用方无需补写历史数据。
    if redirect_url:
        targets.setdefault("miniapp" if redirect_url.startswith("/pages/") else "web", redirect_url)
    return targets


def _wechat_request_payload(channel_code: str, template: NtfTemplate, context: dict[str, Any], redirect_url: str) -> dict[str, Any]:
    targets = notification_targets(context, redirect_url)
    miniapp_target = targets.get("miniapp", "")
    web_target = targets.get("web", "")
    data = {
        str(target): {"value": _wechat_value(context.get(str(source)))}
        for target, source in (template.data_mapping_config or {}).items()
    }
    settings = get_settings()
    base = {
        "template_id": template.wechat_template_no,
        "title": render_template(template.title_template, context),
        "content": render_template(template.content_template, context),
        "data": data,
    }
    if channel_code == CHANNEL_WECHAT_MINIAPP_SUBSCRIBE:
        return {
            **base,
            "page": miniapp_target.lstrip("/") if miniapp_target.startswith("/pages/") else None,
            "miniprogram_state": settings.wechat_miniapp_subscribe_state,
            "lang": "zh_CN",
        }
    miniprogram = None
    url: str | None = web_target if web_target.startswith(("http://", "https://")) else None
    if miniapp_target.startswith("/pages/") and settings.wechat_miniapp_appid:
        miniprogram = {"appid": settings.wechat_miniapp_appid, "pagepath": miniapp_target.lstrip("/")}
    return {**base, "url": url, "miniprogram": miniprogram}


# ───────── 发送 ─────────
async def _event_log(
    session: AsyncSession,
    *,
    org_id: UUID | None,
    scene: NtfScene | None,
    status_code: str,
    message: str | None,
    business_type_code: str | None,
    business_id: UUID | None,
    payload: dict[str, Any],
    created_by: UUID | None,
) -> None:
    org_id = org_id or await repository.root_org_id(session)
    if org_id is None:  # 尚未开通组织，无法记录
        return
    repository.add(
        session,
        NtfEventLog(
            org_id=org_id,
            scene_id=scene.id if scene else None,
            business_type_code=business_type_code,
            business_id=business_id,
            status_code=status_code,
            message=message,
            payload=payload,
            created_by=created_by,
        ),
    )


async def _resolve_recipients(
    session: AsyncSession,
    scene: NtfScene,
    *,
    recipients: list[UUID],
    actors: dict[str, list[UUID]],
    org_id: UUID | None,
) -> set[UUID]:
    user_ids: set[UUID] = set(recipients)
    for route in await repository.scene_routes(session, scene.id, active_only=True):
        if route.org_scope_code == "event_organization":
            if org_id is None:
                continue
            route_org = org_id
        else:
            route_org = None
        kind = route.target_type_code
        if kind == "user" and route.user_id:
            user_ids |= await repository.active_user_ids(session, [route.user_id], route_org)
        elif kind == "role" and route.role_id:
            user_ids |= await repository.user_ids_by_role(session, route.role_id, route_org)
        elif kind == "permission" and route.permission_id:
            user_ids |= await repository.user_ids_by_permission(session, route.permission_id, route_org)
        elif kind == "actor" and route.actor_key:
            user_ids |= await repository.active_user_ids(session, actors.get(route.actor_key) or [], route_org)
        elif kind == "all":
            user_ids |= await repository.all_user_ids(session, route_org)
    # 直接指定的接收人也要求账号有效
    return await repository.active_user_ids(session, user_ids)


async def resolve_scene_recipients(session, *, scene_key: str, org_id: UUID | None,
                                   actors: dict[str, list[UUID]] | None = None) -> set[UUID]:
    """业务事务内复用场景路由取得有效收件人；不发送消息或扩大路由组织范围。"""
    scene = await repository.scene_by_key(session, scene_key)
    if scene is None or not scene.is_active:
        return set()
    return await _resolve_recipients(session, scene, recipients=[], actors=actors or {}, org_id=org_id)


async def notify(
    session: AsyncSession,
    *,
    scene_key: str,
    recipients: list[UUID] | None = None,
    actors: dict[str, list[UUID]] | None = None,
    business_type_code: str | None = None,
    business_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    org_id: UUID | None = None,
    event_key: str | None = None,
    redirect_url: str | None = None,
    source_module_code: str | None = None,
    created_by: UUID | None = None,
    requires_confirmation: bool = False,
    record_without_recipients: bool = False,
    recipient_limit: list[UUID] | None = None,
) -> NotifyResult:
    """按场景发送通知：生成站内通知、接收人与各渠道投递记录。只 flush 不提交。

    - 场景不存在 / 停用 / event_key 重复 / 没有接收人时不发送，记事件日志并返回 skipped_reason。
    - 标题与内容取场景模板（站内信优先）渲染 payload；没有模板时取 payload 的 title / content。
    - 跳转地址：redirect_url 参数，否则 payload["redirect_url"]。
    - recipient_limit 为业务服务确定的接收人上限；配置路由不能扩大该范围，空列表代表无接收人。
    """
    payload = dict(payload or {})
    actors = {key: [item for item in value if item] for key, value in (actors or {}).items()}
    log_kwargs = dict(business_type_code=business_type_code, business_id=business_id, created_by=created_by)
    log_payload = {**payload, "event_key": event_key, "scene_key": scene_key}

    scene = await repository.scene_by_key(session, scene_key)
    if scene is None or not scene.is_active:
        reason = "scene_not_configured" if scene is None else "scene_disabled"
        await _event_log(session, org_id=org_id, scene=scene, status_code="skipped", message=reason, payload=log_payload, **log_kwargs)
        await session.flush()
        return NotifyResult(skipped_reason=reason)
    if event_key:
        existing = await repository.notification_by_event_key(session, event_key)
        if existing is not None:
            await _event_log(session, org_id=org_id, scene=scene, status_code="skipped", message="duplicate_event", payload=log_payload, **log_kwargs)
            await session.flush()
            return NotifyResult(notification_id=existing, skipped_reason="duplicate_event")

    user_ids = sorted(await _resolve_recipients(session, scene, recipients=list(recipients or []), actors=actors, org_id=org_id), key=str)
    # 业务已确定精确受影响人时，租户配置的路由也不能扩大收件范围。
    if recipient_limit is not None:
        allowed = set(recipient_limit)
        user_ids = [user_id for user_id in user_ids if user_id in allowed]
    if not user_ids and not record_without_recipients:
        await _event_log(session, org_id=org_id, scene=scene, status_code="skipped", message="no_recipients", payload=log_payload, **log_kwargs)
        await session.flush()
        return NotifyResult(skipped_reason="no_recipients")

    channels = set((await repository.active_channel_map(session, [scene.id])).get(scene.id, []))
    templates = {row.channel_code: row for row in await repository.scene_templates(session, scene.id, active_only=True)}
    context = {
        **payload,
        "scene_key": scene.scene_key,
        "scene_name": scene.scene_name,
        "module_code": scene.module_code,
        "business_type_code": business_type_code or "",
        "business_id": str(business_id) if business_id else "",
    }
    primary = templates.get(CHANNEL_IN_APP)
    if primary is None and not is_in_app_only_scene(scene.scene_key):
        primary = next(iter(templates.values()), None)
    title = render_template(primary.title_template, context) if primary else None
    content = render_template(primary.content_template, context) if primary else None
    title = (title or payload.get("title") or scene.scene_name)[:256]
    content = content if content is not None else payload.get("content")
    final_redirect = (redirect_url or str(payload.get("redirect_url") or "")).strip()[:1024] or None

    notification_org = org_id or await repository.root_org_id(session)
    if notification_org is None:
        raise AppException("尚未配置组织，无法发送通知", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    notification = repository.add(
        session,
        NtfNotification(
            org_id=notification_org,
            scene_id=scene.id,
            scene_name_snapshot=scene.scene_name,
            title=title,
            content=content,
            severity_code=scene.severity_code,
            status_code="created",
            source_module_code=source_module_code or scene.module_code,
            business_type_code=business_type_code,
            business_id=business_id,
            event_key=event_key,
            redirect_url=final_redirect,
            payload=payload,
            occurred_at=utc_now(),
            created_by=created_by,
            updated_by=created_by,
        ),
    )
    await session.flush()

    delivery_count = await _deliver_to_users(
        session, notification=notification, scene=scene, user_ids=user_ids,
        channels=channels, templates=templates, context=context,
        requires_confirmation=requires_confirmation, created_by=created_by,
    )

    await _event_log(
        session, org_id=notification_org, scene=scene, status_code="processed", message=None, payload=log_payload, **log_kwargs
    )
    await session.flush()
    return NotifyResult(notification_id=notification.id, created=True, recipient_count=len(user_ids), delivery_count=delivery_count)


async def _deliver_to_users(
    session: AsyncSession,
    *,
    notification: NtfNotification,
    scene: NtfScene,
    user_ids: list[UUID],
    channels: set[str],
    templates: dict[str, NtfTemplate],
    context: dict[str, Any],
    requires_confirmation: bool,
    created_by: UUID | None,
) -> int:
    """首次发送和补发复用渠道、偏好及投递记录规则，不提交业务事务。"""
    disabled = await repository.disabled_preferences(session, scene.id, user_ids) if user_ids else set()
    external = [] if is_in_app_only_scene(scene.scene_key) else [
        code for code in EXTERNAL_CHANNELS if code in channels and code in templates
    ]
    bindings = {code: await repository.active_bindings(session, code, user_ids) for code in external}
    in_app_on = CHANNEL_IN_APP in channels
    force_in_app = is_critical_scene(scene.scene_key)
    due_at = confirmation_deadline(scene.scene_key, utc_now()) if requires_confirmation else None
    delivery_count = 0
    for user_id in user_ids:
        in_app = force_in_app or (in_app_on and (user_id, CHANNEL_IN_APP) not in disabled)
        plans: list[tuple[str, NtfChannelBinding | None]] = [
            (code, bindings[code].get(user_id)) for code in external if (user_id, code) not in disabled
        ]
        reachable_external = any(binding is not None for _, binding in plans)
        # 渠道降级：外部渠道都不可达时仍发站内信
        if not in_app and not reachable_external and scene.fallback_policy_code == "all":
            in_app = True
        recipient = repository.add(
            session,
            NtfRecipient(
                org_id=notification.org_id,
                notification_id=notification.id,
                user_id=user_id,
                status_code="unread" if in_app else "archived",
                requires_confirmation=requires_confirmation,
                confirm_due_at=due_at,
                created_by=created_by,
                updated_by=created_by,
            ),
        )
        await session.flush()
        if in_app_on or force_in_app:
            repository.add(
                session,
                NtfDeliveryLog(
                    org_id=notification.org_id,
                    recipient_id=recipient.id,
                    channel_code=CHANNEL_IN_APP,
                    provider_code=None,
                    target_address=str(user_id),
                    status_code="sent" if in_app else "skipped",
                    error_message=None if in_app else "用户关闭了站内信",
                    created_by=created_by,
                ),
            )
            delivery_count += int(in_app)
        for code, binding in plans:
            request_payload = _wechat_request_payload(code, templates[code], context, notification.redirect_url or "")
            repository.add(
                session,
                NtfDeliveryLog(
                    org_id=notification.org_id,
                    recipient_id=recipient.id,
                    channel_code=code,
                    provider_code=binding.provider_code if binding else "wechat",
                    target_address=binding.external_user_no if binding else None,
                    status_code="pending" if binding else "skipped",
                    request_payload=request_payload,
                    error_message=None if binding else "用户未绑定该渠道",
                    created_by=created_by,
                ),
            )
            delivery_count += int(binding is not None)

    return delivery_count


async def supplement_notification(
    session: AsyncSession, notification: NtfNotification, user_ids: list[UUID],
    *, requires_confirmation: bool = False, created_by: UUID | None = None,
) -> int:
    """业务方先授权通知及目标用户；通知中心只给尚无收件记录的有效账号补发。"""
    scene = await repository.scene_by_id(session, notification.scene_id)
    if scene is None or not scene.is_active:
        raise _bad_request("通知场景未启用，不能补发")
    existing = {row.user_id for row in await repository.notification_recipients(session, notification.id)}
    wanted = await repository.active_user_ids(session, user_ids)
    missing = sorted(wanted - existing, key=str)
    channels = set((await repository.active_channel_map(session, [scene.id])).get(scene.id, []))
    templates = {row.channel_code: row for row in await repository.scene_templates(session, scene.id, active_only=True)}
    context = {
        "title": notification.title, "content": notification.content, **(notification.payload or {}),
        "scene_key": scene.scene_key, "scene_name": scene.scene_name, "module_code": scene.module_code,
        "business_type_code": notification.business_type_code or "",
        "business_id": str(notification.business_id or ""),
    }
    await _deliver_to_users(
        session, notification=notification, scene=scene, user_ids=missing, channels=channels,
        templates=templates, context=context, requires_confirmation=requires_confirmation, created_by=created_by,
    )
    await session.flush()
    return len(missing)


async def active_notification_user_ids(session: AsyncSession, user_ids: list[UUID]) -> list[UUID]:
    """业务方按关系选定收件人后，排除停用和已删除的租户账号。"""
    return sorted(await repository.active_user_ids(session, user_ids), key=str)


async def retry_failed_notification(
    session: AsyncSession, notification: NtfNotification, user_ids: list[UUID],
    *, created_by: UUID | None = None,
) -> int:
    """仅重试当前仍可接收此业务消息的账号；保留失败记录，成功和待发记录不重复投递。"""
    scene = await repository.scene_by_id(session, notification.scene_id)
    if scene is None or not scene.is_active:
        raise _bad_request("通知场景未启用，不能重试")
    if is_in_app_only_scene(scene.scene_key):
        return 0
    channels = set((await repository.active_channel_map(session, [scene.id])).get(scene.id, []))
    templates = {row.channel_code: row for row in await repository.scene_templates(session, scene.id, active_only=True)}
    context = {
        "title": notification.title, "content": notification.content, **(notification.payload or {}),
        "scene_key": scene.scene_key, "scene_name": scene.scene_name, "module_code": scene.module_code,
        "business_type_code": notification.business_type_code or "",
        "business_id": str(notification.business_id or ""),
    }
    disabled = await repository.disabled_preferences(session, scene.id, user_ids)
    active_users = await repository.active_user_ids(session, user_ids)
    bindings = {code: await repository.active_bindings(session, code, user_ids) for code in EXTERNAL_CHANNELS}
    retried = 0
    latest = await repository.latest_delivery_logs(session, [notification.id])
    for _, row, user_id in latest:
        if row.status_code != "failed" or row.channel_code not in EXTERNAL_CHANNELS:
            continue
        if (user_id not in active_users or row.channel_code not in channels or
                row.channel_code not in templates or (user_id, row.channel_code) in disabled):
            continue
        binding = bindings[row.channel_code].get(user_id)
        if binding is None:
            continue
        repository.add(session, NtfDeliveryLog(
            org_id=row.org_id, recipient_id=row.recipient_id, channel_code=row.channel_code,
            provider_code=binding.provider_code, target_address=binding.external_user_no,
            status_code="pending", created_by=created_by,
            request_payload=_wechat_request_payload(row.channel_code, templates[row.channel_code], context, notification.redirect_url or ""),
        ))
        retried += 1
    await session.flush()
    return retried


async def notification_delivery_summaries(
    session: AsyncSession, notification_ids: list[UUID],
) -> dict[UUID, dict[str, int]]:
    """只返回投递计数，不把渠道账号、请求报文及供应商错误交给业务页面。"""
    summaries = {key: {"in_app_sent_count": 0, "external_sent_count": 0,
                       "external_failed_count": 0, "external_pending_count": 0} for key in notification_ids}
    for notification_id, row, _ in await repository.latest_delivery_logs(session, notification_ids):
        counts = summaries[notification_id]
        if row.channel_code == CHANNEL_IN_APP and row.status_code == "sent":
            counts["in_app_sent_count"] += 1
        elif row.channel_code in EXTERNAL_CHANNELS and row.status_code in {"sent", "failed", "pending"}:
            counts[f"external_{row.status_code}_count"] += 1
    return summaries


# ───────── 外部渠道投递 ─────────
async def _send_one(channel_code: str, row: NtfDeliveryLog) -> dict[str, Any]:
    payload = row.request_payload if isinstance(row.request_payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    template_id = str(payload.get("template_id") or "").strip()
    if not template_id:
        raise AppException("模板 ID 为空")
    if channel_code == CHANNEL_WECHAT_SERVICE:
        from app.integrations.wechat_official import client

        result = await client.send_template_message(
            openid=str(row.target_address),
            template_id=template_id,
            url=str(payload.get("url") or "").strip() or None,
            data=data,
            miniprogram=payload.get("miniprogram") if isinstance(payload.get("miniprogram"), dict) else None,
        )
    else:
        from app.integrations.wechat_miniapp import client

        result = await client.send_subscribe_message(
            openid=str(row.target_address),
            template_id=template_id,
            page=str(payload.get("page") or "").strip() or None,
            data=data,
            miniprogram_state=str(payload.get("miniprogram_state") or "").strip() or None,
            lang=str(payload.get("lang") or "zh_CN"),
        )
    return result.model_dump(mode="json")


async def process_pending_deliveries(session: AsyncSession, *, channel_code: str | None = None, limit: int = 50) -> DeliveryProcessResult:
    """投递当前租户的待发送外部渠道消息（服务号、小程序订阅消息），并提交。"""
    result = DeliveryProcessResult()
    for code in [channel_code] if channel_code else list(EXTERNAL_CHANNELS):
        if code not in EXTERNAL_CHANNELS:
            raise _bad_request("该渠道不需要后台投递")
        rows = await repository.pending_deliveries(session, code, limit)
        result.scanned_count += len(rows)
        for row, _notification, _scene_key in rows:
            if not row.target_address:
                row.status_code = "skipped"
                row.error_message = "用户未绑定该渠道"
                result.skipped_count += 1
            else:
                try:
                    row.response_payload = await _send_one(code, row)
                    row.status_code = "sent"
                    row.error_message = None
                    result.sent_count += 1
                except AppException as exc:
                    row.status_code = "failed"
                    row.error_message = exc.message[:2000]
                    row.response_payload = {"error": exc.message, "status_code": exc.status_code}
                    result.failed_count += 1
                except Exception as exc:  # noqa: BLE001 - 每条投递单独记录失败
                    row.status_code = "failed"
                    row.error_message = str(exc)[:2000]
                    row.response_payload = {"error": str(exc)}
                    result.failed_count += 1
            repository.add(session, row)
    await repository.commit(session)
    return result


async def process_pending_deliveries_current_tenant(limit: int = 50) -> DeliveryProcessResult:
    """定时任务（见 jobs.py）：投递当前租户的待发送消息。"""
    async with get_session_context() as session:
        return await process_pending_deliveries(session, limit=limit)


_notification_hooks: dict[str, list] = {"confirmed": []}


def register_notification_hook(kind: str, fn) -> None:
    if kind != "confirmed":
        raise ValueError("通知扫描任务应由所属模块的 jobs.py 注册")
    if fn not in _notification_hooks[kind]:
        _notification_hooks[kind].append(fn)


async def _run_confirmation_hooks(session, recipient, user):
    from app.framework.deployment import module_plugin_owner
    from app.framework.tenant_plugins import is_plugin_enabled_for_schema
    from app.framework.db.tenant import get_tenant_schema
    for hook in _notification_hooks["confirmed"]:
        parts = hook.__module__.split(".")
        owner = module_plugin_owner(parts[2]) if len(parts) > 2 else None
        if owner and not await is_plugin_enabled_for_schema(get_tenant_schema(), owner):
            continue
        await hook(session, recipient, user)


# ───────── 渠道绑定（供登录、小程序等模块调用） ─────────
async def bind_channel_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    channel_code: str,
    appid: str,
    external_user_no: str,
    unionid: str | None = None,
    provider_code: str = "wechat",
) -> NtfChannelBinding:
    """为用户绑定外部通知渠道（同一外部账号只归属一个用户；同一用户同一渠道只保留一个有效绑定）。只 flush。"""
    appid, external_user_no = appid.strip(), external_user_no.strip()
    if not appid or not external_user_no:
        raise _bad_request("appid / openid 不能为空")
    if channel_code not in EXTERNAL_CHANNELS:
        raise _bad_request("仅支持绑定服务号或小程序订阅消息渠道")
    now = utc_now()
    binding = await repository.binding_by_external(
        session, channel_code=channel_code, provider_code=provider_code, appid=appid, external_user_no=external_user_no
    )
    if binding is None:
        binding = repository.add(
            session,
            NtfChannelBinding(
                user_id=user_id,
                channel_code=channel_code,
                provider_code=provider_code,
                appid=appid,
                external_user_no=external_user_no,
                unionid=unionid or None,
                bound_at=now,
                is_active=True,
                created_by=user_id,
                updated_by=user_id,
            ),
        )
    else:
        binding.user_id = user_id
        binding.unionid = unionid or binding.unionid
        binding.is_active = True
        binding.bound_at = now
        binding.updated_by = user_id
        repository.add(session, binding)
    await session.flush()
    await repository.deactivate_other_bindings(session, user_id=user_id, channel_code=channel_code, keep_id=binding.id)
    await session.flush()
    return binding


# ───────── 场景配置 ─────────
def _check_code(value: str | None, allowed: set[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise _bad_request(f"无效的{label}：{value}")


async def _route_rows(session: AsyncSession, routes: list[RouteWrite]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for route in routes:
        _check_code(route.org_scope_code, ORG_SCOPES, "组织范围")
        permission_id = route.permission_id
        if route.target_type_code == "permission" and permission_id is None:
            permission = await repository.permission_by_key(session, route.permission_key or "")
            if permission is None:
                raise _bad_request(f"接收权限不存在：{route.permission_key}")
            permission_id = permission.id
        row = {
            "target_type_code": route.target_type_code,
            "role_id": route.role_id if route.target_type_code == "role" else None,
            "user_id": route.user_id if route.target_type_code == "user" else None,
            "permission_id": permission_id if route.target_type_code == "permission" else None,
            "actor_key": (route.actor_key or "").strip() or None if route.target_type_code == "actor" else None,
            "org_scope_code": route.org_scope_code,
            "is_active": route.is_active,
        }
        key = tuple(str(row[k]) for k in ("target_type_code", "role_id", "user_id", "permission_id", "actor_key", "org_scope_code"))
        if key in seen:
            raise _bad_request("接收人路由存在重复配置")
        seen.add(key)
        result.append(row)
    if any(r["role_id"] for r in result):
        roles = await repository.roles_by_ids(session, [r["role_id"] for r in result if r["role_id"]])
        if len(roles) != len({r["role_id"] for r in result if r["role_id"]}):
            raise _bad_request("接收角色不存在")
    if any(r["user_id"] for r in result):
        users = await repository.users_by_ids(session, [r["user_id"] for r in result if r["user_id"]])
        if len(users) != len({r["user_id"] for r in result if r["user_id"]}):
            raise _bad_request("接收用户不存在")
    if any(r["permission_id"] for r in result):
        perms = await repository.permissions_by_ids(session, [r["permission_id"] for r in result if r["permission_id"]])
        if len(perms) != len({r["permission_id"] for r in result if r["permission_id"]}):
            raise _bad_request("接收权限不存在")
    return result


def _template_rows(templates: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows = []
    for item in templates:
        _check_code(item.channel_code, CHANNELS, "渠道")
        if item.channel_code in seen:
            raise _bad_request("同一场景同一渠道只能配置一个模板")
        seen.add(item.channel_code)
        if item.channel_code in EXTERNAL_CHANNELS and item.is_active and not (item.wechat_template_no or "").strip():
            raise _bad_request("启用微信模板时必须填写模板编号")
        data = item.model_dump()
        data["wechat_template_no"] = (item.wechat_template_no or "").strip() or None
        rows.append(data)
    return rows


async def scene_config(session: AsyncSession, scene: NtfScene) -> SceneConfig:
    channels = await repository.scene_channels(session, scene.id)
    templates = await repository.scene_templates(session, scene.id)
    routes = await repository.scene_routes(session, scene.id)
    roles = await repository.roles_by_ids(session, [r.role_id for r in routes if r.role_id])
    users = await repository.users_by_ids(session, [r.user_id for r in routes if r.user_id])
    perms = await repository.permissions_by_ids(session, [r.permission_id for r in routes if r.permission_id])
    route_items = []
    for route in routes:
        role, user, perm = roles.get(route.role_id), users.get(route.user_id), perms.get(route.permission_id)
        route_items.append(
            RouteItem(
                **route.model_dump(include={"id", "scene_id", "target_type_code", "role_id", "user_id", "permission_id", "actor_key", "org_scope_code", "is_active"}),
                role={"id": role.id, "role_no": role.role_no, "role_name": role.role_name} if role else None,
                user={"id": user.id, "display_name": user.display_name} if user else None,
                permission={"id": perm.id, "permission_key": perm.permission_key, "permission_name": perm.permission_name, "module_code": perm.module_code}
                if perm
                else None,
            )
        )
    item = SceneItem.model_validate(scene)
    item.channel_codes = [row.channel_code for row in channels if row.is_active]
    return SceneConfig(
        scene=item,
        channels=[SceneChannelItem.model_validate(row) for row in channels],
        templates=[TemplateItem.model_validate(row) for row in templates],
        routes=route_items,
    )


class NotificationCenterService:
    async def list_scenes(self, params: SceneListQuery) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_scenes(
                session, keyword=params.keyword, module_code=params.module_code, is_active=params.is_active, page=params.page, page_size=params.page_size
            )
            channel_map = await repository.active_channel_map(session, [row.id for row in rows])
        items = []
        for row in rows:
            item = SceneItem.model_validate(row)
            item.channel_codes = channel_map.get(row.id, [])
            items.append(item.model_dump(mode="json"))
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def get_scene(self, scene_id: UUID) -> SceneConfig | None:
        async with get_session_context() as session:
            scene = await repository.scene_by_id(session, scene_id)
            return await scene_config(session, scene) if scene else None

    async def create_scene(self, payload: SceneCreate, user: AuthenticatedUser) -> SceneConfig:
        _check_code(payload.severity_code, SEVERITIES, "重要程度")
        _check_code(payload.fallback_policy_code, FALLBACK_POLICIES, "降级策略")
        for channel in payload.channels:
            _check_code(channel.channel_code, CHANNELS, "渠道")
        async with get_session_context() as session:
            key = payload.scene_key.strip()
            if not key:
                raise _bad_request("场景标识不能为空")
            if await repository.scene_key_exists(session, key):
                raise AppException("场景标识已存在", status_code=status.HTTP_409_CONFLICT)
            templates = _template_rows(payload.templates)
            routes = await _route_rows(session, payload.routes)
            scene = repository.add(
                session,
                NtfScene(
                    **payload.model_dump(include=SCENE_FIELDS),
                    created_by=user.user_id,
                    updated_by=user.user_id,
                ),
            )
            scene.scene_key = key
            await session.flush()
            await repository.upsert_channels(session, scene.id, [c.model_dump() for c in payload.channels], user.user_id)
            await repository.upsert_templates(session, scene.id, templates, user.user_id)
            await repository.replace_routes(session, scene.id, routes, user.user_id)
            await session.commit()
            return await scene_config(session, scene)

    async def update_scene(self, scene_id: UUID, payload: SceneUpdate, user: AuthenticatedUser) -> SceneConfig | None:
        data = payload.model_dump(exclude_unset=True)
        _check_code(data.get("severity_code"), SEVERITIES, "重要程度")
        _check_code(data.get("fallback_policy_code"), FALLBACK_POLICIES, "降级策略")
        async with get_session_context() as session:
            scene = await repository.scene_by_id(session, scene_id, for_update=True)
            if scene is None:
                return None
            if "scene_key" in data:
                key = (data["scene_key"] or "").strip()
                if not key:
                    raise _bad_request("场景标识不能为空")
                if await repository.scene_key_exists(session, key, exclude_id=scene.id):
                    raise AppException("场景标识已存在", status_code=status.HTTP_409_CONFLICT)
                data["scene_key"] = key
            for field in ("scene_key", "scene_name", "module_code", "description", "severity_code", "fallback_policy_code", "is_active"):
                if field in data and (data[field] is not None or field == "description"):
                    setattr(scene, field, data[field])
            scene.updated_by = user.user_id
            scene.updated_at = utc_now()
            repository.add(session, scene)
            if payload.channels is not None:
                for channel in payload.channels:
                    _check_code(channel.channel_code, CHANNELS, "渠道")
                await repository.upsert_channels(session, scene.id, [c.model_dump() for c in payload.channels], user.user_id)
            if payload.templates is not None:
                await repository.upsert_templates(session, scene.id, _template_rows(payload.templates), user.user_id)
            if payload.routes is not None:
                await repository.replace_routes(session, scene.id, await _route_rows(session, payload.routes), user.user_id)
            await session.commit()
            return await scene_config(session, scene)

    async def delete_scene(self, scene_id: UUID, user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            scene = await repository.scene_by_id(session, scene_id, for_update=True)
            if scene is None:
                return False
            await repository.soft_delete_scene(session, scene, user.user_id)
            await session.commit()
            return True

    async def route_options(self) -> dict[str, Any]:
        async with get_session_context() as session:
            options = await repository.route_options(session)
        return {
            "roles": [{"id": str(r.id), "role_no": r.role_no, "role_name": r.role_name} for r in options["roles"]],
            "permissions": [
                {"id": str(p.id), "permission_key": p.permission_key, "permission_name": p.permission_name, "module_code": p.module_code}
                for p in options["permissions"]
            ],
        }

    async def search_users(self, keyword: str | None, limit: int) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            rows = await repository.search_users(session, keyword, limit)
        return [{"id": str(r.id), "display_name": r.display_name} for r in rows]

    # ───────── 发送与投递 ─────────
    async def publish(self, payload: PublishPayload, user: AuthenticatedUser) -> NotifyResult:
        async with get_session_context() as session:
            result = await notify(
                session,
                scene_key=payload.scene_key,
                recipients=payload.recipients,
                actors=payload.actors,
                business_type_code=payload.business_type_code,
                business_id=payload.business_id,
                payload=payload.payload,
                org_id=payload.org_id or user.org_id,
                event_key=payload.event_key,
                redirect_url=payload.redirect_url,
                created_by=user.user_id,
            )
            await session.commit()
            return result

    async def send_pending(self, channel_code: str | None, limit: int) -> DeliveryProcessResult:
        async with get_session_context() as session:
            return await process_pending_deliveries(session, channel_code=channel_code, limit=limit)

    # ───────── 查询 ─────────
    async def list_history(self, params: HistoryListQuery) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_notifications(session, params)
            ids = [row.id for row, _ in rows]
            recipient_stats = await repository.recipient_stats(session, ids)
            delivery_stats = await repository.delivery_stats(session, ids)
        items = []
        for row, scene_key in rows:
            count, read = recipient_stats.get(row.id, (0, 0))
            items.append(
                HistoryItem(
                    **row.model_dump(exclude={"payload", "flex_form"}),
                    scene_key=scene_key,
                    recipient_count=count,
                    read_count=read,
                    unread_count=max(count - read, 0),
                    delivery_stats=delivery_stats.get(row.id, {}),
                ).model_dump(mode="json")
            )
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def list_recipients(self, notification_id: UUID, params: RecipientListQuery) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_recipients(
                session, notification_id, status_code=params.status_code, page=params.page, page_size=params.page_size
            )
        items = [
            RecipientItem(
                id=r.id, user_id=r.user_id, display_name=name, status_code=r.status_code, read_at=r.read_at, created_at=r.created_at
            ).model_dump(mode="json")
            for r, name in rows
        ]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def list_delivery_logs(self, params: DeliveryLogListQuery) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_delivery_logs(session, params)
        items = [
            DeliveryLogItem(
                **log.model_dump(exclude={"org_id", "created_by"}),
                notification_id=notification.id,
                scene_key=scene_key,
                title=notification.title,
                user_id=recipient.user_id,
                display_name=name,
            ).model_dump(mode="json")
            for log, recipient, notification, scene_key, name in rows
        ]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def list_event_logs(self, params: EventLogListQuery) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list_event_logs(session, params)
        items = [
            EventLogItem(**row.model_dump(exclude={"org_id", "created_by"}), scene_key=scene_key).model_dump(mode="json")
            for row, scene_key in rows
        ]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    # ───────── 我的通知 ─────────
    async def list_mine(self, params: MineListQuery, user: AuthenticatedUser) -> dict[str, Any]:
        from .scene_policies import individual_read_scene_keys
        individual_read = individual_read_scene_keys()
        async with get_session_context() as session:
            rows, total = await repository.list_mine(
                session, user.user_id, status_code=params.status_code, scene_key=params.scene_key, page=params.page, page_size=params.page_size
            )
        items = [
            MineItem(
                recipient_id=r.id,
                notification_id=n.id,
                scene_key=scene_key,
                requires_individual_read=scene_key in individual_read,
                scene_name_snapshot=n.scene_name_snapshot,
                title=n.title,
                content=n.content,
                severity_code=n.severity_code,
                status_code=r.status_code,
                read_at=r.read_at,
                requires_confirmation=r.requires_confirmation,
                confirmed_at=r.confirmed_at,
                business_type_code=n.business_type_code,
                business_id=n.business_id,
                redirect_url=n.redirect_url,
                targets=notification_targets(n.payload, n.redirect_url),
                occurred_at=n.occurred_at,
                created_at=r.created_at,
            ).model_dump(mode="json")
            for r, n, scene_key in rows
        ]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def mine_detail(self, recipient_id: UUID, user: AuthenticatedUser):
        async with get_session_context() as session:
            row = await repository.mine_detail(session, recipient_id, user.user_id)
            if row is None:
                return None
            return {"title": row.title, "content": row.content, "scene_name": row.scene_name_snapshot or "消息",
                    "occurred_at": row.occurred_at.isoformat()}

    async def unread_count(self, user: AuthenticatedUser) -> int:
        async with get_session_context() as session:
            return await repository.unread_count(session, user.user_id)

    async def mark_read(self, recipient_id: UUID, user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            recipient = await repository.recipient_for_user(session, recipient_id, user.user_id)
            if recipient is None:
                return False
            if recipient.status_code != "read":
                recipient.status_code = "read"
                recipient.read_at = utc_now()
                recipient.updated_by = user.user_id
                repository.add(session, recipient)
                await session.commit()
            return True

    async def mark_confirmed(self, recipient_id: UUID, user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            recipient = await repository.recipient_for_user(session, recipient_id, user.user_id)
            if recipient is None or not recipient.requires_confirmation:
                return False
            if recipient.confirmed_at is None:
                recipient.confirmed_at = utc_now()
                if recipient.status_code != "read":
                    recipient.status_code = "read"
                    recipient.read_at = recipient.confirmed_at
                recipient.updated_by = user.user_id
                repository.add(session, recipient)
                await _run_confirmation_hooks(session, recipient, user)
                await session.commit()
            return True

    async def mark_all_read(self, user: AuthenticatedUser) -> int:
        async with get_session_context() as session:
            count = await repository.mark_all_read(session, user.user_id)
            await session.commit()
            return count

    # ───────── 偏好 ─────────
    async def list_preferences(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            scenes = await repository.list_active_scenes(session)
            channel_map = await repository.active_channel_map(session, [s.id for s in scenes])
            prefs = await repository.user_preferences(session, user.user_id)
        items = []
        for scene in scenes:
            for code in channel_map.get(scene.id, []):
                pref = prefs.get((scene.id, code))
                items.append(
                    PreferenceItem(
                        scene_id=scene.id,
                        scene_key=scene.scene_key,
                        scene_name=scene.scene_name,
                        module_code=scene.module_code,
                        channel_code=code,
                        is_enabled_by_user=pref.is_enabled_by_user if pref else True,
                    ).model_dump(mode="json")
                )
        return items

    async def save_preferences(self, items: list[PreferenceWrite], user: AuthenticatedUser) -> int:
        async with get_session_context() as session:
            prefs = await repository.user_preferences(session, user.user_id)
            for item in items:
                _check_code(item.channel_code, CHANNELS, "渠道")
                if await repository.scene_by_id(session, item.scene_id) is None:
                    raise _bad_request("通知场景不存在")
                row = prefs.get((item.scene_id, item.channel_code))
                if row is None:
                    row = NtfPreference(
                        user_id=user.user_id, scene_id=item.scene_id, channel_code=item.channel_code, created_by=user.user_id
                    )
                    prefs[(item.scene_id, item.channel_code)] = row
                row.is_enabled_by_user = item.is_enabled_by_user
                row.updated_by = user.user_id
                repository.add(session, row)
            await session.commit()
            return len(items)

    # ───────── 渠道绑定 ─────────
    async def list_bindings(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            rows = await repository.user_bindings(session, user.user_id)
        return [ChannelBindingItem.model_validate(row).model_dump(mode="json") for row in rows]

    async def bind_channel(self, payload: ChannelBindingCreate, user: AuthenticatedUser) -> ChannelBindingItem:
        async with get_session_context() as session:
            binding = await bind_channel_for_user(
                session,
                user_id=user.user_id,
                channel_code=payload.channel_code,
                appid=payload.appid,
                external_user_no=payload.external_user_no,
                unionid=payload.unionid,
                provider_code=payload.provider_code,
            )
            await session.commit()
            return ChannelBindingItem.model_validate(binding)

    async def unbind_channel(self, binding_id: UUID, user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            binding = await repository.binding_for_user(session, binding_id, user.user_id)
            if binding is None:
                return False
            binding.is_active = False
            binding.deleted_at = utc_now()
            binding.deleted_by = user.user_id
            repository.add(session, binding)
            await session.commit()
            return True

    # ───────── 服务号绑定（OAuth） ─────────
    async def build_wechat_service_bind_url(self, user: AuthenticatedUser) -> WechatServiceBindUrlData:
        from app.integrations.redis_client import get_redis

        settings = get_settings()
        if not (settings.wechat_official_appid or "").strip() or not (settings.wechat_official_secret or "").strip():
            raise AppException("未配置微信服务号参数 WECHAT_OFFICIAL_APPID / WECHAT_OFFICIAL_SECRET", status_code=500)
        callback_url = _require_url(settings.wechat_official_bind_callback_url, "WECHAT_OFFICIAL_BIND_CALLBACK_URL")
        state = secrets.token_urlsafe(32)
        ttl = settings.wechat_official_bind_state_ttl_seconds
        # 回调不带登录态：在状态里记下租户 schema 与 sys_user.id
        state_payload = {"user_id": str(user.user_id), "tenant_schema": user.tenant_schema}
        await get_redis().set(f"{WECHAT_SERVICE_BIND_STATE_PREFIX}{state}", json.dumps(state_payload), ex=ttl)
        return WechatServiceBindUrlData(authorize_url=_oauth_entry_url(callback_url, state), expires_in=ttl)

    async def wechat_service_binding_status(self, user: AuthenticatedUser) -> WechatServiceBindingStatusData:
        from app.integrations.wechat_official import client

        async with get_session_context() as session:
            binding = (await repository.active_bindings(session, CHANNEL_WECHAT_SERVICE, [user.user_id])).get(user.user_id)
        if binding is None:
            return WechatServiceBindingStatusData(bound=False, subscribed=False, needs_bind=True, needs_follow=True)
        try:
            result = await client.get_subscribe_status(openid=binding.external_user_no)
        except AppException:
            return WechatServiceBindingStatusData(bound=True, subscribed=None)
        return WechatServiceBindingStatusData(bound=True, subscribed=result.subscribed, needs_follow=not result.subscribed)

    async def wechat_service_oauth_redirect_url(self, state: str) -> str:
        from app.integrations.redis_client import get_redis

        settings = get_settings()
        state = (state or "").strip()
        if not state or not await get_redis().exists(f"{WECHAT_SERVICE_BIND_STATE_PREFIX}{state}"):
            raise _bad_request("微信服务号授权已过期，请重新发起绑定")
        appid = (settings.wechat_official_appid or "").strip()
        if not appid:
            raise AppException("未配置微信服务号 appid", status_code=500)
        callback_url = _require_url(settings.wechat_official_bind_callback_url, "WECHAT_OFFICIAL_BIND_CALLBACK_URL")
        authorize_url = _require_url(settings.wechat_official_oauth_authorize_url, "WECHAT_OFFICIAL_OAUTH_AUTHORIZE_URL")
        query = urlencode({"appid": appid, "redirect_uri": callback_url, "response_type": "code", "scope": "snsapi_base", "state": state})
        return f"{authorize_url}?{query}#wechat_redirect"

    async def wechat_service_oauth_callback(self, *, code: str, state: str) -> WechatServiceBindCallbackResult:
        from app.integrations.redis_client import get_redis
        from app.integrations.wechat_official import client

        settings = get_settings()
        state, code = (state or "").strip(), (code or "").strip()
        if not state or not code:
            raise _bad_request("微信服务号授权参数缺失")
        raw = await get_redis().eval(
            "local v=redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]); end; return v",
            1,
            f"{WECHAT_SERVICE_BIND_STATE_PREFIX}{state}",
        )
        try:
            state_payload = json.loads(str(raw)) if raw else None
            user_id = UUID(str(state_payload["user_id"]))
            tenant_schema = str(state_payload["tenant_schema"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise _bad_request("微信服务号授权已过期，请重新发起绑定") from exc
        oauth = await client.oauth2_access_token(code=code)
        appid = (settings.wechat_official_appid or "").strip()
        with use_tenant_schema(tenant_schema):
            async with get_session_context() as session:
                await bind_channel_for_user(
                    session, user_id=user_id, channel_code=CHANNEL_WECHAT_SERVICE, appid=appid, external_user_no=oauth.openid, unionid=oauth.unionid
                )
                await session.commit()
        try:
            subscribed = (await client.get_subscribe_status(openid=oauth.openid)).subscribed
        except AppException:
            subscribed = None
        message = "服务号通知已绑定，请关注服务号后才能接收提醒" if subscribed is False else "服务号通知绑定成功"
        return WechatServiceBindCallbackResult(
            bound=True, message=message, redirect_url=_with_bind_result(settings.wechat_official_bind_success_redirect_url, True, message)
        )

    def wechat_service_bind_failure_redirect(self, message: str) -> str | None:
        return _with_bind_result(get_settings().wechat_official_bind_failure_redirect_url, False, message)



def _require_url(value: str | None, field_name: str) -> str:
    clean = (value or "").strip()
    if not clean.startswith(("http://", "https://")):
        raise AppException(f"{field_name} 必须是完整 URL", status_code=500)
    if get_settings().app_env == "production" and not clean.startswith("https://"):
        raise AppException(f"生产环境 {field_name} 必须使用 HTTPS", status_code=500)
    return clean


def _with_bind_result(base_url: str | None, success: bool, message: str) -> str | None:
    clean = (base_url or "").strip()
    if not clean:
        return None
    separator = "&" if "?" in clean else "?"
    return f"{clean}{separator}{urlencode({'wechat_service_bind': 'success' if success else 'failed', 'message': message})}"


def _oauth_entry_url(callback_url: str, state: str) -> str:
    parts = urlsplit(callback_url)
    path = parts.path[: -len("/oauth-callback")] if parts.path.endswith("/oauth-callback") else parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, f"{path}/oauth-entry", urlencode({"state": state}), ""))


service = NotificationCenterService()
