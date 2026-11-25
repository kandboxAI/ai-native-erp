"""通知中心接口：场景配置、发送、通知历史与日志、我的通知、偏好、渠道绑定。"""

from __future__ import annotations

import logging
from html import escape
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.integrations.oss_storage import get_object_access_url, is_oss_configured

from .schemas import (
    ChannelBindingCreate,
    DeliveryLogListQuery,
    EventLogListQuery,
    HistoryListQuery,
    MineListQuery,
    PreferenceWrite,
    PublishPayload,
    RecipientListQuery,
    SceneCreate,
    SceneListQuery,
    SceneUpdate,
)
from .service import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notification_center", tags=["notification_center"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")


def _oss_object_from_url(value: str) -> tuple[str, str] | None:
    parsed = urlparse(value)
    host = parsed.netloc.split("@")[-1].split(":")[0]
    if ".oss-" not in host or not host.endswith(".aliyuncs.com"):
        return None
    bucket, _, _endpoint = host.partition(".oss-")
    key = unquote(parsed.path.lstrip("/"))
    if not bucket or not key:
        return None
    return bucket, key


def _safe_external_image_url(value: str | None) -> str | None:
    clean = (value or "").strip()
    if not clean.startswith(("https://", "http://")):
        return None
    oss_object = _oss_object_from_url(clean)
    if oss_object and is_oss_configured():
        bucket, key = oss_object
        try:
            clean = get_object_access_url(bucket, key).rstrip("?")
        except Exception:
            logger.warning(
                "wechat official qr code oss url resolve failed bucket=%s key=%s",
                bucket,
                key,
                exc_info=True,
            )
    return escape(clean, quote=True)


