from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from app.auth.models import AuthIdentity
from app.auth.repository import repository as auth_repository
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.framework.datetime_local import naive_local_now
from app.framework.db.session import get_session_context
from app.integrations.wechat_miniapp import client as wechat_client

from .qr_login_models import (
    EmployeeQrLoginSessionCreateResult,
    EmployeeQrLoginSessionRecord,
    EmployeeQrLoginStatusItem,
    EmployeeQrLoginWechatRequest,
    EmployeeQrLoginWechatResult,
)
from .qr_login_repository import repository
from .service import login_with_auth_user_id
from .wechat_login_service import WECHAT_MINIAPP_PROVIDER


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _verify(record: EmployeeQrLoginSessionRecord, secret: str) -> None:
    if not secrets.compare_digest(record.browser_secret_hash, _secret_hash(secret.strip())):
        raise AppException("扫码登录会话校验失败", status_code=403)


class EmployeeQrLoginService:
    async def create_session(self, *, pc_ip: str, pc_user_agent: str) -> EmployeeQrLoginSessionCreateResult:
        settings = get_settings()
        prefix = settings.wechat_employee_qr_login_url_prefix.strip()
        if not prefix:
            raise AppException("未配置微信扫码登录地址", status_code=500)
        ttl = settings.employee_qr_login_ttl_seconds
        now = naive_local_now()
        for _ in range(3):
            secret = secrets.token_urlsafe(32)
            record = EmployeeQrLoginSessionRecord(
                session_id=uuid4().hex, scene=secrets.token_urlsafe(18),
                browser_secret_hash=_secret_hash(secret), pc_ip=pc_ip[:64],
                pc_user_agent=pc_user_agent[:300], created_at=now,
            )
            try:
                await repository.create(record, ttl)
                return EmployeeQrLoginSessionCreateResult(
                    session_id=record.session_id, browser_secret=secret,
                    qr_url=f"{prefix.rstrip('/')}/{quote(record.scene, safe='')}",
                    status="pending", expires_in=ttl, expires_at=now + timedelta(seconds=ttl),
                )
            except RuntimeError:
                continue
        raise AppException("创建扫码登录会话失败，请重试", status_code=500)

    async def status(self, session_id: str, secret: str) -> EmployeeQrLoginStatusItem:
        record = await repository.get(session_id)
        if record is None:
            return EmployeeQrLoginStatusItem(session_id=session_id, status="expired")
        _verify(record, secret)
        return EmployeeQrLoginStatusItem(session_id=session_id, status=record.status,
                                         employee_name=record.employee_name,
                                         expires_in=await repository.ttl(session_id))

    async def login_or_bind_wechat(self, scene: str, payload: EmployeeQrLoginWechatRequest) -> EmployeeQrLoginWechatResult:
        record = await repository.get_by_scene(scene)
        if record is None:
            raise AppException("登录二维码已过期，请在电脑端刷新", status_code=410)
        if record.status not in {"pending", "scanned"}:
            raise AppException("当前登录请求已处理，请勿重复操作", status_code=409)
        settings = get_settings()
        appid = (settings.wechat_miniapp_appid or "").strip()
        if not appid:
            raise AppException("未配置微信小程序 appid", status_code=500)
        wechat = await wechat_client.code2session(payload.code)
        async with get_session_context() as session:
            identity = await auth_repository.find_auth_identity(
                session, provider=WECHAT_MINIAPP_PROVIDER, appid=appid,
                external_user_no=wechat.openid,
            )
            auth_user = await auth_repository.get_auth_user(session, identity.auth_user_id) if identity else None
            if auth_user is None:
                if not payload.phone_code:
                    await self._mark_scanned(record)
                    return EmployeeQrLoginWechatResult(status="scanned", bound=False, requires_phone=True)
                phone = (await wechat_client.get_phone_number(payload.phone_code)).pure_phone_number.strip()
                auth_user = await auth_repository.find_auth_user_by_login(session, email=None, mobile=phone)
                if auth_user is None:
                    raise AppException("手机号未匹配到系统账号，请联系管理员", status_code=403)
                if not auth_user.is_active:
                    raise AppException("账号已停用，请联系管理员", status_code=403)
                existing = await auth_repository.find_auth_identity_for_user(
                    session, provider=WECHAT_MINIAPP_PROVIDER, appid=appid, auth_user_id=auth_user.id,
                )
                if existing:
                    raise AppException("该账号已绑定其他微信，请联系管理员", status_code=409)
                session.add(AuthIdentity(provider=WECHAT_MINIAPP_PROVIDER, appid=appid,
                                         external_user_no=wechat.openid, unionid=wechat.unionid,
                                         auth_user_id=auth_user.id))
                await session.commit()
        login = await login_with_auth_user_id(auth_user.id)
        name = str(login.user.display_name or login.user.profile.get("full_name") or login.user.email or "用户")
        if payload.confirm:
            await self._confirm(record, str(login.user.auth_user_id), name)
            return EmployeeQrLoginWechatResult(status="confirmed", bound=True, requires_phone=False,
                                               employee_name=name, login=login)
        await self._mark_scanned(record)
        return EmployeeQrLoginWechatResult(status="scanned", bound=True, requires_phone=False, employee_name=name)

    async def _mark_scanned(self, record: EmployeeQrLoginSessionRecord) -> None:
        now = naive_local_now()
        await repository.transition(record.session_id, allowed={"pending"},
                                    mutate=lambda row: (setattr(row, "status", "scanned"), setattr(row, "scanned_at", now)))

    async def _confirm(self, record: EmployeeQrLoginSessionRecord, auth_user_id: str, name: str) -> None:
        now = naive_local_now()
        def mutate(row):
            row.status, row.auth_user_id, row.employee_name, row.confirmed_at = "confirmed", auth_user_id, name, now
        _, changed = await repository.transition(record.session_id, allowed={"pending", "scanned"}, mutate=mutate)
        if not changed:
            raise AppException("登录请求状态已变化，请重新扫码", status_code=409)

    async def exchange(self, session_id: str, secret: str):
        record = await repository.get(session_id)
        if record is None:
            raise AppException("登录二维码已过期，请刷新", status_code=410)
        _verify(record, secret)
        if record.status != "confirmed" or not record.auth_user_id:
            raise AppException("用户尚未确认登录", status_code=409)
        now = naive_local_now()
        consumed, changed = await repository.transition(
            session_id, allowed={"confirmed"},
            mutate=lambda row: (setattr(row, "status", "consumed"), setattr(row, "consumed_at", now)),
        )
        if not changed or consumed is None or not consumed.auth_user_id:
            raise AppException("登录凭证已使用，请重新扫码", status_code=409)
        return await login_with_auth_user_id(UUID(consumed.auth_user_id))


service = EmployeeQrLoginService()
