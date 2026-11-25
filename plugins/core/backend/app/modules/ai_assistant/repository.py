"""Redis 会话与运行记录；所有键包含已验证租户和租户内用户。"""
import json
import time
from datetime import datetime
from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.integrations.redis_client import get_redis


def owner_key(user: AuthenticatedUser, session_id: UUID) -> str:
    return f"ai-assistant:{user.tenant_id}:{user.user_id}:{session_id}"


async def save_session(user, session_id, authorization_revision):
    await get_redis().setex(owner_key(user, session_id), get_settings().server_assistant_session_ttl_seconds,
                          json.dumps({"authorization_revision": authorization_revision, "runtime_id": str(session_id)}))


async def read_session(user, session_id):
    raw = await get_redis().get(owner_key(user, session_id))
    return json.loads(raw) if raw else None


async def save_runtime_identity(user, session_id, metadata):
    await get_redis().setex(owner_key(user, session_id), get_settings().server_assistant_session_ttl_seconds, json.dumps(metadata))


async def lock_run(user, session_id, run_id, seconds):
    return await get_redis().set(owner_key(user, session_id) + ":lock", str(run_id), nx=True, ex=seconds)


async def release_run(user, session_id, run_id):
    await get_redis().eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end", 1,
                         owner_key(user, session_id) + ":lock", str(run_id))


async def run_is_live(user, session_id, run_id):
    return await get_redis().get(owner_key(user, session_id) + ":lock") == str(run_id)


async def save_run(user, run, authorization_revision):
    ttl = get_settings().server_assistant_session_ttl_seconds
    key = owner_key(user, run.session_id)
    async with get_redis().pipeline(transaction=True) as pipeline:
        record = {"authorization_revision": authorization_revision, "run": run.model_dump(mode="json")}
        pipeline.setex(key + ":run:" + str(run.run_id), ttl, json.dumps(record, ensure_ascii=False))
        pipeline.zadd(key + ":runs", {str(run.run_id): time.time()})
        pipeline.expire(key + ":runs", ttl)
        pipeline.expire(key, ttl)
        await pipeline.execute()


async def read_run(user, session_id, run_id, authorization_revision):
    from .schemas import AssistantRun
    raw = await get_redis().get(owner_key(user, session_id) + ":run:" + str(run_id))
    if not raw:
        return None
    record = json.loads(raw)
    if record["authorization_revision"] != authorization_revision:
        return None
    return AssistantRun.model_validate(record["run"])


def conversation_prefix(user):
    return f"ai-assistant:{user.tenant_id}:{user.user_id}:conversation"


async def conversation(user, client_id):
    raw = await get_redis().get(conversation_prefix(user) + ":record:" + client_id)
    return json.loads(raw) if raw else None


async def bind_conversation(user, client_id, metadata):
    """仅首次绑定；多个请求同时创建时复用第一个成功的绑定。"""
    key = conversation_prefix(user) + ":record:" + client_id
    return await get_redis().set(key, json.dumps(metadata), nx=True, ex=get_settings().server_assistant_session_ttl_seconds)


async def save_conversation(user, client_id, metadata):
    ttl = get_settings().server_assistant_session_ttl_seconds
    prefix = conversation_prefix(user)
    async with get_redis().pipeline(transaction=True) as pipeline:
        pipeline.setex(prefix + ":record:" + client_id, ttl, json.dumps(metadata, ensure_ascii=False))
        pipeline.zadd(prefix + ":index", {client_id: datetime.fromisoformat(metadata["updated_at"]).timestamp()})
        pipeline.expire(prefix + ":index", ttl)
        await pipeline.execute()


async def conversations(user, limit):
    prefix = conversation_prefix(user)
    ids = await get_redis().zrevrange(prefix + ":index", 0, limit - 1 if limit is not None else -1)
    if not ids:
        return []
    records = await get_redis().mget([prefix + ":record:" + ident for ident in ids])
    return [json.loads(raw) for raw in records if raw]


