from __future__ import annotations

from typing import Awaitable, Callable
from uuid import UUID
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.framework.db.ids import uuid7
from app.modules.operation_log.service import service as operation_logs
from app.modules.operation_log.policy import find_sensitive_rule, audit_metadata
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PREFIXES = (
    "/api/auth",
    "/api/login_log",
    "/api/operation_log",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return ""


def _module_name(path: str) -> str:
    parts = [item for item in path.split("/") if item]
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1][:64]
    return "system"


ACTION_BY_METHOD = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}


def _action_code(method: str) -> str:
    """操作类型（字典 audit_action）。"""
    return ACTION_BY_METHOD.get(method.upper(), "update")


def _target_id(path: str) -> UUID | None:
    tail = path.rstrip("/").rsplit("/", 1)[-1]
    try:
        return UUID(tail)
    except ValueError:
        return None


async def _prepare_sensitive_audit(request):
    rule = find_sensitive_rule(request.method, request.url.path)
    if rule is None:
        return
    body = {}
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and "application/json" in request.headers.get("content-type", ""):
        try:
            parsed = await request.json()
            body = parsed if isinstance(parsed, dict) else {}
        except (ValueError, UnicodeError):
            pass
    metadata = audit_metadata(rule, request.method, request.url.path, request.query_params, body)
    if metadata is not None:
        request.state.sensitive_audit = metadata
        request.state.audit_request_id = uuid7()


def _should_skip(request: Request) -> bool:
    if any(request.url.path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    return not getattr(request.state, "sensitive_audit", None) and request.method.upper() not in WRITE_METHODS


async def _write_operation_log(request: Request, response: Response) -> bool:
    current_user = getattr(request.state, "current_user", None)
    if current_user is None:
        return True
    sensitive = getattr(request.state, "sensitive_audit", None)
    request_id = getattr(request.state, "audit_request_id", None) or uuid7()
    path = sensitive["request_path"] if sensitive else getattr(request.scope.get("route"), "path", request.url.path)
    # 不保存查询字符串、请求体、异常原文或响应正文，避免把敏感数据复制到日志。
    content = f"{request.method.upper()} {path} -> {response.status_code}"
    values = {
        "module_code": sensitive["module_code"] if sensitive else _module_name(path),
        "action_code": sensitive["action_code"] if sensitive else _action_code(request.method),
        "target_type_code": sensitive["target_type_code"] if sensitive else _module_name(path),
        "target_id": sensitive["target_id"] if sensitive else _target_id(request.url.path),
        "content": content[:2000], "ip_address": _client_ip(request),
        "is_sensitive": sensitive is not None, "request_id": request_id,
        "request_method": request.method.upper(), "request_path": path[:512],
        "http_status": response.status_code,
    }
    try:
        if current_user.org_id is None:
            raise ValueError("missing audit organization")
        await operation_logs.record(current_user, **values)
        return True
    except Exception:
        # 不打印驱动异常：其中可能携带连接凭据、SQL 或业务值。
        logger.error("Operation audit persistence failed; request_id=%s", request_id)
        return False


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        await _prepare_sensitive_audit(request)
        try:
            response = await call_next(request)
        except Exception:
            if not _should_skip(request):
                await _write_operation_log(request, Response(status_code=500))
            raise
        if not _should_skip(request):
            recorded = await _write_operation_log(request, response)
            sensitive = getattr(request.state, "sensitive_audit", None)
            if not recorded and sensitive and sensitive["action_code"] in {"read", "export"} and response.status_code < 400:
                return JSONResponse({"code": 503, "message": "审计服务暂不可用，请稍后重试", "data": None}, status_code=503)
        return response
