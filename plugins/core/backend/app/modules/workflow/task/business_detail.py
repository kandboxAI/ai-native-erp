"""审批待办中的业务单据摘要与详情：由业务模块经 register_business_adapter 提供。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.workflow.integration.registry import get_business_adapter


def _empty(message: str) -> dict[str, Any]:
    return {"fields": [{"label": "提示", "value": message}], "tables": []}


async def load_workflow_business_detail(session: AsyncSession, *, business_type_code: str, business_id: UUID, current_user=None) -> dict[str, Any]:
    adapter = get_business_adapter(business_type_code)
    if adapter is None or adapter.detail is None:
        return _empty(f"业务类型「{business_type_code}」尚未接入审批详情，请前往对应业务页查看")
    if adapter.detail_access and (current_user is None or not await adapter.detail_access(session, business_id, current_user)):
        return _empty("当前账号不在该业务资料的读取范围内，请联系业务负责人")
    detail = await adapter.detail(session, business_id)
    avatar_url = await adapter.avatar(session, business_id) if adapter.avatar else None
    if avatar_url:
        detail = {**detail, "fields": [
            {"label": "头像", "value": avatar_url, "type": "avatar"},
            *detail.get("fields", []),
        ]}
    return detail


async def load_business_avatar(session: AsyncSession, *, business_type_code: str, business_id: UUID, current_user) -> str | None:
    adapter = get_business_adapter(business_type_code)
    if adapter is None or adapter.avatar is None:
        return None
    if adapter.detail_access and not await adapter.detail_access(session, business_id, current_user):
        return None
    return await adapter.avatar(session, business_id)


async def load_business_summary(session: AsyncSession, *, business_type_code: str, business_id: UUID, current_user=None) -> str:
    adapter = get_business_adapter(business_type_code)
    if adapter and adapter.detail_access and (current_user is None or not await adapter.detail_access(session, business_id, current_user)):
        return adapter.label
    summary = await adapter.summary(session, business_id) if adapter and adapter.summary else None
    return summary or f"{adapter.label if adapter else business_type_code}"
