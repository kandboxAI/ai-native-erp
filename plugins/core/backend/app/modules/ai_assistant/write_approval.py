"""当前账号的智能体写操作确认；确认结果只供本轮 DSH 工具使用。"""
import asyncio
import hashlib
import json
import secrets
import time
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.core.config import get_settings
from app.integrations.redis_client import get_redis
from . import repository


def _prefix(user):
    return f"ai-assistant:{user.tenant_id}:{user.user_id}:write-approvals"


def _secret_key(user, session_id, run_id):
    return repository.owner_key(user, session_id) + f":approval-secret:{run_id}"


async def issue_secret(user, session_id, run_id, surface):
    secret = secrets.token_urlsafe(32)
    ttl = get_settings().server_assistant_turn_timeout_seconds + 90
    await get_redis().setex(_secret_key(user, session_id, run_id), ttl,
                            json.dumps({"digest": hashlib.sha256(secret.encode()).hexdigest(), "surface": surface}))
    return secret


async def forget_secret(user, session_id, run_id):
    await get_redis().delete(_secret_key(user, session_id, run_id))


async def request_decision(user, session_id: UUID, run_id: UUID, secret: str, preview: str):
    from .service import get_run

    stored = await get_redis().get(_secret_key(user, session_id, run_id))
    if not stored or not secrets.compare_digest(json.loads(stored)["digest"], hashlib.sha256(secret.encode()).hexdigest()):
        raise HTTPException(403, "写操作确认请求无效")
    run = await get_run(user, session_id, run_id)
    if run.status != "running" or not await repository.run_is_live(user, session_id, run_id):
        raise HTTPException(409, "智能体任务已结束")
    approval_id = str(uuid4())
    prefix = _prefix(user)
    key = prefix + ":" + approval_id
    timeout = min(90, max(15, get_settings().server_assistant_turn_timeout_seconds - 45))
    expires_at = time.time() + timeout
    record = {"approval_id": approval_id, "session_id": str(session_id),
              "run_id": str(run_id), "preview": preview, "expires_at": expires_at,
              "surface": json.loads(stored)["surface"]}
    async with get_redis().pipeline(transaction=True) as pipeline:
        pipeline.setex(key, timeout, json.dumps(record, ensure_ascii=False))
        pipeline.zadd(prefix + ":index", {approval_id: expires_at})
        pipeline.expire(prefix + ":index", get_settings().server_assistant_turn_timeout_seconds + 90)
        await pipeline.execute()
    try:
        while time.time() < expires_at:
            if not await repository.run_is_live(user, session_id, run_id):
                break
            if not await get_redis().exists(key):
                break
            decision = await get_redis().get(key + ":decision")
            if decision == "approved":
                return "allowed-once"
            if decision == "rejected":
                return "rejected"
            await asyncio.sleep(0.25)
        return "unavailable"
    finally:
        await get_redis().delete(key, key + ":decision")
        await get_redis().zrem(prefix + ":index", approval_id)


async def list_pending(user, surface=None):
    from .service import get_run

    prefix = _prefix(user)
    ids = await get_redis().zrangebyscore(prefix + ":index", time.time(), "+inf")
    pending = []
    for ident in ids:
        raw = await get_redis().get(prefix + ":" + ident)
        if not raw or await get_redis().exists(prefix + ":" + ident + ":decision"):
            continue
        record = json.loads(raw)
        if surface is not None and record["surface"] != surface:
            continue
        try:
            run = await get_run(user, UUID(record["session_id"]), UUID(record["run_id"]))
        except HTTPException:
            continue
        if run.status == "running":
            pending.append(record)
    return pending


async def decide(user, approval_id: UUID, approved: bool):
    from .service import get_run

    key = _prefix(user) + ":" + str(approval_id)
    raw = await get_redis().get(key)
    if not raw:
        raise HTTPException(404, "写操作确认已过期")
    record = json.loads(raw)
    run = await get_run(user, UUID(record["session_id"]), UUID(record["run_id"]))
    if run.status != "running" or not await repository.run_is_live(user, run.session_id, run.run_id):
        raise HTTPException(409, "智能体任务已结束")
    ttl = await get_redis().ttl(key)
    if ttl < 1 or not await get_redis().set(key + ":decision", "approved" if approved else "rejected", nx=True, ex=ttl):
        raise HTTPException(409, "写操作确认已处理或过期")
    return {"accepted": True}
