from __future__ import annotations

from typing import Any

from pydantic import BaseModel
import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.integrations.redis_client import get_redis


INVALID_ACCESS_TOKEN_ERRCODES = {40001, 40014, 42001}


def _http_error_message(exc: httpx.HTTPError) -> str:
    """Return a useful message even when httpx exception text is empty."""
    if isinstance(exc, httpx.TimeoutException):
        return "请求微信服务器超时，请稍后重试"
    if isinstance(exc, httpx.ConnectError):
        return "无法连接微信服务器，请检查后端网络、DNS或代理配置"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"微信服务器返回 HTTP {exc.response.status_code}"
    detail = str(exc).strip()
    return detail or f"网络请求异常（{exc.__class__.__name__}）"


class WechatSession(BaseModel):
    openid: str
    session_key: str | None = None
    unionid: str | None = None


class WechatPhoneNumber(BaseModel):
    phone_number: str
    pure_phone_number: str
    country_code: str | None = None


class WechatMiniappSubscribeSendResult(BaseModel):
    errcode: int = 0
    errmsg: str = "ok"
    raw: dict[str, Any]


class WechatMiniappClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _require_config(self) -> tuple[str, str]:
        appid = (self._settings.wechat_miniapp_appid or "").strip()
        secret = (self._settings.wechat_miniapp_secret or "").strip()
        if not appid or not secret:
            raise AppException("未配置微信小程序登录参数 WECHAT_MINIAPP_APPID / WECHAT_MINIAPP_SECRET", status_code=500)
        return appid, secret

    async def code2session(self, code: str) -> WechatSession:
        appid, secret = self._require_config()
        params = {
            "appid": appid,
            "secret": secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_miniapp_request_timeout_seconds) as client:
                resp = await client.get(self._settings.wechat_miniapp_code2session_url, params=params)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信登录接口调用失败：{_http_error_message(exc)}", status_code=502) from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise AppException("微信登录接口返回了非 JSON 数据，请检查网络代理配置", status_code=502) from exc
        if data.get("errcode"):
            raise AppException(f"微信登录失败：{data.get('errmsg') or data.get('errcode')}", status_code=400)
        openid = str(data.get("openid") or "").strip()
        if not openid:
            raise AppException("微信登录未返回 openid", status_code=400)
        return WechatSession(
            openid=openid,
            session_key=data.get("session_key"),
            unionid=data.get("unionid"),
        )

    async def get_phone_number(self, phone_code: str) -> WechatPhoneNumber:
        appid, secret = self._require_config()
        token = await self._get_access_token(appid, secret)
        url = f"{self._settings.wechat_miniapp_phone_url}?access_token={token}"
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_miniapp_request_timeout_seconds) as client:
                resp = await client.post(url, json={"code": phone_code})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信手机号接口调用失败：{exc}", status_code=502) from exc
        data = resp.json()
        if data.get("errcode"):
            raise AppException(f"微信手机号授权失败：{data.get('errmsg') or data.get('errcode')}", status_code=400)
        info = data.get("phone_info") or {}
        phone = str(info.get("purePhoneNumber") or info.get("phoneNumber") or "").strip()
        if not phone:
            raise AppException("微信手机号授权未返回手机号", status_code=400)
        return WechatPhoneNumber(
            phone_number=str(info.get("phoneNumber") or phone),
            pure_phone_number=phone,
            country_code=info.get("countryCode"),
        )

    async def get_unlimited_qr_code(self, *, scene: str, page: str) -> bytes:
        """生成可直接打开指定页面的微信小程序码。scene 最长 32 个可见字符。"""
        if not scene or len(scene) > 32:
            raise AppException("小程序码 scene 长度必须为 1-32 个字符", status_code=500)
        access_token = await self._get_access_token()
        url = f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={access_token}"
        configured_state = (self._settings.wechat_miniapp_qr_env_version or "release").strip().lower()
        # 兼容历史配置叫法；微信小程序码接口最终只接收 release/trial/develop。
        qr_env_version = {
            "formal": "release",
            "release": "release",
            "trial": "trial",
            "developer": "develop",
            "develop": "develop",
        }.get(configured_state)
        if qr_env_version is None:
            raise AppException(
                "微信小程序运行环境配置无效；本地开发请使用 develop，体验版使用 trial，正式版使用 formal/release",
                status_code=500,
            )
        payload = {
            "scene": scene,
            "page": page.lstrip("/"),
            "check_path": False,
            "env_version": qr_env_version,
            "width": 430,
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_miniapp_request_timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信小程序码生成失败：{exc}", status_code=502) from exc
        content_type = resp.headers.get("content-type", "")
        if "image" in content_type:
            return resp.content
        try:
            body = resp.json()
        except ValueError as exc:
            raise AppException("微信小程序码接口返回异常", status_code=502) from exc
        message = body.get("errmsg") or body.get("errcode")
        if int(body.get("errcode") or 0) == 41030:
            message = f"小程序页面未发布或路径不存在：{page}（请先在微信开发者工具上传对应版本）"
        raise AppException(f"微信小程序码生成失败：{message}", status_code=502)

    async def send_subscribe_message(
        self,
        *,
        openid: str,
        template_id: str,
        data: dict[str, Any],
        page: str | None = None,
        miniprogram_state: str | None = None,
        lang: str = "zh_CN",
    ) -> WechatMiniappSubscribeSendResult:
        access_token = await self._get_access_token()
        payload: dict[str, Any] = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
            "miniprogram_state": (miniprogram_state or self._settings.wechat_miniapp_subscribe_state or "formal").strip(),
            "lang": lang,
        }
        if page:
            payload["page"] = page.lstrip("/")

        body = await self._post_subscribe_message(access_token=access_token, payload=payload)
        errcode = int(body.get("errcode") or 0)
        if errcode in INVALID_ACCESS_TOKEN_ERRCODES:
            access_token = await self._get_access_token(force_refresh=True)
            body = await self._post_subscribe_message(access_token=access_token, payload=payload)
            errcode = int(body.get("errcode") or 0)
        errmsg = str(body.get("errmsg") or "")
        if errcode:
            raise AppException(f"微信小程序订阅消息发送失败：{errmsg or errcode}", status_code=502)
        return WechatMiniappSubscribeSendResult(errcode=errcode, errmsg=errmsg or "ok", raw=body)

    async def _post_subscribe_message(self, *, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        params = {"access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_miniapp_request_timeout_seconds) as client:
                resp = await client.post(self._settings.wechat_miniapp_subscribe_send_url, params=params, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信小程序订阅消息接口调用失败：{exc}", status_code=502) from exc
        try:
            return resp.json()
        except ValueError as exc:
            raise AppException("微信小程序订阅消息接口返回非 JSON 数据", status_code=502) from exc

    async def _get_access_token(
        self,
        appid: str | None = None,
        secret: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> str:
        if appid is None or secret is None:
            appid, secret = self._require_config()
        cache_key = f"wechat:miniapp:access_token:{appid}"
        redis = get_redis()
        cached = None if force_refresh else await redis.get(cache_key)
        if cached:
            return str(cached)

        params = {
            "grant_type": "client_credential",
            "appid": appid,
            "secret": secret,
            "force_refresh": force_refresh,
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_miniapp_request_timeout_seconds) as client:
                resp = await client.post(self._settings.wechat_miniapp_stable_token_url, json=params)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信 access_token 获取失败：{exc}", status_code=502) from exc
        data = resp.json()
        if data.get("errcode"):
            raise AppException(f"微信 access_token 获取失败：{data.get('errmsg') or data.get('errcode')}", status_code=400)
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise AppException("微信 access_token 为空", status_code=502)
        expires_in = int(data.get("expires_in") or 7200)
        await redis.set(cache_key, token, ex=max(60, expires_in - 300))
        return token


client = WechatMiniappClient()
