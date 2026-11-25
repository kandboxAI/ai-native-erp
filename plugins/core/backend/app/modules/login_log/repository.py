"""登录日志（public.auth_login_log）：只追加；查询时只显示属于当前租户的账号（auth_membership）的日志。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthLoginLog, AuthMembership
from app.framework.db.session import get_session_context
from app.modules.user_profile.models import SysUser

from .schemas import LoginLogItem, LoginLogListQuery


class LoginLogRepository:
    async def list(self, session: AsyncSession, params: LoginLogListQuery, tenant_id: UUID) -> dict[str, Any]:
        conditions: list[Any] = [
            exists().where(AuthMembership.auth_user_id == AuthLoginLog.auth_user_id, AuthMembership.tenant_id == tenant_id)
        ]
        if params.keyword and params.keyword.strip():
            kw = f"%{params.keyword.strip()}%"
            conditions.append(or_(AuthLoginLog.login_name.ilike(kw), AuthLoginLog.message.ilike(kw), SysUser.display_name.ilike(kw)))
        if params.login_name and params.login_name.strip():
            kw = f"%{params.login_name.strip()}%"
            conditions.append(or_(AuthLoginLog.login_name.ilike(kw), SysUser.display_name.ilike(kw)))
        if params.ip_address and params.ip_address.strip():
            conditions.append(AuthLoginLog.ip_address.ilike(f"%{params.ip_address.strip()}%"))
        if params.is_success is not None:
            conditions.append(AuthLoginLog.is_success.is_(params.is_success))
        if params.created_start is not None:
            conditions.append(AuthLoginLog.created_at >= params.created_start)
        if params.created_end is not None:
            conditions.append(AuthLoginLog.created_at <= params.created_end)

        base = (
            select(
                AuthLoginLog.id,
                AuthLoginLog.auth_user_id,
                SysUser.id.label("user_id"),
                SysUser.display_name,
                AuthLoginLog.login_name,
                AuthLoginLog.ip_address,
                AuthLoginLog.user_agent,
                AuthLoginLog.is_success,
                AuthLoginLog.message,
                AuthLoginLog.created_at,
            )
            .select_from(AuthLoginLog)
            .outerjoin(SysUser, and_(SysUser.auth_user_id == AuthLoginLog.auth_user_id, SysUser.deleted_at.is_(None)))
            .where(*conditions)
        )
        total = int((await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                base.order_by(AuthLoginLog.created_at.desc()).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        items = [LoginLogItem(**row._mapping).model_dump(mode="json") for row in rows]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


repository = LoginLogRepository()


async def append_login_attempt(
    *,
    login_name: str,
    ip_address: str,
    success: bool,
    auth_user_id: UUID | None = None,
    user_agent: str | None = None,
    message: str | None = None,
) -> None:
    """记录一次登录尝试（public.auth_login_log）。登录失败但账号存在时也记下账号，便于按租户查看。"""
    from app.integrations.user_auth import find_auth_user_by_login_name

    try:
        async with get_session_context() as session:
            if auth_user_id is None:
                found = await find_auth_user_by_login_name(session, login_name)
                auth_user_id = found.id if found else None
            session.add(
                AuthLoginLog(
                    auth_user_id=auth_user_id,
                    login_name=(login_name or "").strip()[:128] or None,
                    ip_address=(ip_address or "")[:64] or None,
                    user_agent=user_agent,
                    is_success=success,
                    message=message,
                )
            )
            await session.commit()
    except Exception:
        return
