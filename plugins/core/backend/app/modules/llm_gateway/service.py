"""Authenticate desktop model calls and relay DeepSeek Messages without exposing its key."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.auth.schemas import AuthenticatedUser
from app.auth.service import build_authenticated_user
from app.core.config import get_settings
from app.core.runtime import online_user_registry
from app.modules.llm_gateway import repository
from app.modules.llm_gateway.models import GatewayCredentialResponse, GatewayIdentity, GatewaySearchRequest
from app.modules.llm_gateway.privacy import redact_public_source

logger = logging.getLogger(__name__)


def _settings_and_key():
    settings = get_settings()
    key = (settings.llm_gateway_deepseek_api_key or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="智能体服务尚未配置，请联系管理员")
    return settings, key


async def issue_credential(user: AuthenticatedUser, client_id: UUID) -> GatewayCredentialResponse:
    settings, _key = _settings_and_key()
    identity = GatewayIdentity(auth_user_id=user.auth_user_id, tenant_id=user.tenant_id, user_id=user.user_id,
                               client_id=client_id, email=str(user.email) if user.email else None)
    token = await repository.issue_credential(identity, settings.llm_gateway_credential_ttl_seconds)
    return GatewayCredentialResponse(access_token=token, expires_in=settings.llm_gateway_credential_ttl_seconds)


async def authenticate_credential(token: str | None, client_id: str | None) -> GatewayIdentity:
    if not token or not client_id or len(token) > 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="智能体访问凭证无效或已过期，请重新连接 ERP")
    identity = await repository.read_credential(token)
    if identity is None or str(identity.client_id) != client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="智能体访问凭证无效或已过期，请重新连接 ERP")
    if await online_user_registry.is_session_revoked(identity.auth_user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ERP 登录已失效，请重新登录")
    await build_authenticated_user({"sub": str(identity.auth_user_id), "tenant_id": str(identity.tenant_id),
                                    "email": identity.email})
    return identity


async def search_web(identity: GatewayIdentity, body: bytes):
    """公开关键词的搜索出口：只转发 query/count/need_content，复用凭据、配额和用量记录。"""
    settings, key = _settings_and_key()
    if len(body) > settings.llm_gateway_max_request_bytes:
        raise HTTPException(413, "搜索请求内容过大")
    try:
        request = GatewaySearchRequest.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(400, "搜索参数无效：仅支持 1～128 字符的 query 和 1～5 条结果") from error
    query = request.query.strip()
    if not query:
        raise HTTPException(400, "请输入公开搜索关键词")
    if not await repository.consume_request_quota(identity.auth_user_id, settings.llm_gateway_requests_per_minute,
                                                  settings.llm_gateway_requests_per_day):
        raise HTTPException(429, "智能体调用次数已达上限，请稍后再试")
    root = settings.llm_gateway_search_base_url.rstrip("/")
    url = root + ("/tools/search" if root.endswith("/v1") else "/v1/tools/search")
    request_id, upstream_status = str(uuid4()), 502
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
            upstream = await client.post(url, headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "count": request.count, "need_content": True})
        upstream_status = upstream.status_code
        if upstream_status != 200:
            # 不回显供应商原始错误，避免其中包含诊断信息或请求内容。
            message = "联网搜索服务拒绝了请求，请稍后重试或联系管理员"
            if upstream_status == 402:
                message = "联网搜索服务余额不足，请联系管理员"
            raise HTTPException(upstream_status if upstream_status < 500 else 502, message)
        try:
            payload = upstream.json()
        except ValueError as error:
            raise HTTPException(502, "联网搜索服务返回格式异常") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise HTTPException(502, "联网搜索服务返回格式异常")
        sources = []
        for item in payload["results"][:request.count]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            # 保留有出处的摘要与正文摘录，限制模型上下文，不传供应商其他字段。
            summary = item.get("summary") or item.get("snippet") or ""
            content = item.get("content") or ""
            summary = summary if isinstance(summary, str) else ""
            content = content if isinstance(content, str) else ""
            excerpt = "\n".join(part for part in (summary[:1000], content[:3000]) if part)
            source = {"url": item["url"][:8192], "snippet": excerpt}
            if isinstance(item.get("title"), str):
                source["title"] = item["title"][:500]
            if isinstance(item.get("date"), str):
                source["publishedAt"] = item["date"][:64]
            safe_source, _ = redact_public_source(source)
            if safe_source is not None:
                sources.append(safe_source)
        result = {"sources": sources, "truncated": False}
        return JSONResponse(result, headers={"x-llm-request-id": request_id, "cache-control": "no-store"})
    except httpx.HTTPError as error:
        raise HTTPException(502, "联网搜索服务暂时不可用，请稍后重试") from error
    finally:
        try:
            await repository.record_usage(identity.auth_user_id, request_id, "web-search", {}, upstream_status)
        except Exception:
            logger.error("Failed to record web search usage: request_id=%s", request_id)


def _usage_from_event(raw: bytes, totals: dict[str, int]) -> None:
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return
    if not isinstance(event, dict) or not isinstance(event.get("usage"), dict):
        return
    for key in ("input_tokens", "output_tokens"):
        value = event["usage"].get(key)
        if isinstance(value, int) and value >= 0:
            totals[key] = max(totals.get(key, 0), value)


def _contains_file_reference(value: object) -> bool:
    if isinstance(value, dict):
        if "file_id" in value or (value.get("type") == "file" and "source" in value):
            return True
        return any(_contains_file_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_file_reference(item) for item in value)
    return False


async def relay_messages(identity: GatewayIdentity, body: bytes, anthropic_version: str | None,
                         anthropic_beta: str | None):
    settings, upstream_key = _settings_and_key()
    if len(body) > settings.llm_gateway_max_request_bytes:
        raise HTTPException(status_code=413, detail="模型请求内容过大，请减少上下文或附件后重试")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="模型请求不是有效的 JSON 格式") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="模型请求必须为 JSON 对象")
    model = payload.get("model")
    if not isinstance(model, str) or model not in settings.llm_gateway_allowed_models:
        raise HTTPException(status_code=403, detail="当前模型未启用，请联系管理员")
    max_tokens = payload.get("max_tokens")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1 \
            or max_tokens > settings.llm_gateway_max_output_tokens:
        raise HTTPException(status_code=400, detail="模型输出长度参数无效或超过服务端上限")
    if not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=400, detail="模型请求格式错误：消息列表必须为数组")
    if not isinstance(payload.get("stream", False), bool):
        raise HTTPException(status_code=400, detail="模型请求格式错误：流式输出参数必须为布尔值")
    # The upstream account is shared. File IDs from another request or user must never be accepted.
    if _contains_file_reference(payload):
        raise HTTPException(status_code=400, detail="暂未开放文件引用功能")
    if not await repository.consume_request_quota(identity.auth_user_id, settings.llm_gateway_requests_per_minute,
                                                  settings.llm_gateway_requests_per_day):
        raise HTTPException(status_code=429, detail="智能体调用次数已达上限，请稍后再试")

    request_id = str(uuid4())
    response_headers = {"x-llm-request-id": request_id}
    root = settings.llm_gateway_upstream_base_url.rstrip("/")
    upstream_url = root + ("/messages" if root.endswith("/v1") else "/v1/messages")
    headers = {
        "x-api-key": upstream_key,
        "content-type": "application/json",
        "anthropic-version": anthropic_version or "2023-06-01",
    }
    if anthropic_beta:
        headers["anthropic-beta"] = anthropic_beta[:256]
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=180, write=30, pool=10), follow_redirects=False)
    try:
        upstream_request = client.build_request("POST", upstream_url, content=body, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("LLM gateway upstream unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="模型服务暂时不可用，请稍后重试") from exc
    if upstream.status_code >= 300:
        await upstream.aclose()
        await client.aclose()
        try:
            await repository.record_usage(identity.auth_user_id, request_id, model, {}, upstream.status_code)
        except Exception:
            logger.exception("Failed to record LLM gateway usage")
        return JSONResponse(status_code=upstream.status_code if upstream.status_code < 500 else 502,
                            content={"type": "error", "error": {"type": "api_error", "message": "模型服务拒绝了请求，请稍后重试或联系管理员"}},
                            headers=response_headers)

    if not payload.get("stream"):
        try:
            content = await upstream.aread()
            parsed = json.loads(content)
            usage = parsed.get("usage", {}) if isinstance(parsed, dict) else {}
            safe_usage = {key: value for key, value in usage.items() if key in {"input_tokens", "output_tokens"}
                          and isinstance(value, int) and value >= 0} if isinstance(usage, dict) else {}
            try:
                await repository.record_usage(identity.auth_user_id, request_id, model, safe_usage, upstream.status_code)
            except Exception:
                logger.exception("Failed to record LLM gateway usage")
            return JSONResponse(status_code=upstream.status_code, content=parsed,
                                headers=response_headers)
        finally:
            await upstream.aclose()
            await client.aclose()

    async def chunks() -> AsyncIterator[bytes]:
        totals: dict[str, int] = {}
        pending = b""
        try:
            async for chunk in upstream.aiter_bytes():
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if line.startswith(b"data:"):
                        _usage_from_event(line[5:].strip(), totals)
                if len(pending) > 65536:
                    pending = b""
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            try:
                await repository.record_usage(identity.auth_user_id, request_id, model, totals, upstream.status_code)
            except Exception:
                logger.exception("Failed to record LLM gateway usage")

    return StreamingResponse(chunks(), media_type="text/event-stream",
                             headers={**response_headers, "cache-control": "no-store"})
