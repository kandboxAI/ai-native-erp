"""现有聊天界面的会话别名、历史与清理；复用同一智能体运行服务。"""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import HTTPException

from app.framework.db.models import utc_now
from . import repository, service


async def resolve_conversation(user, client_id):
    record = await repository.conversation(user, client_id)
    if record is not None and await repository.read_session(user, UUID(record["session_id"])) is not None:
        await repository.bind_session_conversation(user, UUID(record["session_id"]), client_id)
        return record
    session = await service.create_session(user)
    now = utc_now().isoformat()
    record = {"conversation_id": client_id, "session_id": str(session.session_id),
              "title": "新会话", "created_at": now, "updated_at": now}
    bound = await repository.bind_conversation(user, client_id, record)
    if not bound:
        existing = await repository.conversation(user, client_id)
        if existing is not None and await repository.read_session(user, UUID(existing["session_id"])) is not None:
            return existing
    await repository.save_conversation(user, client_id, record)
    await repository.bind_session_conversation(user, session.session_id, client_id)
    return record


async def remember_question(user, record, question):
    record = dict(record)
    if record["title"] == "新会话":
        record["title"] = service.visible_text(question.strip())[:48]
    record["updated_at"] = utc_now().isoformat()
    await repository.save_conversation(user, record["conversation_id"], record)


async def list_conversations(user, limit):
    records = await repository.conversations(user, limit)
    result = []
    revision = service.authorization_revision(user)
    for record in records:
        metadata = await repository.read_session(user, UUID(record["session_id"]))
        if metadata is not None and metadata["authorization_revision"] == revision:
            result.append({key: record[key] for key in ("conversation_id", "title", "created_at", "updated_at")})
    return result