async def conversation_page(user, offset, limit):
    prefix = conversation_prefix(user)
    ids = await get_redis().zrevrange(prefix + ":index", offset, offset + limit - 1)
    if not ids:
        return []
    records = await get_redis().mget([prefix + ":record:" + ident for ident in ids])
    # 保留过期项的位置，分页游标仍对应有序索引位置。
    return [json.loads(raw) if raw else None for raw in records]


async def bind_session_conversation(user, session_id, client_id):
    # 原子补充反向标识，不覆盖运行中的凭据版本、权限版本或运行会话 ID。
    await get_redis().eval("local raw=redis.call('get',KEYS[1]); if not raw then return 0 end; "
                         "local value=cjson.decode(raw); value.conversation_id=ARGV[1]; "
                         "local ttl=redis.call('pttl',KEYS[1]); "
                         "redis.call('set',KEYS[1],cjson.encode(value)); "
                         "if ttl>0 then redis.call('pexpire',KEYS[1],ttl) end; return 1", 1,
                         owner_key(user, session_id), client_id)


async def history_initialized(user):
    return bool(await get_redis().get(conversation_prefix(user) + ":initialized"))


async def mark_history_initialized(user):
    await get_redis().setex(conversation_prefix(user) + ":initialized", get_settings().server_assistant_session_ttl_seconds, "1")


async def unindexed_sessions(user):
    prefix = f"ai-assistant:{user.tenant_id}:{user.user_id}:"
    async for key in get_redis().scan_iter(match=prefix + "*", count=200):
        ident = key[len(prefix):]
        try:
            session_id = UUID(ident)
        except ValueError:
            continue
        metadata = await read_session(user, session_id)
        if metadata is not None and not metadata.get("conversation_id"):
            yield session_id, metadata


async def session_times(user, session_id):
    key = owner_key(user, session_id) + ":runs"
    first = await get_redis().zrange(key, 0, 0, withscores=True)
    last = await get_redis().zrevrange(key, 0, 0, withscores=True)
    return (first[0][1] if first else None, last[0][1] if last else None)


async def conversation_runs(user, session_id, limit, revision):
    ids = await get_redis().zrevrange(owner_key(user, session_id) + ":runs", 0, limit - 1)
    result = []
    for ident in reversed(ids):
        run = await read_run(user, session_id, UUID(ident), revision)
        if run is not None:
            result.append(run)
    return result


async def reset_conversation(user, client_id, session_id, metadata=None):
    """调用方持有会话锁；删除展示记录，日志原件按部署保留策略处理。"""
    key = owner_key(user, session_id)
    prefix = conversation_prefix(user)
    ids = await get_redis().zrange(key + ":runs", 0, -1)
    async with get_redis().pipeline(transaction=True) as pipeline:
        pipeline.delete(key + ":runs", *(key + ":run:" + ident for ident in ids))
        if metadata is None:
            pipeline.delete(key, prefix + ":record:" + client_id)
            pipeline.zrem(prefix + ":index", client_id)
        else:
            pipeline.setex(key, get_settings().server_assistant_session_ttl_seconds, json.dumps(metadata))
        await pipeline.execute()


async def delete_conversations(user, records):
    """调用方持有所有目标会话锁；一次事务清理当前账号的展示记录。"""
    keys = []
    prefix = conversation_prefix(user)
    for record in records:
        key = owner_key(user, UUID(record["session_id"]))
        ids = await get_redis().zrange(key + ":runs", 0, -1)
        keys.extend([key, key + ":runs", prefix + ":record:" + record["conversation_id"]])
        keys.extend(key + ":run:" + ident for ident in ids)
    if not keys:
        return
    async with get_redis().pipeline(transaction=True) as pipeline:
        pipeline.delete(*keys)
        pipeline.zrem(prefix + ":index", *(record["conversation_id"] for record in records))
        await pipeline.execute()
