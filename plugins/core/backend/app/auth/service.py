import secrets
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from html import escape
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.auth.data_scope import ORG_ACCESS_ALL, normalize_org_access_mode
from app.auth.login_email import resolve_login_identity
from app.auth.models import AuthUser
from app.auth.password import verify_password
from app.auth.plugin_repository import repository as plugin_repository
from app.auth.repository import repository
from app.auth.schemas import (
    AuthenticatedUser,
    AuthSession,
    LoginCaptchaResponse,
    LoginPortal,
    LoginResponse,
)
from app.auth.token import (
    RefreshSession,
    create_access_token,
    issue_refresh_token,
    rotate_refresh_token,
    verify_access_token,
    verify_refresh_token,
)
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.runtime import online_user_registry
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.db.tenant import use_tenant_schema


FAMILY_ACCOUNT_USED_FOR_EMPLOYEE_LOGIN_MESSAGE = "该账号为家长账号，请切换到家长端登录或使用教职工账号登录"
EMPLOYEE_ACCOUNT_USED_FOR_FAMILY_LOGIN_MESSAGE = "该账号没有监护人身份，请切换到教职工端登录"
LOGIN_FAILED_MESSAGE = "账号或密码错误"
ACCOUNT_LOCKED_MESSAGE = "登录失败次数过多，账号已临时锁定，请稍后再试"
NO_TENANT_MESSAGE = "该账号尚未开通任何租户，请联系管理员"
TENANT_USER_DISABLED_MESSAGE = "账号在当前租户未启用或已停用，请联系管理员"
LOGIN_LOCK_THRESHOLD = 10
LOGIN_LOCK_MINUTES = 15
LOGIN_CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
LOGIN_CAPTCHA_LENGTH = 4
LOGIN_CAPTCHA_WIDTH = 128
LOGIN_CAPTCHA_HEIGHT = 42


def _random_between(start: int, end: int) -> int:
    return start + secrets.randbelow(end - start + 1)


def _build_login_captcha_code() -> str:
    return "".join(
        secrets.choice(LOGIN_CAPTCHA_ALPHABET)
        for _ in range(LOGIN_CAPTCHA_LENGTH)
    )


