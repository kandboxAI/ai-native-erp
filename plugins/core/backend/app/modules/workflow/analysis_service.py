"""通用审批AI分析调度；分析仅作参考，永不代替人工办理任务。"""
import asyncio
import hashlib
import logging
from datetime import timedelta

from sqlalchemy import event
import json
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import TenantSession, get_session_context
from app.framework.db.tenant import require_tenant_schema, use_tenant_schema
from .integration.registry import get_business_adapter
from . import analysis_repository as repo


def fingerprint(facts):
    return hashlib.sha256(json.dumps(facts,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


async def current_user(claims):
    from app.auth.service import build_authenticated_user
    if not claims:
        raise AppException("分析发起账号已不可用",403)
    return await build_authenticated_user(claims)


_SCHEDULED = "workflow_ai_analysis"
_tasks: set[asyncio.Task] = set()
logger = logging.getLogger(__name__)


async def queue_after_commit(session, instance_id):
    schema = require_tenant_schema()
    await repo.queue(session, instance_id)
    sync_session = session.sync_session
    transaction = sync_session.get_nested_transaction() or sync_session.get_transaction()
    sync_session.info.setdefault(_SCHEDULED, {}).setdefault(transaction, set()).add((schema, instance_id))


@event.listens_for(TenantSession, "after_commit")
def _schedule_committed_analysis(session):
    scheduled = session.info.get(_SCHEDULED)
    if not scheduled:
        return
    nested = session.get_nested_transaction()
    if nested is not None:
        scheduled.setdefault(nested.parent, set()).update(scheduled.pop(nested, ()))
        return
    for schema, instance_id in scheduled.pop(session.get_transaction(), ()):
        task = asyncio.create_task(_run_in_tenant(schema, instance_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


@event.listens_for(TenantSession, "after_transaction_end")
def _discard_ended_transaction(session, transaction):
    scheduled = session.info.get(_SCHEDULED)
    if scheduled:
        scheduled.pop(transaction, None)


async def _run_in_tenant(schema, instance_id):
    with use_tenant_schema(schema):
        try:
            await analyze_instance(instance_id)
        except Exception:
            logger.exception("审批 AI 意见生成失败，审批实例 %s", instance_id)


async def analyze_instance(instance_id):
    lease=None
    try:
        async with get_session_context() as session:
            row=await repo.claim(session,instance_id)
            if not row:
                return
            lease=row.ai_analysis_started_at
            business_type,business_id=row.business_type_code,row.business_id
            claims=await repo.actor_claims(session,instance_id)
            await session.commit()
        user=await current_user(claims)
        adapter=get_business_adapter(business_type)
        if not adapter or not adapter.analysis_prepare or not adapter.analysis_run or not adapter.analysis_access:
            raise AppException("该业务暂未接入AI分析",409)
        async with get_session_context() as session:
            if not await adapter.analysis_access(session,business_id,user):
                raise AppException("当前账号无权读取分析依据",403)
            facts=await adapter.analysis_prepare(session,business_id,user)
        source_hash=fingerprint(facts)
        result,model=await adapter.analysis_run(facts)
        if not isinstance(result,str) or not result.strip() or len(result)>600:
            raise AppException("AI分析结果格式异常",502)
        user=await current_user(claims)
        async with get_session_context() as session:
            if not await adapter.analysis_access(session,business_id,user):
                raise AppException("分析期间账号权限已变化",403)
            fresh=await adapter.analysis_prepare(session,business_id,user)
            await repo.finish(session,instance_id,lease,source_hash,result.strip(),model,
                stale=fingerprint(fresh)!=source_hash)
            await session.commit()
    except Exception as exc:
        if lease is None:
            raise
        message=exc.message if isinstance(exc,AppException) else "AI分析暂不可用，请按业务材料人工审批"
        async with get_session_context() as session:
            await repo.finish(session,instance_id,lease,"",error=message)
            await session.commit()

async def visible_analysis(session, instance, user):
    adapter=get_business_adapter(instance.business_type_code)
    if not adapter or not adapter.analysis_access or not await adapter.analysis_access(session,instance.business_id,user):
        return {"ai_analysis":None,"ai_analysis_status_code":"not_applicable","_analysis_access":False}
    status=instance.ai_analysis_status_code
    if status in {"pending", "processing"}:
        started_at = instance.ai_analysis_started_at or instance.started_at
        if started_at < utc_now() - timedelta(minutes=5):
            status = "failed"
    return {"_analysis_access":True,"ai_analysis":instance.ai_analysis if status=="succeeded" else None,
        "ai_analysis_status_code":status,"ai_analysis_generated_at":instance.ai_analysis_generated_at}
