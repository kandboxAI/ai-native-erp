from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    AuthenticatedUser,
    LoginRequest,
    RefreshTokenRequest,
    WechatMiniappLoginRequest,
)
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_fixed_window_rate_limit
from app.core.response import success_response
from app.core.runtime import online_user_registry
from app.modules.login_log.repository import append_login_attempt

from .service import (
    create_login_captcha,
    login_with_password,
    refresh_access_token,
    verify_login_captcha,
)
from .qr_login_models import EmployeeQrLoginBrowserRequest, EmployeeQrLoginWechatRequest
from .qr_login_service import service as employee_qr_login_service
from .wechat_login_service import login_with_wechat_miniapp
from app.modules.menu.service import service as menu_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return ""


@router.get("/captcha")
async def login_captcha(request: Request) -> dict:
    settings = get_settings()
    await enforce_fixed_window_rate_limit(
        namespace="auth_captcha_ip",
        key_parts=[_client_ip(request) or "unknown"],
        limit=settings.auth_captcha_rate_limit_per_minute,
        window_seconds=60,
    )
    result = await create_login_captcha()
    return success_response(result.model_dump(mode="json"))


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict:
    settings = get_settings()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    login_name = payload.login_name.strip().lower()
    await enforce_fixed_window_rate_limit(
        namespace="auth_login_ip",
        key_parts=[ip or "unknown"],
        limit=settings.auth_login_rate_limit_per_minute,
        window_seconds=60,
    )
    await enforce_fixed_window_rate_limit(
        namespace="auth_login_account",
        key_parts=[login_name, ip or "unknown"],
        limit=settings.auth_login_account_rate_limit_per_15_minutes,
        window_seconds=15 * 60,
    )
    try:
        await verify_login_captcha(payload.captcha_id, payload.captcha_code)
        result = await login_with_password(login_name, payload.password, payload.portal, payload.tenant_id,
                                           remember_me=payload.remember_me, remember_days=payload.remember_days)
        await online_user_registry.clear_session_revocation(result.user.auth_user_id)
        await append_login_attempt(
            login_name=login_name,
            ip_address=ip,
            success=True,
            auth_user_id=result.user.auth_user_id,
            user_agent=ua,
            message=None,
        )
        return success_response(result.model_dump(mode="json"))
    except AppException as exc:
        await append_login_attempt(
            login_name=login_name,
            ip_address=ip,
            success=False,
            auth_user_id=None,
            user_agent=ua,
            message=(exc.message[:2000] if exc.message else None),
        )
        raise
    except Exception as exc:
        await append_login_attempt(
            login_name=login_name,
            ip_address=ip,
            success=False,
            auth_user_id=None,
            user_agent=ua,
            message=str(exc)[:500],
        )
        raise


@router.post("/wechat-miniapp/login")
async def wechat_miniapp_login(payload: WechatMiniappLoginRequest, request: Request) -> dict:
    settings = get_settings()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    await enforce_fixed_window_rate_limit(
        namespace="auth_wechat_miniapp_login_ip",
        key_parts=[ip or "unknown"],
        limit=settings.auth_login_rate_limit_per_minute,
        window_seconds=60,
    )
    try:
        result = await login_with_wechat_miniapp(payload)
        await online_user_registry.clear_session_revocation(result.user.auth_user_id)
        await append_login_attempt(
            login_name="wechat_miniapp",
            ip_address=ip,
            success=True,
            auth_user_id=result.user.auth_user_id,
            user_agent=ua,
            message=None,
        )
        return success_response(result.model_dump(mode="json"))
    except AppException as exc:
        await append_login_attempt(
            login_name="wechat_miniapp",
            ip_address=ip,
            success=False,
            auth_user_id=None,
            user_agent=ua,
            message=(exc.message[:2000] if exc.message else None),
        )
        raise
    except Exception as exc:
        await append_login_attempt(
            login_name="wechat_miniapp",
            ip_address=ip,
            success=False,
            auth_user_id=None,
            user_agent=ua,
            message=str(exc)[:500],
        )
        raise


@router.post("/employee-qr-login/sessions")
async def create_employee_qr_login_session(request: Request) -> dict:
    settings = get_settings()
    ip = _client_ip(request)
    await enforce_fixed_window_rate_limit(
        namespace="employee_qr_login_create_ip", key_parts=[ip or "unknown"],
        limit=settings.auth_login_rate_limit_per_minute, window_seconds=60,
    )
    item = await employee_qr_login_service.create_session(
        pc_ip=ip, pc_user_agent=request.headers.get("user-agent") or ""
    )
    return success_response(item.model_dump(mode="json"))


@router.get("/employee-qr-login/sessions/{session_id}/status")
async def employee_qr_login_status(session_id: str, browser_secret: str = Query(...)) -> dict:
    item = await employee_qr_login_service.status(session_id, browser_secret)
    return success_response(item.model_dump(mode="json"))


@router.post("/employee-qr-login/sessions/{session_id}/exchange")
async def exchange_employee_qr_login(
    session_id: str, payload: EmployeeQrLoginBrowserRequest, request: Request
) -> dict:
    result = await employee_qr_login_service.exchange(session_id, payload.browser_secret)
    await online_user_registry.clear_session_revocation(result.user.auth_user_id)
    await append_login_attempt(
        login_name=result.user.email or "wechat-qr-login", ip_address=_client_ip(request),
        success=True, auth_user_id=result.user.auth_user_id,
        user_agent=request.headers.get("user-agent"), message="employee wechat qr login",
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/employee-qr-login/mobile/{scene}/wechat")
async def employee_qr_login_with_wechat(
    scene: str, payload: EmployeeQrLoginWechatRequest, request: Request
) -> dict:
    settings = get_settings()
    await enforce_fixed_window_rate_limit(
        namespace="employee_qr_login_wechat_ip",
        key_parts=[_client_ip(request) or "unknown", scene],
        limit=settings.auth_login_rate_limit_per_minute, window_seconds=60,
    )
    item = await employee_qr_login_service.login_or_bind_wechat(scene, payload)
    if item.login is not None:
        await online_user_registry.clear_session_revocation(item.login.user.auth_user_id)
    return success_response(item.model_dump(mode="json"))


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest, request: Request) -> dict:
    settings = get_settings()
    await enforce_fixed_window_rate_limit(
        namespace="auth_refresh_ip",
        key_parts=[_client_ip(request) or "unknown"],
        limit=settings.auth_refresh_rate_limit_per_minute,
        window_seconds=60,
    )
    result = await refresh_access_token(payload.refresh_token)
    return success_response(result.model_dump(mode="json"))


@router.get("/me")
async def current_user_profile(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    return success_response(current_user.model_dump(mode="json"))


@router.get("/menus")
async def current_user_menus(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    menus = await menu_service.tree_for_user(current_user)
    return success_response(menus)
