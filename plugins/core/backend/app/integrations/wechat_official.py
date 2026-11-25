from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.integrations.redis_client import get_redis


INVALID_ACCESS_TOKEN_ERRCODES = {40001, 40014, 42001}


class WechatOfficialTemplateSendResult(BaseModel):
    errcode: int = 0
    errmsg: str = "ok"
    msgid: int | None = None
    raw: dict[str, Any]


class WechatOfficialOAuthTokenResult(BaseModel):
    access_token: str
    expires_in: int | None = None
    refresh_token: str | None = None
    openid: str
    scope: str | None = None
    unionid: str | None = None
    raw: dict[str, Any]


class WechatOfficialSubscribeStatus(BaseModel):
    openid: str
    subscribed: bool
    raw: dict[str, Any]


class WechatOfficialClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _require_config(self) -> tuple[str, str]:
        appid = (self._settings.wechat_official_appid or "").strip()
        secret = (self._settings.wechat_official_secret or "").strip()
        if not appid or not secret:
            raise AppException(
                "未配置微信服务号参数 WECHAT_OFFICIAL_APPID / WECHAT_OFFICIAL_SECRET",
                status_code=500,
            )
        return appid, secret

    async def send_template_message(
        self,
        *,
        openid: str,
        template_id: str,
        data: dict[str, Any],
        url: str | None = None,
        miniprogram: dict[str, Any] | None = None,
    ) -> WechatOfficialTemplateSendResult:
        access_token = await self._get_access_token()
        payload: dict[str, Any] = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if url:
            payload["url"] = url
        if miniprogram:
            payload["miniprogram"] = miniprogram

        body = await self._post_template_message(access_token=access_token, payload=payload)
        errcode = int(body.get("errcode") or 0)
        if errcode in INVALID_ACCESS_TOKEN_ERRCODES:
            access_token = await self._get_access_token(force_refresh=True)
            body = await self._post_template_message(access_token=access_token, payload=payload)
            errcode = int(body.get("errcode") or 0)
        errmsg = str(body.get("errmsg") or "")
        if errcode:
            raise AppException(f"微信服务号模板消息发送失败：{errmsg or errcode}", status_code=502)
        return WechatOfficialTemplateSendResult(
            errcode=errcode,
            errmsg=errmsg or "ok",
            msgid=body.get("msgid"),
            raw=body,
        )

    async def _post_template_message(self, *, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        params = {"access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_official_request_timeout_seconds) as client:
                resp = await client.post(self._settings.wechat_official_template_send_url, params=params, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信服务号模板消息接口调用失败：{exc}", status_code=502) from exc
        return resp.json()

    async def oauth2_access_token(self, *, code: str) -> WechatOfficialOAuthTokenResult:
        appid, secret = self._require_config()
        clean_code = (code or "").strip()
        if not clean_code:
            raise AppException("微信服务号授权 code 为空", status_code=400)

        params = {
            "appid": appid,
            "secret": secret,
            "code": clean_code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_official_request_timeout_seconds) as client:
                resp = await client.get(self._settings.wechat_official_oauth_token_url, params=params)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信服务号网页授权接口调用失败：{exc}", status_code=502) from exc

        try:
            body = resp.json()
        except ValueError as exc:
            raise AppException("微信服务号网页授权返回非 JSON 数据", status_code=502) from exc
        if body.get("errcode"):
            raise AppException(
                f"微信服务号网页授权失败：{body.get('errmsg') or body.get('errcode')}",
                status_code=502,
            )
        openid = str(body.get("openid") or "").strip()
        access_token = str(body.get("access_token") or "").strip()
        if not openid or not access_token:
            raise AppException("微信服务号网页授权返回缺少 openid", status_code=502)
        try:
            expires_in = int(body["expires_in"]) if body.get("expires_in") is not None else None
        except (TypeError, ValueError) as exc:
            raise AppException("微信服务号网页授权返回 expires_in 格式错误", status_code=502) from exc
        return WechatOfficialOAuthTokenResult(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=body.get("refresh_token"),
            openid=openid,
            scope=body.get("scope"),
            unionid=body.get("unionid"),
            raw=body,
        )

    async def get_subscribe_status(self, *, openid: str) -> WechatOfficialSubscribeStatus:
        clean_openid = (openid or "").strip()
        if not clean_openid:
            raise AppException("微信服务号 openid 为空", status_code=400)
        cache_key = f"wechat:official:subscribe_status:{clean_openid}"
        redis = get_redis()
        cached = await redis.get(cache_key)
        if cached in {"0", "1"}:
            return WechatOfficialSubscribeStatus(
                openid=clean_openid,
                subscribed=cached == "1",
                raw={"cached": True},
            )

        access_token = await self._get_access_token()
        params = {
            "access_token": access_token,
            "openid": clean_openid,
            "lang": "zh_CN",
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_official_request_timeout_seconds) as client:
                resp = await client.get(self._settings.wechat_official_user_info_url, params=params)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信服务号用户关注状态查询失败：{exc}", status_code=502) from exc

        try:
            body = resp.json()
        except ValueError as exc:
            raise AppException("微信服务号用户信息接口返回非 JSON 数据", status_code=502) from exc
        if body.get("errcode"):
            raise AppException(
                f"微信服务号用户关注状态查询失败：{body.get('errmsg') or body.get('errcode')}",
                status_code=502,
            )
        subscribed = int(body.get("subscribe") or 0) == 1
        await redis.set(cache_key, "1" if subscribed else "0", ex=300)
        return WechatOfficialSubscribeStatus(
            openid=clean_openid,
            subscribed=subscribed,
            raw=body,
        )

    async def _get_access_token(self, *, force_refresh: bool = False) -> str:
        appid, secret = self._require_config()
        cache_key = f"wechat:official:access_token:{appid}"
        redis = get_redis()
        cached = None if force_refresh else await redis.get(cache_key)
        if cached:
            return str(cached)

        payload = {
            "grant_type": "client_credential",
            "appid": appid,
            "secret": secret,
            "force_refresh": force_refresh,
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.wechat_official_request_timeout_seconds) as client:
                resp = await client.post(self._settings.wechat_official_stable_token_url, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(f"微信服务号 access_token 获取失败：{exc}", status_code=502) from exc

        body = resp.json()
        if body.get("errcode"):
            raise AppException(
                f"微信服务号 access_token 获取失败：{body.get('errmsg') or body.get('errcode')}",
                status_code=502,
            )
        token = str(body.get("access_token") or "").strip()
        if not token:
            raise AppException("微信服务号 access_token 为空", status_code=502)
        expires_in = int(body.get("expires_in") or 7200)
        await redis.set(cache_key, token, ex=max(60, expires_in - 300))
        return token


client = WechatOfficialClient()
