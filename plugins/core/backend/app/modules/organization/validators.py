"""通用组织写入校验；行业专属限制由插件的 Repository 校验。"""
from uuid import UUID
from fastapi import status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from .models import SysOrg

async def get_active_org(session: AsyncSession, org_id: UUID) -> SysOrg:
    org = (await session.execute(select(SysOrg).where(SysOrg.id == org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True)))).scalar_one_or_none()
    if org is None:
        raise AppException("组织不存在或已停用", status_code=status.HTTP_400_BAD_REQUEST)
    return org

async def ensure_active_org(session: AsyncSession, current_user: AuthenticatedUser | None, org_id: UUID | None) -> UUID:
    if org_id is None:
        raise AppException("请选择所属组织", status_code=400)
    return (await get_active_org(session, UUID(str(org_id)))).id

async def ensure_active_org_access(session, current_user, org_id, permission_key=None):
    accessed = ensure_org_access(current_user, org_id, permission_key)
    return await ensure_active_org(session, current_user, accessed)
