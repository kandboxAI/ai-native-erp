"""独立员工 MCP 进程：python -m app.modules.sample_app.employee_mcp。"""
from contextlib import asynccontextmanager
from time import time
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.auth.api import login as auth_login, refresh_token as auth_refresh, router as auth_router
from app.auth.schemas import LoginRequest, RefreshTokenRequest
from app.auth.token import revoke_refresh_token, verify_refresh_token
from app.auth.dependencies import get_current_user
from app.framework.plugin_settings import load_plugin_settings
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import enforce_fixed_window_rate_limit
from app.core.security import bearer_scheme, extract_token
from app.db.connection import startup_database, shutdown_database
from app.framework.db.session import startup_sqlmodel_database, shutdown_sqlmodel_database
from app.framework.deployment import is_module_enabled
from app.integrations.redis_client import startup_redis, shutdown_redis
from app.modules.file.api import router as file_router
from app.modules.user_profile.service import service as users
from app.modules.user_profile.schemas import UserListQuery
from . import employee_mcp_service as service, employee_mcp_protocol as protocol
from . import software_claim_service as software_claims
from .employee_mcp_auth import mcp_user, normal_employee, issue_token
from .employee_mcp_schemas import BindingBody, TicketBody, CompleteBody, RequestBody, PrepareBody, ChangePasswordBody
from .employee_mcp_portal import HTML, JAVASCRIPT, CSS
from . import employee_mcp_pairing as pairing
from . import software_claim_files as _software_claim_files  # noqa: F401  # 注册附件场景


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_prefix="SAMPLE_APP_EMPLOYEE_MCP_")
    public_url: str = "http://127.0.0.1:18990"
    host: str = "127.0.0.1"
    port: int = 18990

    @field_validator("public_url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value)
        if (parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in {"", "/"}):
            raise ValueError("员工 MCP public_url 必须是无路径、无凭据的访问源地址")
        if parts.scheme != "https" and parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("远程员工 MCP 必须使用 HTTPS")
        return value.rstrip("/")


config = load_plugin_settings("sample_app", McpSettings)


@asynccontextmanager
async def lifespan(_app):
    if not is_module_enabled("sample_app"):
        raise RuntimeError("当前部署未加载快盒插件")
    try:
        await startup_database()
        await startup_sqlmodel_database()
        await startup_redis()
        yield
    finally:
        await shutdown_redis()
        await shutdown_sqlmodel_database()
        await shutdown_database()


app = FastAPI(title="快盒员工端 MCP", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(file_router)


@app.middleware("http")
async def secure_surface(request, call_next):
    # 不接受其他网站发起的浏览器请求；非浏览器 MCP 客户端可不带 Origin。
    if request.headers.get("origin") not in {None, config.public_url}:
        return JSONResponse({"message": "来源不允许"}, status_code=403)
    if request.headers.get("host") != urlsplit(config.public_url).netloc:
        return JSONResponse({"message": "访问域名与配置不一致"}, status_code=403)
    body = bytearray()
    # JSON 请求限制为 128KB；本地开发文件直传由公共文件接口按场景验证大小。
    if request.headers.get("content-type", "").startswith("application/json"):
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 128 * 1024:
                return Response(status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https:; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get("/", response_class=HTMLResponse)
async def portal():
    return HTML


@app.get("/portal.js")
async def portal_script():
    return Response(JAVASCRIPT, media_type="application/javascript")


@app.get("/portal.css")
async def portal_styles():
    return Response(CSS, media_type="text/css")


SESSION_COOKIE = "kuaihe_employee_session"
SESSION_PATH = "/employee/session"


def browser_session(response, session):
    response.set_cookie(SESSION_COOKIE, session["refresh_token"], path=SESSION_PATH,
                        httponly=True, secure=urlsplit(config.public_url).scheme == "https", samesite="strict",
                        max_age=max(0, int(session["session_expires_at"] - time())))
    return {key: value for key, value in session.items() if key != "refresh_token"}


@app.post(SESSION_PATH + "/login")
async def employee_login(body: LoginRequest, request: Request, response: Response):
    result = await auth_login(body, request)
    result["data"]["session"] = browser_session(response, result["data"]["session"])
    return result


@app.post(SESSION_PATH + "/refresh")
async def employee_refresh(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "请先登录员工服务")
    result = await auth_refresh(RefreshTokenRequest(refresh_token=token), request)
    result["data"] = browser_session(response, result["data"])
    return result


@app.post(SESSION_PATH + "/logout")
async def employee_logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            session = await verify_refresh_token(token)
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
        else:
            await revoke_refresh_token(token, session.user_id)
    response.delete_cookie(SESSION_COOKIE, path=SESSION_PATH, httponly=True,
                           secure=urlsplit(config.public_url).scheme == "https", samesite="strict")
    return {"logged_out": True}


@app.post(SESSION_PATH + "/change-password")
async def employee_change_password(body: ChangePasswordBody, request: Request, response: Response,
                                   user=Depends(normal_employee)):
    result = await service.change_password(user, body)
    response.delete_cookie(SESSION_COOKIE, path=SESSION_PATH, httponly=True,
                           secure=urlsplit(config.public_url).scheme == "https", samesite="strict")
    return result


@app.get("/employee/connection")
async def connection_info():
    """公开连接元数据，不包含凭证或任何员工数据。"""
    return {"name": "快盒员工报销", "transport": "Streamable HTTP",
            "mcp_url": config.public_url + "/mcp/sample-app/employee",
            "auth_type": "Bearer", "header_name": "Authorization"}


@app.post("/employee/token")
async def token(user=Depends(normal_employee), credentials=Depends(bearer_scheme)):
    # 凭证签发前要求可信本人绑定，而非让管理员账号直接代替员工。
    from app.framework.db.session import get_session_context
    async with get_session_context() as session:
        await service.identity(session, user)
    return {**issue_token(user, extract_token(credentials)), "mcp_url": config.public_url + "/mcp/sample-app/employee"}


@app.get("/employee/requests/{request_id}")
async def detail(request_id: UUID, user=Depends(normal_employee)):
    return await service.detail(user, request_id)


@app.get("/employee/requests")
async def recent_requests(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                          user=Depends(normal_employee)):
    return await service.recent_requests(user, page=page, page_size=page_size)


@app.get("/employee/reimbursements/{reimbursement_id}")
async def reimbursement_detail(reimbursement_id: UUID, user=Depends(normal_employee)):
    return await service.reimbursement_detail(user, reimbursement_id)


@app.post("/employee/prepare")
async def prepare_request(body: PrepareBody, user=Depends(normal_employee)):
    return await service.prepare(user, body, source="manual")


@app.post("/employee/revise")
async def revise_request(body: RequestBody, user=Depends(normal_employee)):
    return await service.revise_manual(user, body.request_id)


@app.post("/employee/submit")
async def submit_request(body: RequestBody, user=Depends(normal_employee)):
    return await service.submit(user, body.request_id)


@app.post("/employee/upload-tickets")
async def tickets(body: TicketBody, user=Depends(normal_employee)):
    return {"tickets": await service.upload_tickets(user, body.request_id, body.files)}


@app.post("/employee/complete-upload")
async def complete(body: CompleteBody, user=Depends(normal_employee)):
    return await service.complete_upload(user, body.request_id, body.file_id)


@app.post("/employee/approve")
async def approve(body: RequestBody, user=Depends(normal_employee)):
    return await service.approve(user, body.request_id)


@app.get("/employee/software-claims")
async def software_claim_list(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                              user=Depends(normal_employee)):
    return await software_claims.recent_claims(user, page=page, page_size=page_size)


@app.get("/employee/software-claims/{claim_id}")
async def software_claim_detail(claim_id: UUID, user=Depends(normal_employee)):
    return await software_claims.detail(user, claim_id)


@app.post("/employee/software-claims/approve")
async def software_claim_approve(body: RequestBody, user=Depends(normal_employee)):
    return await software_claims.approve(user, body.request_id)


@app.get("/admin/binding-options")
async def binding_options(user=Depends(get_current_user)):
    if ("sample_app" not in user.enabled_plugin_keys or "sample_app:access" not in user.permissions
            or "user_profile:list" not in user.permissions or "user_profile:detail" not in user.permissions):
        raise HTTPException(403, "无权维护员工账号绑定")
    from .scoped_service import BusinessScope, employees
    result = await users.list(UserListQuery(page=1, page_size=100, is_active=True), user)
    people = await employees(BusinessScope(user), "internal")
    return {"users": [{"id": row["id"], "name": row["full_name"] or row["display_name"]} for row in result["items"]],
            "employees": [{"id": row["id"], "name": row["full_name"], "org_name": row.get("org_name", "")} for row in people]}


class PairingCode(BaseModel):
    browser_code: str = Field(min_length=20, max_length=100)


class DeviceCode(BaseModel):
    device_code: str = Field(min_length=20, max_length=100)


async def pairing_rate(request):
    await enforce_fixed_window_rate_limit(namespace="sample_app_mcp_pair", key_parts=[request.client.host if request.client else "unknown"],
                                          limit=30, window_seconds=60)


@app.post("/pair/start")
async def pair_start(request: Request):
    await pairing_rate(request)
    result = await pairing.start()
    return {**result, "verification_url": config.public_url + "/?browser_code=" + result["browser_code"]}


@app.post("/pair/poll")
async def pair_poll(body: DeviceCode, request: Request):
    await pairing_rate(request)
    return await pairing.poll(body.device_code)


@app.post("/employee/pair")
async def pair_approve(body: PairingCode, user=Depends(normal_employee), credentials=Depends(bearer_scheme)):
    from app.framework.db.session import get_session_context
    async with get_session_context() as session:
        await service.identity(session, user)
    await pairing.approve(body.browser_code, issue_token(user, extract_token(credentials)))
    return {"authorized": True}


@app.post("/admin/binding")
async def binding(body: BindingBody, user=Depends(get_current_user)):
    if "sample_app" not in user.enabled_plugin_keys:
        raise HTTPException(403, "快盒未开通")
    return await service.bind_account(user, body.user_id, body.employee_id, body.previous_user_id)


@app.get("/mcp/sample-app/employee")
async def no_sse(_user=Depends(mcp_user)):
    # 规范允许不提供独立 SSE，明确返回 405，POST 以 JSON 返回结果。
    return Response(status_code=405, headers={"Allow": "POST"})


@app.post("/mcp/sample-app/employee")
async def mcp(request: Request, user=Depends(mcp_user)):
    await enforce_fixed_window_rate_limit(namespace="sample_app_employee_mcp", key_parts=[str(user.tenant_id), str(user.user_id)],
                                          limit=120, window_seconds=60)
    if not request.headers.get("content-type", "").startswith("application/json"):
        return Response(status_code=415)
    accept = request.headers.get("accept", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        return Response(status_code=406)
    version = request.headers.get("mcp-protocol-version")
    if version and version != protocol.VERSION:
        return JSONResponse(protocol.error(None, -32600, "不支持的协议版本"), status_code=400)
    try:
        message = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(protocol.error(None, -32700, "JSON 解析失败"), status_code=400)
    if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str) or isinstance(message.get("id"), bool)
            or ("id" in message and not isinstance(message["id"], (str, int)))):
        return JSONResponse(protocol.error(None, -32600, "无效 JSON-RPC 请求"), status_code=400)
    if "id" not in message:
        if message["method"] not in {"notifications/initialized", "notifications/cancelled"}:
            return Response(status_code=400)
        return Response(status_code=202)
    return JSONResponse(await protocol.dispatch(message, user, config.public_url))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.modules.sample_app.employee_mcp:app", host=config.host, port=config.port, access_log=False)
