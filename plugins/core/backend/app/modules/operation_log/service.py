from typing import Any
from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.framework.db.session import get_session_context
from app.framework.db.tenant import use_tenant_schema

from .repository import repository
from .schemas import OperationLogItem, OperationLogListQuery


class OperationLogService:
    async def record(self, current_user, **values):
        """由认证后的请求上下文调用；不接受客户端 schema 或动作人。"""
        with use_tenant_schema(current_user.tenant_schema):
            async with get_session_context() as session:
                await repository.append(session, {**values, "org_id": current_user.org_id,
                    "actor_user_id": current_user.user_id, "created_by": current_user.user_id})
                await session.commit()

    async def list(self, params: OperationLogListQuery, current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            return await repository.list(session, params, current_user)

    async def detail(self, item_id: str, current_user: AuthenticatedUser) -> OperationLogItem | None:
        try:
            pk = UUID(str(item_id))
        except ValueError:
            return None
        async with get_session_context() as session:
            return await repository.detail(session, pk, current_user)


service = OperationLogService()


def append_entity_change(session, **values):
    """拥有者提供已鉴权对象、白名单差异；只追加到其事务，不单独提交。"""
    from .entity_change_repository import append_change
    append_change(session, **values)


async def query_entity_changes(session, **query):
    """拥有者提供目标模型和当前范围，返回同范围内的字段变更。"""
    from .entity_change_repository import query_changes
    return await query_changes(session, **query)
