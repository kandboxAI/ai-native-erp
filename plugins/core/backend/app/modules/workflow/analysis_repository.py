"""审批业务AI分析的持久队列；不读取行业数据。"""
from sqlmodel import select
from app.framework.db.models import utc_now
from .models import WfInstance


async def locked_instance(session, instance_id):
    return (await session.exec(select(WfInstance).where(WfInstance.id == instance_id).with_for_update())).first()


async def queue(session, instance_id):
    row = await session.get(WfInstance, instance_id)
    if row:
        row.ai_analysis_status_code = "pending"
        row.ai_analysis_started_at = utc_now()
        row.ai_analysis_error = ""
        row.updated_at, row.updated_by = utc_now(), row.started_by
        session.add(row)


async def actor_claims(session, instance_id):
    from app.auth.models import AuthTenant
    from app.modules.user_profile.models import SysUser
    from app.framework.db.tenant import get_tenant_schema
    actor = (await session.exec(select(SysUser.auth_user_id).join(WfInstance, WfInstance.started_by == SysUser.id)
        .where(WfInstance.id == instance_id, SysUser.is_active.is_(True), SysUser.deleted_at.is_(None)))).first()
    tenant = (await session.exec(select(AuthTenant.id).where(AuthTenant.schema_name == get_tenant_schema(), AuthTenant.is_active.is_(True)))).first()
    return {"sub": str(actor), "tenant_id": str(tenant)} if actor and tenant else None


async def claim(session, instance_id):
    row = (await session.exec(select(WfInstance).where(WfInstance.id == instance_id).with_for_update(skip_locked=True))).first()
    if not row or row.status_code != "running" or row.ai_analysis_status_code != "pending":
        return None
    row.ai_analysis_status_code = "processing"
    row.ai_analysis_started_at = utc_now()
    row.ai_analysis_error = ""
    row.updated_at, row.updated_by = utc_now(), None
    session.add(row)
    await session.flush()
    return row


async def finish(session, instance_id, lease, source_hash, result=None, model="", error="", stale=False):
    row = (await session.exec(select(WfInstance).where(WfInstance.id == instance_id).with_for_update())).first()
    if not row or row.status_code != "running" or row.ai_analysis_status_code != "processing" or row.ai_analysis_started_at != lease:
        return False
    if stale:
        row.ai_analysis_status_code = "failed"
        row.ai_analysis_error = "分析期间依据已变化"
    elif error:
        row.ai_analysis_status_code, row.ai_analysis_error = "failed", error[:300]
    else:
        row.ai_analysis_status_code = "succeeded"
        row.ai_analysis, row.ai_analysis_model = result, model
        row.ai_analysis_source_hash, row.ai_analysis_generated_at = source_hash, utc_now()
    row.updated_at, row.updated_by = utc_now(), getattr(row, "started_by", None)
    session.add(row)
    await session.flush()
    return True