def _wechat_service_bind_result_page(*, success: bool, message: str) -> HTMLResponse:
    settings = get_settings()
    safe_message = escape(message or ("绑定成功" if success else "绑定失败"))
    account_name = escape((settings.wechat_official_account_name or "").strip() or "机构服务号")
    qr_code_url = _safe_external_image_url(settings.wechat_official_qr_code_url)
    title = "服务号通知绑定成功" if success else "服务号通知绑定失败"
    action_text = "返回小程序" if success else "返回重试"
    icon = "✓" if success else "!"
    follow_guide = ""
    if success:
        qr_html = (
            f'<img class="qr" src="{qr_code_url}" alt="{account_name}二维码">'
            if qr_code_url
            else '<div class="qr-empty">请配置服务号二维码</div>'
        )
        follow_guide = f"""
    <section class="follow">
      <h2>继续关注服务号</h2>
      <p class="hint">关注后才能接收合同签署、待确认事项等微信提醒。</p>
      {qr_html}
      <div class="search-box">
        <span>微信搜索</span>
        <strong>{account_name}</strong>
      </div>
      <p class="tip">可长按二维码保存图片，返回微信后扫码或搜索名称关注。</p>
    </section>"""
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7faf9;
      color: #1f2933;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .wrap {{
      width: 100%;
      box-sizing: border-box;
      padding: 40px 24px;
      text-align: center;
    }}
    .icon {{
      width: 72px;
      height: 72px;
      margin: 0 auto 24px;
      border-radius: 50%;
      background: {"#0f9f6e" if success else "#d64545"};
      color: #fff;
      font-size: 42px;
      line-height: 72px;
      font-weight: 700;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 24px;
      line-height: 1.35;
      font-weight: 700;
    }}
    p {{
      margin: 0 auto 24px;
      max-width: 320px;
      color: #667085;
      font-size: 16px;
      line-height: 1.65;
    }}
    .follow {{
      max-width: 340px;
      margin: 0 auto 28px;
      padding: 22px 18px;
      border: 1px solid #e4ebe8;
      border-radius: 12px;
      background: #fff;
      box-sizing: border-box;
    }}
    .follow h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.4;
    }}
    .hint {{
      margin-bottom: 16px;
      font-size: 14px;
    }}
    .qr {{
      display: block;
      width: 190px;
      height: 190px;
      object-fit: contain;
      margin: 0 auto 16px;
      border: 1px solid #eef2f0;
      border-radius: 8px;
      background: #fff;
    }}
    .qr-empty {{
      width: 190px;
      height: 190px;
      margin: 0 auto 16px;
      border: 1px dashed #b8c7c1;
      border-radius: 8px;
      color: #667085;
      font-size: 14px;
      line-height: 190px;
      background: #f8fbfa;
    }}
    .search-box {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 8px;
      background: #f2f7f5;
      font-size: 14px;
      color: #667085;
    }}
    .search-box strong {{
      min-width: 0;
      color: #1f2933;
      overflow-wrap: anywhere;
      text-align: right;
    }}
    .tip {{
      margin: 14px 0 0;
      font-size: 13px;
      color: #8a97a3;
    }}
    button {{
      border: 0;
      border-radius: 8px;
      padding: 12px 28px;
      background: #00695c;
      color: #fff;
      font-size: 16px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{safe_message}</p>
    {follow_guide}
    <button type="button" onclick="goBackToMiniapp()">{action_text}</button>
  </main>
  <script src="https://res.wx.qq.com/open/js/jweixin-1.6.0.js"></script>
  <script>
    function goBackToMiniapp() {{
      if (window.wx && wx.miniProgram && wx.miniProgram.navigateBack) {{
        wx.miniProgram.navigateBack({{ delta: 1 }});
        return;
      }}
      if (history.length > 1) {{
        history.back();
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(
        content=html,
        status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        headers={"Cache-Control": "no-store"},
    )


# ───────── 场景配置 ─────────
@router.get("/scenes")
async def list_scenes(
    params: SceneListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_scenes(params))


@router.get("/scenes/{scene_id}")
async def scene_detail(
    scene_id: UUID,
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:detail"])),
) -> dict[str, Any]:
    item = await service.get_scene(scene_id)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/scenes")
async def create_scene(
    payload: SceneCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["notification_center:create"])),
) -> dict[str, Any]:
    item = await service.create_scene(payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/scenes/{scene_id}")
async def update_scene(
    scene_id: UUID,
    payload: SceneUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["notification_center:update"])),
) -> dict[str, Any]:
    item = await service.update_scene(scene_id, payload, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.delete("/scenes/{scene_id}")
async def delete_scene(
    scene_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["notification_center:delete"])),
) -> dict[str, Any]:
    if not await service.delete_scene(scene_id, current_user):
        raise _not_found()
    return success_response({"deleted": True})


@router.get("/route-options")
async def route_options(
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:detail"])),
) -> dict[str, Any]:
    """路由可选的角色与权限。"""
    return success_response(await service.route_options())


@router.get("/route-options/users")
async def route_user_options(
    keyword: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:detail"])),
) -> dict[str, Any]:
    return success_response(await service.search_users(keyword, limit))


# ───────── 发送与投递 ─────────
@router.post("/publish")
async def publish(
    payload: PublishPayload,
    current_user: AuthenticatedUser = Depends(require_permissions(["notification_center:publish"])),
) -> dict[str, Any]:
    result = await service.publish(payload, current_user)
    return success_response(result.model_dump(mode="json"))


@router.post("/deliveries/send-pending")
async def send_pending_deliveries(
    channel_code: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:publish"])),
) -> dict[str, Any]:
    result = await service.send_pending(channel_code, limit)
    return success_response(result.model_dump(mode="json"))




# ───────── 通知历史与日志 ─────────
@router.get("/notifications")
async def list_notifications(
    params: HistoryListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_history(params))


@router.get("/notifications/{notification_id}/recipients")
async def list_notification_recipients(
    notification_id: UUID,
    params: RecipientListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_recipients(notification_id, params))


@router.get("/delivery-logs")
async def list_delivery_logs(
    params: DeliveryLogListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_delivery_logs(params))


@router.get("/event-logs")
async def list_event_logs(
    params: EventLogListQuery = Depends(),
    _: AuthenticatedUser = Depends(require_permissions(["notification_center:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_event_logs(params))


# ───────── 我的通知（登录即可） ─────────
@router.get("/mine/list")
async def list_mine(
    params: MineListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return paginated_response(**await service.list_mine(params, current_user))


@router.get("/mine/unread-count")
async def mine_unread_count(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response({"unread_count": await service.unread_count(current_user)})


@router.get("/mine/detail/{recipient_id}")
async def mine_detail(recipient_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)):
    data = await service.mine_detail(recipient_id, current_user)
    if data is None:
        raise _not_found()
    return success_response(data)


@router.post("/mine/read/{recipient_id}")
async def mark_mine_read(recipient_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    if not await service.mark_read(recipient_id, current_user):
        raise _not_found()
    return success_response({"updated": True})


@router.post("/mine/confirm/{recipient_id}")
async def confirm_mine(recipient_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    if not await service.mark_confirmed(recipient_id, current_user):
        raise _not_found()
    return success_response({"confirmed": True})


@router.post("/mine/read-all")
async def mark_mine_read_all(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response({"marked_count": await service.mark_all_read(current_user)})


@router.get("/mine/preferences")
async def list_mine_preferences(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.list_preferences(current_user))


@router.put("/mine/preferences")
async def save_mine_preferences(
    items: list[PreferenceWrite] = Body(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return success_response({"saved_count": await service.save_preferences(items, current_user)})


@router.get("/mine/channel-bindings")
async def list_mine_bindings(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.list_bindings(current_user))


@router.post("/mine/channel-bindings")
async def bind_mine_channel(
    payload: ChannelBindingCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    item = await service.bind_channel(payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.delete("/mine/channel-bindings/{binding_id}")
async def unbind_mine_channel(binding_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    if not await service.unbind_channel(binding_id, current_user):
        raise _not_found()
    return success_response({"deleted": True})


# ───────── 服务号绑定 ─────────
@router.get("/wechat-service/bind-url")
async def wechat_service_bind_url(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    result = await service.build_wechat_service_bind_url(current_user)
    return success_response(result.model_dump(mode="json"))


@router.get("/wechat-service/binding-status")
async def wechat_service_binding_status(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    result = await service.wechat_service_binding_status(current_user)
    return success_response(result.model_dump(mode="json"))


@router.get("/wechat-service/oauth-entry", response_model=None)
async def wechat_service_oauth_entry(state: str = Query(..., max_length=128)) -> RedirectResponse:
    return RedirectResponse(await service.wechat_service_oauth_redirect_url(state), status_code=status.HTTP_302_FOUND)


@router.get("/wechat-service/oauth-callback", response_model=None)
async def wechat_service_oauth_callback(
    code: str | None = Query(default=None, max_length=512),
    state: str | None = Query(default=None, max_length=128),
    errcode: str | None = Query(default=None, max_length=64),
) -> Any:
    if errcode:
        message = "微信服务号授权失败"
        redirect_url = service.wechat_service_bind_failure_redirect(message)
        if redirect_url:
            return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)
        return _wechat_service_bind_result_page(success=False, message=message)
    try:
        result = await service.wechat_service_oauth_callback(code=code or "", state=state or "")
    except AppException as exc:
        redirect_url = service.wechat_service_bind_failure_redirect(exc.message)
        if redirect_url:
            return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)
        return _wechat_service_bind_result_page(success=False, message=exc.message)
    if result.redirect_url:
        return RedirectResponse(result.redirect_url, status_code=status.HTTP_302_FOUND)
    return _wechat_service_bind_result_page(success=True, message=result.message)