async def messages(user, client_id, limit):
    record = await repository.conversation(user, client_id)
    if record is None:
        # 原界面在首次发送前创建本地空会话，此时没有服务端记录。
        return []
    runs = await repository.conversation_runs(user, UUID(record["session_id"]), (limit + 1) // 2, service.authorization_revision(user))
    result = []
    for run in runs:
        result.append({"id": str(run.run_id) + ":user", "role": "user", "content": run.question})
        text = "\n\n".join(part for part in (run.answer, run.message) if part)
        if text:
            result.append({"id": str(run.run_id) + ":assistant", "role": "assistant", "content": text,
                           "executionSteps": [item.model_dump(exclude_none=True) for item in run.progress]})
    return result[-limit:]


async def clear(user, client_id, *, delete=False):
    record = await repository.conversation(user, client_id)
    if record is None:
        return
    session_id, lock_id = UUID(record["session_id"]), uuid4()
    if not await repository.lock_run(user, session_id, lock_id, 30):
        raise HTTPException(409, "当前会话仍在回答，请等本轮完成后再清理")
    try:
        metadata = None if delete else {"authorization_revision": service.authorization_revision(user), "runtime_id": str(uuid4()), "conversation_id": client_id}
        await repository.reset_conversation(user, client_id, session_id, metadata)
        if not delete:
            record.update(title="新会话", updated_at=utc_now().isoformat())
            await repository.save_conversation(user, client_id, record)
    finally:
        await repository.release_run(user, session_id, lock_id)


async def delete_all(user):
    # 包括权限变动后不再展示的会话；任意会话忙碌时整批拒绝，避免部分删除。
    records = await repository.conversations(user, None)
    acquired = []
    try:
        for record in records:
            session_id, lock_id = UUID(record["session_id"]), uuid4()
            if not await repository.lock_run(user, session_id, lock_id, 120):
                raise HTTPException(409, "有会话仍在回答，请等本轮完成后再清理")
            acquired.append((session_id, lock_id))
        await repository.delete_conversations(user, records)
    finally:
        for session_id, lock_id in acquired:
            await repository.release_run(user, session_id, lock_id)


async def create_session(user):
    session = await service.create_session(user)
    now = utc_now().isoformat()
    ident = str(session.session_id)
    record = {"conversation_id": ident, "session_id": ident, "title": "新会话", "created_at": now, "updated_at": now}
    await repository.save_conversation(user, ident, record)
    await repository.bind_session_conversation(user, session.session_id, ident)
    return session


async def remember_session_question(user, session_id, question):
    metadata = await repository.read_session(user, session_id)
    if metadata and metadata.get("conversation_id"):
        record = await repository.conversation(user, metadata["conversation_id"])
        if record:
            await remember_question(user, record, question)


async def _index_existing_sessions(user):
    if await repository.history_initialized(user):
        return
    # 旧小程序只有运行记录；首次读取自己的历史时补目录，不扫描其他用户内容。
    existing = await repository.conversations(user, None)
    for record in existing:
        await repository.bind_session_conversation(user, UUID(record["session_id"]), record["conversation_id"])
    async for session_id, metadata in repository.unindexed_sessions(user):
        first, last = await repository.session_times(user, session_id)
        now = utc_now().isoformat()
        runs = await repository.conversation_runs(user, session_id, 500, metadata["authorization_revision"])
        if not runs:
            continue
        record = {"conversation_id": str(session_id), "session_id": str(session_id),
                  "title": service.visible_text(runs[0].question)[:48] if runs else "新会话",
                  "created_at": datetime.fromtimestamp(first, timezone.utc).isoformat() if first else now,
                  "updated_at": datetime.fromtimestamp(last, timezone.utc).isoformat() if last else now}
        await repository.save_conversation(user, str(session_id), record)
        await repository.bind_session_conversation(user, session_id, str(session_id))
    await repository.mark_history_initialized(user)


async def list_session_page(user, offset, limit):
    await _index_existing_sessions(user)
    revision = service.authorization_revision(user)
    result = []
    cursor = offset
    while True:
        records = await repository.conversation_page(user, cursor, limit)
        if not records:
            return {"items": result, "has_more": False, "next_offset": cursor}
        for record in records:
            cursor += 1
            if record is None:
                continue
            metadata = await repository.read_session(user, UUID(record["session_id"]))
            if metadata is None or metadata["authorization_revision"] != revision:
                continue
            if len(result) == limit:
                return {"items": result, "has_more": True, "next_offset": cursor - 1}
            result.append({key: record[key] for key in ("session_id", "title", "created_at", "updated_at")})


async def _session_record(user, session_id):
    metadata = await repository.read_session(user, session_id)
    if metadata is None or metadata["authorization_revision"] != service.authorization_revision(user):
        raise HTTPException(404, "会话不存在、已过期或当前账号无权访问")
    client_id = metadata.get("conversation_id")
    record = await repository.conversation(user, client_id) if client_id else None
    if record is None:
        raise HTTPException(404, "会话目录已过期，请新建会话")
    return record


async def session_history(user, session_id, limit):
    record = await _session_record(user, session_id)
    runs = await repository.conversation_runs(user, session_id, (limit + 1) // 2, service.authorization_revision(user))
    active = None
    if runs and runs[-1].status == "running":
        runs[-1] = await service.get_run(user, session_id, runs[-1].run_id)
        if runs[-1].status == "running":
            active = runs[-1].model_dump(mode="json")
    rows = []
    for run in runs:
        timestamp = run.created_at.isoformat() if run.created_at else None
        rows.append({"id": str(run.run_id) + ":user", "role": "user", "content": run.question, "created_at": timestamp})
        text = "\n\n".join(part for part in (run.answer, run.message) if part)
        if text:
            rows.append({"id": str(run.run_id) + ":assistant", "role": "assistant", "content": text, "created_at": timestamp})
    return {"session_id": str(session_id), "title": record["title"], "messages": rows[-limit:], "active_run": active}


async def delete_session(user, session_id):
    record = await _session_record(user, session_id)
    await clear(user, record["conversation_id"], delete=True)