def _build_login_captcha_image(code: str) -> str:
    line_colors = ["#94a3b8", "#60a5fa", "#34d399", "#f59e0b"]
    text_colors = ["#0f172a", "#1d4ed8", "#047857", "#9a3412"]
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{LOGIN_CAPTCHA_WIDTH}" '
            f'height="{LOGIN_CAPTCHA_HEIGHT}" viewBox="0 0 {LOGIN_CAPTCHA_WIDTH} {LOGIN_CAPTCHA_HEIGHT}">'
        ),
        '<rect width="100%" height="100%" rx="6" fill="#f8fafc"/>',
    ]
    for idx in range(5):
        color = line_colors[idx % len(line_colors)]
        parts.append(
            f'<path d="M{_random_between(0, 24)} {_random_between(5, 37)} '
            f'C{_random_between(32, 56)} {_random_between(0, 42)}, '
            f'{_random_between(70, 96)} {_random_between(0, 42)}, '
            f'{_random_between(104, 128)} {_random_between(5, 37)}" '
            f'stroke="{color}" stroke-width="1.2" fill="none" opacity="0.5"/>'
        )
    for idx, char in enumerate(code):
        x = 18 + idx * 27 + _random_between(-2, 2)
        y = _random_between(27, 33)
        rotate = _random_between(-18, 18)
        color = text_colors[idx % len(text_colors)]
        parts.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-size="24" font-weight="700" '
            f'font-family="Arial, Helvetica, sans-serif" transform="rotate({rotate} {x} {y})">'
            f'{escape(char)}</text>'
        )
    for _ in range(18):
        parts.append(
            f'<circle cx="{_random_between(4, 124)}" cy="{_random_between(4, 38)}" '
            f'r="{_random_between(1, 2)}" fill="#64748b" opacity="0.35"/>'
        )
    parts.append("</svg>")
    encoded = b64encode("".join(parts).encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


async def create_login_captcha() -> LoginCaptchaResponse:
    settings = get_settings()
    captcha_id = str(uuid4())
    code = _build_login_captcha_code()
    await repository.save_login_captcha(
        captcha_id,
        code,
        settings.auth_login_captcha_ttl_seconds,
    )
    return LoginCaptchaResponse(
        captcha_id=captcha_id,
        image=_build_login_captcha_image(code),
        expires_in=settings.auth_login_captcha_ttl_seconds,
    )


async def verify_login_captcha(captcha_id: str, captcha_code: str) -> None:
    clean_id = (captcha_id or "").strip()
    clean_code = (captcha_code or "").strip().lower()
    if not clean_id:
        raise AppException("请刷新验证码后重试", status_code=status.HTTP_400_BAD_REQUEST)
    if not clean_code:
        raise AppException("请输入验证码", status_code=status.HTTP_400_BAD_REQUEST)

    expected = await repository.consume_login_captcha(clean_id)
    if expected is None:
        raise AppException("验证码已失效，请刷新后重试", status_code=status.HTTP_400_BAD_REQUEST)
    if not secrets.compare_digest(expected, clean_code):
        raise AppException("验证码错误，请刷新后重试", status_code=status.HTTP_400_BAD_REQUEST)


async def _resolve_tenant_id(session, auth_user_id: UUID, requested: UUID | None) -> UUID:
    """确定本次会话进入的租户（public）：指定的租户须在账号可进入的租户中；未指定时取最近进入的一个。"""
    memberships = await repository.list_memberships(session, auth_user_id)
    if not memberships:
        raise AppException(NO_TENANT_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
    # 本地多能力包部署可能让同一个管理员同时属于教育租户和 MES 租户。
    # 管理端当前未提供租户选择器时，优先进入服务配置的默认租户，避免
    # 启动后仍然落到历史租户；没有匹配项时保持“最近进入租户”兼容行为。
    default_tenant_no = get_settings().default_tenant_no
    chosen = next(
        (membership for membership, tenant in memberships if tenant.tenant_no == default_tenant_no),
        memberships[0][0],
    )
    if requested is not None:
        chosen = next((membership for membership, _ in memberships if membership.tenant_id == requested), None)
        if chosen is None:
            raise AppException("无权进入该租户", status_code=status.HTTP_403_FORBIDDEN)
    await repository.touch_membership(session, chosen)
    return chosen.tenant_id


async def build_authenticated_user(claims: dict) -> AuthenticatedUser:
    """由访问令牌（或登录成功后的账号）构建当前用户。

    claims 含 sub（登录账号），可含 tenant_id（public.auth_tenant.id）；没有时取账号最近进入的租户。
    先在 public 校验账号、租户与成员关系，再切换到该租户的 schema 加载租户内用户、权限与组织。
    """
    auth_user_id = UUID(str(claims["sub"]))
    async with get_session_context() as session:
        auth_user = await repository.get_auth_user(session, auth_user_id)
        if auth_user is None or not auth_user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已失效，请重新登录")
        tenant_claim = claims.get("tenant_id")
        if tenant_claim:
            tenant_id = UUID(str(tenant_claim))
            if await repository.get_membership(session, auth_user_id, tenant_id) is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已不能进入该租户，请重新登录")
        else:
            tenant_id = await _resolve_tenant_id(session, auth_user_id, None)
        tenant = await repository.get_tenant(session, tenant_id)
        if tenant is None or not tenant.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="租户未开通或已停用")
        from app.framework.deployment import effective_plugin_keys

        enabled_plugin_keys = effective_plugin_keys(await plugin_repository.active_keys(session, tenant.id))
        if session.dirty:
            await session.commit()

    from app.framework.deployment import blocked_plugin_module_codes

    blocked_module_codes = blocked_plugin_module_codes(enabled_plugin_keys)
    with use_tenant_schema(tenant.schema_name):
        async with get_session_context() as session:
            sys_user = await repository.get_tenant_user(session, auth_user_id)
            if sys_user is None or not sys_user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TENANT_USER_DISABLED_MESSAGE)
            grants = await repository.get_grants(session, sys_user.id, blocked_module_codes)
            grants = await repository.extend_grants(session, sys_user, grants, enabled_plugin_keys)
            user_orgs = await repository.get_user_orgs(session, sys_user.id)
            person = await repository.get_person(session, sys_user.id)
            party_id = person.party_id if person else None
            is_guardian, is_teacher = await repository.get_identity_flags(session, party_id, enabled_plugin_keys=enabled_plugin_keys)
            from app.modules.user_profile.avatar_service import service as avatars
            avatar_url = await avatars.url_for_user(session, sys_user.id, legacy_url=sys_user.avatar_url)

    org_access_mode = normalize_org_access_mode(sys_user.org_access_mode_code)
    primary = next((item for item in user_orgs if item.is_primary), user_orgs[0] if user_orgs else None)
    org_ids = [] if org_access_mode == ORG_ACCESS_ALL else [item.org_id for item in user_orgs]
    return AuthenticatedUser(
        auth_user_id=auth_user_id,
        tenant_id=tenant.id,
        tenant_no=tenant.tenant_no,
        tenant_schema=tenant.schema_name,
        tenant_name=tenant.tenant_name,
        user_id=sys_user.id,
        party_id=party_id,
        org_id=primary.org_id if primary else sys_user.org_id,
        org_ids=org_ids,
        org_access_mode_code=org_access_mode,
        department_id=sys_user.department_id,
        email=auth_user.email,
        display_name=sys_user.display_name,
        avatar_url=avatar_url,
        data_scope_code=grants.data_scope_code,
        permission_scopes=grants.permission_scopes,
        role_nos=grants.role_nos,
        role_names=grants.role_names,
        permissions=grants.permissions,
        enabled_plugin_keys=sorted(enabled_plugin_keys),
        is_guardian=is_guardian,
        is_teacher=is_teacher,
        profile={**repository.profile_payload(sys_user, person, auth_user), "avatar_url": avatar_url},
    )


