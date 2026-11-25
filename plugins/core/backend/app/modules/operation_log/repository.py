"""操作日志（audit_operation_log）：只追加；此处提供传统HTTP摘要查询。

业务字段差异通过公开Service与entity_change_repository复用业务事务写入/查询。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import table_scope_condition
from app.modules.user_profile.models import SysUser

from .models import AuditOperationLog
from .schemas import OperationLogItem, OperationLogListQuery


def _base_statement():
    return (
        select(
            AuditOperationLog.id,
            AuditOperationLog.org_id,
            AuditOperationLog.module_code,
            AuditOperationLog.action_code,
            AuditOperationLog.target_type_code,
            AuditOperationLog.target_id,
            AuditOperationLog.actor_user_id,
            SysUser.display_name.label("actor_name"),
            AuditOperationLog.is_agent_action,
            AuditOperationLog.is_sensitive,
            AuditOperationLog.request_id,
            AuditOperationLog.request_method,
            AuditOperationLog.request_path,
            AuditOperationLog.http_status,
            AuditOperationLog.content,
            AuditOperationLog.ip_address,
            AuditOperationLog.created_at,
        )
        .select_from(AuditOperationLog)
        .outerjoin(SysUser, SysUser.id == AuditOperationLog.actor_user_id)
    )


class OperationLogRepository:
    async def append(self, session, values):
        session.add(AuditOperationLog(**values))
        await session.flush()

    @staticmethod
    def _scope(current_user: AuthenticatedUser, permission_key: str):
        return table_scope_condition(AuditOperationLog, current_user, permission_key)

    async def list(self, session: AsyncSession, params: OperationLogListQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        statement = _base_statement()
        scope = self._scope(current_user, "operation_log:list")
        if scope is not None:
            statement = statement.where(scope)
        if params.keyword and params.keyword.strip():
            kw = f"%{params.keyword.strip()}%"
            statement = statement.where(
                or_(AuditOperationLog.module_code.ilike(kw), AuditOperationLog.action_code.ilike(kw), cast(AuditOperationLog.content, Text).ilike(kw))
            )
        if params.actor_name and params.actor_name.strip():
            statement = statement.where(SysUser.display_name.ilike(f"%{params.actor_name.strip()}%"))
        if params.actor_user_id:
            statement = statement.where(AuditOperationLog.actor_user_id == params.actor_user_id)
        if params.ip_address and params.ip_address.strip():
            statement = statement.where(AuditOperationLog.ip_address.ilike(f"%{params.ip_address.strip()}%"))
        if params.module_code and params.module_code.strip():
            statement = statement.where(AuditOperationLog.module_code == params.module_code.strip())
        if params.action_code and params.action_code.strip():
            statement = statement.where(AuditOperationLog.action_code == params.action_code.strip())
        if params.org_id:
            statement = statement.where(AuditOperationLog.org_id == params.org_id)
        if params.sensitive_only:
            statement = statement.where(AuditOperationLog.is_sensitive.is_(True))
        if params.target_type_code:
            statement = statement.where(AuditOperationLog.target_type_code == params.target_type_code)
        if params.target_id:
            statement = statement.where(AuditOperationLog.target_id == params.target_id)
        if params.http_status is not None:
            statement = statement.where(AuditOperationLog.http_status == params.http_status)
        if params.successful is not None:
            statement = statement.where(AuditOperationLog.http_status < 400 if params.successful else AuditOperationLog.http_status >= 400)
        if params.created_start is not None:
            statement = statement.where(AuditOperationLog.created_at >= params.created_start)
        if params.created_end is not None:
            statement = statement.where(AuditOperationLog.created_at <= params.created_end)
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        rows = (
            await session.execute(
                statement.order_by(AuditOperationLog.created_at.desc()).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        return {"items": [OperationLogItem(**r._mapping).model_dump(mode="json") for r in rows], "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, session: AsyncSession, item_id: UUID, current_user: AuthenticatedUser) -> OperationLogItem | None:
        statement = _base_statement().where(AuditOperationLog.id == item_id)
        scope = self._scope(current_user, "operation_log:detail")
        if scope is not None:
            statement = statement.where(scope)
        row = (await session.execute(statement)).one_or_none()
        return OperationLogItem(**row._mapping) if row else None


repository = OperationLogRepository()
