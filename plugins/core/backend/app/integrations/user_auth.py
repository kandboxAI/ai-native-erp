"""登录账号（public.auth_user）管理：查找、创建、改密、启停。

登录账号全局唯一、不属于任何租户；租户内的用户身份在各租户 schema 的 sys_user 中。
调用方传入会话（不在这里提交），以便与租户内用户的写入放在同一事务中。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import AuthPasswordHistory, AuthUser
from app.auth.password import hash_password
from app.core.exceptions import AppException
from app.framework.db.models import utc_now


def normalize_email(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value or None


def normalize_mobile(mobile: str | None) -> str | None:
    value = (mobile or "").strip()
    return value or None


async def find_auth_user(session: AsyncSession, *, email: str | None = None, mobile: str | None = None) -> AuthUser | None:
    """按邮箱或手机号查找登录账号（邮箱优先）。"""
    email = normalize_email(email)
    mobile = normalize_mobile(mobile)
    if email:
        found = (await session.execute(select(AuthUser).where(func.lower(AuthUser.email) == email).limit(1))).scalar_one_or_none()
        if found is not None:
            return found
    if mobile:
        return (await session.execute(select(AuthUser).where(AuthUser.mobile == mobile).limit(1))).scalar_one_or_none()
    return None


async def find_auth_user_by_login_name(session: AsyncSession, login_name: str | None) -> AuthUser | None:
    """按用户输入的登录名查找账号（规则与登录一致）。"""
    if not login_name or not login_name.strip():
        return None
    from app.auth.login_email import resolve_login_identity

    email, mobile = resolve_login_identity(login_name)
    return await find_auth_user(session, email=email, mobile=mobile)


async def create_auth_user(
    session: AsyncSession,
    *,
    email: str | None,
    mobile: str | None,
    password: str,
    created_by: UUID | None = None,
    is_password_change_required: bool = False,
) -> AuthUser:
    """新建登录账号；邮箱或手机号已被占用时报错。"""
    email = normalize_email(email)
    mobile = normalize_mobile(mobile)
    if not email and not mobile:
        raise AppException("邮箱和手机号至少填写一个", status_code=status.HTTP_400_BAD_REQUEST)
    if email and await find_auth_user(session, email=email) is not None:
        raise AppException("该邮箱已被其他账号使用", status_code=status.HTTP_409_CONFLICT)
    if mobile and await find_auth_user(session, mobile=mobile) is not None:
        raise AppException("该手机号已被其他账号使用", status_code=status.HTTP_409_CONFLICT)
    password_hash = hash_password(password)
    user = AuthUser(
        email=email,
        mobile=mobile,
        password_hash=password_hash,
        is_email_verified=bool(email),
        password_changed_at=utc_now(),
        is_password_change_required=is_password_change_required,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(user)
    await session.flush()
    session.add(AuthPasswordHistory(auth_user_id=user.id, password_hash=password_hash))
    return user


async def set_password(
    session: AsyncSession,
    auth_user_id: UUID,
    password: str,
    *,
    updated_by: UUID | None = None,
    is_password_change_required: bool = False,
) -> AuthUser:
    """重设登录密码（记录密码历史，清除登录失败锁定）。updated_by 为登录账号 ID。"""
    user = await session.get(AuthUser, auth_user_id)
    if user is None:
        raise AppException("登录账号不存在", status_code=status.HTTP_404_NOT_FOUND)
    password_hash = hash_password(password)
    user.password_hash = password_hash
    user.password_changed_at = utc_now()
    user.is_password_change_required = is_password_change_required
    user.failed_login_count = 0
    user.locked_until = None
    user.updated_by = updated_by
    session.add(user)
    session.add(AuthPasswordHistory(auth_user_id=user.id, password_hash=password_hash))
    await session.flush()
    return user


async def get_user_email(session: AsyncSession, auth_user_id: UUID) -> str | None:
    email = (await session.execute(select(AuthUser.email).where(AuthUser.id == auth_user_id).limit(1))).scalar_one_or_none()
    return str(email).strip() if email else None