async def _build_auth_session(auth_user_id: UUID, email: str | None, tenant_id: UUID, *, remember_me: bool,
                              remember_days: int = 7) -> AuthSession:
    settings = get_settings()
    if remember_me and remember_days > settings.jwt_refresh_expire_days:
        raise AppException(f"免登录期限不能超过 {settings.jwt_refresh_expire_days} 天")
    seconds = remember_days * 86400 if remember_me else settings.auth_session_expire_hours * 3600
    session_expires_at = int(datetime.now(UTC).timestamp()) + seconds
    access_token, expires_in, expires_at = create_access_token(auth_user_id, email, tenant_id, session_expires_at=session_expires_at)
    refresh_token = await issue_refresh_token(RefreshSession(auth_user_id, email, remember_me, session_expires_at, tenant_id))
    return AuthSession(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        expires_at=expires_at,
        remember_me=remember_me,
        session_expires_at=session_expires_at,
    )


def _enforce_login_portal(auth_user: AuthenticatedUser, portal: LoginPortal | None) -> None:
    if portal is None:
        return
    from app.framework.catalog import iter_module_attr
    for module in iter_module_attr("login_portal"):
        module.enforce_login_portal(auth_user, portal)
        return
    # The employee portal is the legacy name of the generic administration client.
    if portal != "employee":
        raise AppException("当前部署未提供此登录入口", status_code=status.HTTP_403_FORBIDDEN)


async def enforce_employee_portal_user(auth_user: AuthenticatedUser) -> None:
    """校验当前登录态可以进入教职工端。"""
    _enforce_login_portal(auth_user, "employee")


