"""Authenticated, fail-closed ERP API facade for model tools."""

from __future__ import annotations

from typing import Any, Literal
import json
import logging
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.db.ids import uuid7

from app.framework.harness_http import DEFAULT_REQUEST_BYTES, permitted, ProjectionError
from .harness_api_policy import allowed_read, allowed_write, automatic_position_memory_write, inherited_operation, project_read, route_availability, route_catalog
from .harness_http_catalog import operation_document
from .harness_write_approval import issue_grant, consume_grant, request_hash
from .harness_value_policy import model_scalar

router = APIRouter(prefix="/api/harness", tags=["harness-api"])
logger = logging.getLogger(__name__)


def _log_failure(request, user, method, path, stage, reason, status, operation=None):
    # 只记录路由模板与授权元数据，不复制正文、查询参数、令牌或异常原文。
    from app.framework.harness_http import RouteSnapshot

    route_path = next((route.path for route in RouteSnapshot.capture(request.app.routes).routes
                       if method in (route.methods or ()) and route.path_regex.fullmatch(path)), "<unregistered>")
    request_id = getattr(request.state, "audit_request_id", None) or uuid7()
    request.state.audit_request_id = request_id
    groups = operation.permissions if operation is not None else ()
    logger.warning("Harness API failure %s", json.dumps({
        "request_id": str(request_id), "tenant_id": str(user.tenant_id), "user_id": str(user.user_id),
        "org_id": str(user.org_id) if user.org_id else None,
        "entry": request.url.path, "method": method, "route": route_path,
        "stage": stage, "reason": reason, "status": status,
        "required_permissions": groups,
        "missing_permissions": sorted({name for _, names in groups for name in names if name not in user.permissions}),
    }, ensure_ascii=False))


class ApiCall(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1, max_length=2048)
    body: Any = None
    write_approval: str | None = Field(default=None, max_length=4096)


def _write_contract(operation, method, path, routes):
    if operation is not None:
        return operation_document(operation)["contract_hash"]
    # Plugin-declared writers are also bound to current enable/deny policy.
    from .harness_api_policy import HTTP_POLICY_PATH
    return request_hash(method, path, HTTP_POLICY_PATH.read_text(encoding="utf-8"), "legacy")