async def _verify_credentials(login_name: str, password: str) -> AuthUser:
    email, mobile = resolve_login_identity(login_name)
    async with get_session_context() as session:
        user = await repository.find_auth_user_by_login(session, email=email, mobile=mobile)
        if user is None or not user.is_active or not user.password_hash:
            raise AppException(LOGIN_FAILED_MESSAGE, status_code=status.HTTP_401_UNAUTHORIZED)
        now = utc_now()
        if user.locked_until is not None and user.locked_until > now:
            raise AppException(ACCOUNT_LOCKED_MESSAGE, status_code=status.HTTP_423_LOCKED)
        if not verify_password(password, user.password_hash):
            await repository.record_login_failure(
                session,
                user,
                threshold=LOGIN_LOCK_THRESHOLD,
                lock_until=now + timedelta(minutes=LOGIN_LOCK_MINUTES),
            )
            raise AppException(LOGIN_FAILED_MESSAGE, status_code=status.HTTP_401_UNAUTHORIZED)
        await repository.reset_login_failures(session, user)
        await session.commit()
        return user


async def authenticate_with_password(
    login_name: str,
    password: str,
    portal: LoginPortal | None = None,
    tenant_id: UUID | None = None,
) -> AuthenticatedUser:
    """只校验账号、租户与门户，不签发 token；供绑定等事务前置校验复用。"""
    user = await _verify_credentials(login_name, password)
    async with get_session_context() as session:
        resolved_tenant_id = await _resolve_tenant_id(session, user.id, tenant_id)
        await session.commit()
    auth_user = await build_authenticated_user({"sub": str(user.id), "tenant_id": str(resolved_tenant_id)})
    _enforce_login_portal(auth_user, portal)
    return auth_user


async def login_with_password(login_name: str, password: str, portal: LoginPortal | None = None,
                              tenant_id: UUID | None = None, *,
                              remember_me: bool = False, remember_days: int = 7) -> LoginResponse:
    auth_user = await authenticate_with_password(login_name, password, portal, tenant_id)
    session = await _build_auth_session(auth_user.auth_user_id, auth_user.email, auth_user.tenant_id,
                                       remember_me=remember_me, remember_days=remember_days)
    return LoginResponse(session=session, user=auth_user)


async def login_with_auth_user_id(auth_user_id: UUID, tenant_id: UUID | None = None) -> LoginResponse:
    """外部身份（如微信）认证通过后，按登录账号直接签发会话。"""
    async with get_session_context() as session:
        user = await repository.get_auth_user(session, auth_user_id)
        if user is None or not user.is_active:
            raise AppException("账号不存在或已停用", status_code=status.HTTP_401_UNAUTHORIZED)
        resolved_tenant_id = await _resolve_tenant_id(session, auth_user_id, tenant_id)
        await session.commit()
    auth_session = await _build_auth_session(user.id, user.email, resolved_tenant_id, remember_me=True,
                                            remember_days=get_settings().jwt_refresh_expire_days)
    claims = verify_access_token(auth_session.access_token)
    auth_user = await build_authenticated_user(claims)
    return LoginResponse(session=auth_session, user=auth_user)


async def refresh_access_token(refresh_token: str) -> AuthSession:
    refresh_session = await verify_refresh_token(refresh_token)
    user_id, email = refresh_session.user_id, refresh_session.email
    if await online_user_registry.is_session_revoked(user_id):
        raise AppException("session terminated by administrator", status_code=status.HTTP_401_UNAUTHORIZED)

    access_token, expires_in, expires_at = create_access_token(user_id, email, refresh_session.tenant_id,
                                                              session_expires_at=refresh_session.expires_at)
    new_refresh_token = await rotate_refresh_token(refresh_token, refresh_session)
    return AuthSession(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        expires_at=expires_at,
        remember_me=refresh_session.remember_me,
        session_expires_at=refresh_session.expires_at,
    )