def _has_redacted_input(value):
    if isinstance(value, dict):
        return any(_has_redacted_input(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_redacted_input(item) for item in value)
    return isinstance(value, str) and any(marker in value for marker in ("[已隐藏]", "[REDACTED]"))


def _check_write_permission(operation, method, path, user):
    from .harness_api_policy import WRITE_ROUTES
    groups = operation.permissions if operation is not None else (("any", WRITE_ROUTES[(method, path)]),)
    if not permitted(groups, user):
        raise HTTPException(403, "当前账号无此操作权限")


async def _check_request_size(request, operation):
    # 签发确认和执行使用同一服务端容量，避免正文可保存却拿不到写授权。
    limit = operation.max_request_bytes if operation is not None else DEFAULT_REQUEST_BYTES
    if len(await request.body()) > limit:
        raise HTTPException(413, f"ERP 接口请求超过容量限制（最多 {limit:,} 字节），请减少提交内容")


def _unavailable_response(reason):
    # 只发布固定的诊断编码，不透传上游异常、凭据或业务信息。
    return JSONResponse(status_code=404, content=success_response({
        "status": 404, "ok": False, "error_code": reason,
    }), headers={"Cache-Control": "no-store"})


@router.post("/write-approval", include_in_schema=False)
async def approve_erp_write(payload: ApiCall, request: Request,
                            current_user: AuthenticatedUser = Depends(get_current_user)):
    """Called by the trusted client only after a human confirms the exact write."""
    path, target = _target(payload.path)
    availability = route_availability(payload.method, path, current_user, request.app.routes)
    if availability != "ready":
        _log_failure(request, current_user, payload.method, path, "route", availability, 404)
        return _unavailable_response(availability)
    operation = inherited_operation(payload.method, path, request.app.routes)
    if allowed_read(payload.method, path, payload.body, request.app.routes) or not allowed_write(payload.method, path, request.app.routes):
        _log_failure(request, current_user, payload.method, path, "policy", "write_not_open", 403, operation)
        raise HTTPException(403, "此操作不能签发写授权")
    try:
        _check_write_permission(operation, payload.method, path, current_user)
    except HTTPException as exc:
        _log_failure(request, current_user, payload.method, path, "permission", "write_permission_denied", exc.status_code, operation)
        raise
    await _check_request_size(request, operation)
    if _has_redacted_input(payload.body):
        raise HTTPException(400, "写入参数无效，脱敏占位符不能写回业务数据")
    contract = _write_contract(operation, payload.method, path, request.app.routes)
    return JSONResponse(content=success_response({"write_approval": issue_grant(current_user, payload.method, target, payload.body, contract)}),
                        headers={"Cache-Control": "no-store"})


def _target(path: str) -> tuple[str, str]:
    parsed = urlsplit(path)
    if (
        parsed.scheme or parsed.netloc or parsed.fragment or not path.startswith("/api/")
        or "\\" in path or "%" in parsed.path or "//" in parsed.path
        or any(part in (".", "..") for part in parsed.path.split("/"))
        or parsed.path.startswith("/api/harness/")
    ):
        raise HTTPException(status_code=400, detail="Invalid ERP API path")
    return parsed.path, path


@router.post("/api", include_in_schema=False)
async def call_erp_api(
    payload: ApiCall,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JSONResponse:
    if (request.headers.get("x-harness-read-only") == "1" or request.headers.get("x-harness-server-assistant") == "1") and payload.path == "/api/harness/catalog":
        raise HTTPException(status_code=400, detail="请按问题检索资源并 describe，不支持向网页智能体返回全量接口目录")
    if payload.method == "GET" and payload.path == "/api/harness/catalog" and payload.body is None:
        return JSONResponse(content=success_response({"status": 200, "ok": True, "data": route_catalog(current_user, request.app.routes)}),
                            headers={"Cache-Control": "no-store"})
    path, target = _target(payload.path)
    availability = route_availability(payload.method, path, current_user, request.app.routes)
    if availability != "ready":
        _log_failure(request, current_user, payload.method, path, "route", availability, 404)
        return _unavailable_response(availability)
    operation = inherited_operation(payload.method, path, request.app.routes)
    is_read = allowed_read(payload.method, path, payload.body, request.app.routes)
    if request.headers.get("x-harness-read-only") == "1" and not is_read:
        _log_failure(request, current_user, payload.method, path, "policy", "read_only_client", 403, operation)
        raise HTTPException(status_code=403, detail="网页和小程序智能体当前仅支持读取 ERP 数据，请在业务页面执行修改")
    if not is_read and not allowed_write(payload.method, path, request.app.routes):
        _log_failure(request, current_user, payload.method, path, "policy", "write_not_open_or_catalog_stale", 403, operation)
        raise HTTPException(status_code=403, detail="接口未开放或静态目录已过期，请重新生成接口目录")
    if operation is not None and not permitted(operation.permissions, current_user):
        _log_failure(request, current_user, payload.method, path, "permission", "operation_permission_denied", 403, operation)
        raise HTTPException(status_code=403, detail="ERP API permission denied")
    if payload.method == "GET" and payload.body is not None:
        raise HTTPException(status_code=400, detail="GET body is not supported")
    await _check_request_size(request, operation)
    if not is_read:
        try:
            _check_write_permission(operation, payload.method, path, current_user)
        except HTTPException as exc:
            _log_failure(request, current_user, payload.method, path, "permission", "write_permission_denied", exc.status_code, operation)
            raise
        if _has_redacted_input(payload.body):
            raise HTTPException(400, "脱敏占位符不能写回业务数据，请在 ERP 页面填写真实信息")
        if payload.write_approval is None and not automatic_position_memory_write(payload.method, path):
            # The model never chooses a boolean to bypass this. The trusted
            # client asks the human, then requests a bound server-issued grant.
            return JSONResponse(status_code=409, content=success_response({
                "status": 409, "ok": False, "approval_required": True,
                "approval_preview": {"method": payload.method, "path": path,
                                     "title": model_scalar(operation.route.summary or operation.route.name) if operation else "ERP 业务写入",
                                     "message": "此操作会修改 ERP 数据，请确认待执行操作和参数。"},
            }), headers={"Cache-Control": "no-store"})
        if not automatic_position_memory_write(payload.method, path):
            try:
                await consume_grant(payload.write_approval, current_user, payload.method, target, payload.body,
                                    _write_contract(operation, payload.method, path, request.app.routes))
            except HTTPException as exc:
                _log_failure(request, current_user, payload.method, path, "approval", "write_approval_invalid", exc.status_code, operation)
                raise

    # Dispatch through the actual ERP route with the caller's bearer. This keeps
    # permission dependencies, service rules, and scoped repository queries intact.
    headers = {"accept": "application/json"}
    if authorization := request.headers.get("authorization"):
        headers["authorization"] = authorization
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=request.app), base_url="http://erp.internal",
        follow_redirects=False, timeout=30.0,
    ) as client:
        from app.framework.harness_context import model_request_context
        with model_request_context():
            response = await client.request(
                payload.method, target, headers=headers,
                json=payload.body if payload.method != "GET" else None,
            )

    status = response.status_code
    visible: dict[str, Any] = {"status": status, "ok": 200 <= status < 300}
    if is_read and visible["ok"]:
        if len(response.content) > 2 * 1024 * 1024:
            return JSONResponse(status_code=413, content=success_response({"status": 413, "ok": False,
                "message": "接口结果过大，请分页或缩小查询范围"}))
        try:
            source = response.json()
        except ValueError:
            source = None
        if not isinstance(source, dict) or source.get("code") != 0:
            visible = {"status": 502, "ok": False}
        else:
            filtered = operation is not None and operation.response_policy == "recursive_filter"
            if filtered:
                try:
                    counts: dict[str, int] = {}
                    projected = operation.projection.apply(source.get("data"), model_scalar, counts=counts)
                except ProjectionError:
                    return JSONResponse(status_code=413, content=success_response({"status": 413, "ok": False,
                        "message": "接口结果超过容量限制，请分页或缩小查询范围"}))
            else:
                projected = project_read(payload.method, path, payload.body, source.get("data"), request.app.routes)
            valid_null = operation is not None and operation.projection is not None \
                and operation.projection.nullable and source.get("data") is None
            if projected is None and not valid_null and not filtered:
                visible = {"status": 502, "ok": False}
            else:
                visible["data"] = projected
    elif not is_read and visible["ok"]:
        # A 200 envelope can still contain a business failure. Do not report a
        # successful mutation or expose its potentially sensitive error text.
        try:
            source = response.json()
        except ValueError:
            source = None
        if not isinstance(source, dict) or source.get("code") != 0:
            visible = {"status": 502, "ok": False}
        elif automatic_position_memory_write(payload.method, path):
            visible["data"] = {key: source["data"][key] for key in (
                "document_id", "version_id", "status_code", "publish_status_code", "unchanged")}
        elif operation is not None and operation.route.path in {
            "/api/knowledge/bases/{item_id}/documents/manual",
            "/api/knowledge/bases/{item_id}/documents/upload",
        } and payload.method == "POST":
            from .knowledge.harness import project_created_document
            created = project_created_document(source.get("data"))
            if created is None:
                visible = {"status": 502, "ok": False, "error_code": "write_result_unconfirmed"}
            else:
                visible["data"] = created
    content = success_response(visible)
    if len(json.dumps(content, ensure_ascii=False).encode("utf-8")) > 45000:
        visible = {"status": 413, "ok": False, "message": "接口结果过大，请分页或缩小查询范围"}
        content = success_response(visible)
    if visible["status"] >= 400:
        _log_failure(request, current_user, payload.method, path,
                     "business" if status >= 400 else "response",
                     "business_http_error" if status >= 400 else visible.get("error_code", "response_contract_failed"),
                     visible["status"], operation)
    return JSONResponse(status_code=visible["status"], content=content,
                        headers={"Cache-Control": "no-store"})
