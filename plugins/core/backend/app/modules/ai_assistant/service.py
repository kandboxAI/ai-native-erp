"""受控服务端会话编排；发布回答和阶段摘要，不透传原始事件或运行凭据。"""
import asyncio
import hashlib
import json
import logging
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.framework.db.models import utc_now
from app.modules.llm_gateway import repository as gateway_repository, service as gateway_service
from . import diagnostics, repository, runtime, write_approval, context_service
from .schemas import AssistantProgress, AssistantRun, AssistantSession

_tasks: set[asyncio.Task] = set()
_stopping = False
_slots: asyncio.Semaphore | None = None
logger = logging.getLogger(__name__)


def _settled(task):
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("智能体任务清理或状态保存失败，请检查 Redis 与 SDK 运行状态")


def authorization_revision(user: AuthenticatedUser) -> str:
    # 权限或组织范围变化后使用新运行日志，避免旧工具数据继续进入模型上下文。
    data = user.model_dump(mode="json", exclude={"profile", "display_name", "avatar_url", "email", "role_nos", "tenant_name"})
    for field in ("permissions", "org_ids"):
        data[field] = sorted(set(data[field]))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def visible_text(text: str) -> str:
    return text


async def create_session(user):
    runtime.runtime_paths()
    session_id = uuid4()
    await repository.save_session(user, session_id, authorization_revision(user))
    return AssistantSession(session_id=session_id)


async def get_run(user, session_id, run_id):
    run = await repository.read_run(user, session_id, run_id, authorization_revision(user))
    if run is None:
        raise HTTPException(404, "智能体任务不存在或无权访问")
    if run.status == "running" and not await repository.run_is_live(user, session_id, run_id):
        run.status, run.message, run.error_code = "interrupted", "任务已中断，请在当前会话重新发送问题", "RUN_INTERRUPTED"
    return run


async def send_message(user, session_id: UUID, content: str, access_token: str, *, surface="miniapp"):
    global _slots
    if _stopping:
        raise HTTPException(503, "智能体服务正在重启，请稍后重试")
    metadata = await repository.read_session(user, session_id)
    if metadata is None:
        raise HTTPException(404, "智能体会话不存在或无权访问，请新建会话")
    if not content.strip():
        raise HTTPException(400, "请输入问题")
    runtime.runtime_paths()
    settings = get_settings()
    if settings.server_assistant_turn_timeout_seconds + 30 > settings.llm_gateway_credential_ttl_seconds:
        raise HTTPException(503, "模型网关凭据有效期须大于智能体任务时限至少 30 秒")
    if _slots is None:
        _slots = asyncio.Semaphore(settings.server_assistant_max_concurrent_runs)
    slots = _slots
    if slots.locked():
        raise HTTPException(429, "智能体当前繁忙，请稍后再试")
    await slots.acquire()
    run = AssistantRun(run_id=uuid4(), session_id=session_id, status="running", question=visible_text(content.strip()),
                       created_at=utc_now(), progress=[AssistantProgress(key="runtime", label="理解问题", status="running")])
    credential = None
    locked = False
    try:
        locked = await repository.lock_run(user, session_id, run.run_id, settings.server_assistant_turn_timeout_seconds + 90)
        if not locked:
            raise HTTPException(409, "当前会话仍在回答，请等本轮完成")
        metadata = await repository.read_session(user, session_id)
        if metadata is None:
            raise HTTPException(404, "智能体会话已删除，请新建会话")
        revision = authorization_revision(user)
        if metadata["authorization_revision"] != revision:
            metadata = {**metadata, "authorization_revision": revision, "runtime_id": str(uuid4())}
            await repository.save_runtime_identity(user, session_id, metadata)
        user_context = await context_service.current_context(user)
        client_id = uuid4()
        credential = await gateway_service.issue_credential(user, client_id)
        approval_token = await write_approval.issue_secret(user, session_id, run.run_id, surface)
        worker = runtime.create_runtime(user, UUID(metadata["runtime_id"]), access_token, credential.access_token, client_id,
                                        approval_token=approval_token, run_id=run.run_id, public_session_id=session_id, user_context=user_context["prompt"])
        await repository.save_run(user, run, revision)
        task = asyncio.create_task(_execute(user, run, metadata["runtime_id"], worker, credential.access_token, slots, revision))
        _tasks.add(task)
        task.add_done_callback(_settled)
        return run
    except BaseException:
        try:
            if credential is not None:
                await gateway_repository.revoke_credential(credential.access_token)
        finally:
            slots.release()
            if locked:
                await write_approval.forget_secret(user, session_id, run.run_id)
                await repository.release_run(user, session_id, run.run_id)
        raise


async def _execute(user, run, runtime_id, worker, token, slots, revision):
    from .text_stream import ProtectedTextStream, protected_text
    from .progress import ProgressTracker
    loop = asyncio.get_running_loop()
    stream = ProtectedTextStream()
    attempt_id = None
    progress = ProgressTracker(run)

    async def publish_progress(event):
        if run.status == "running" and progress.handle(event):
            await repository.save_run(user, run, revision)

    async def publish(answer):
        if run.status == "running" and run.answer != answer:
            run.answer = answer
            await repository.save_run(user, run, revision)

    def notification(item):
        nonlocal stream, attempt_id
        data = item.payload
        if data.get("sessionId") != runtime_id:
            return
        if item.method == "session.event":
            asyncio.run_coroutine_threadsafe(publish_progress(data["event"]), loop).result(timeout=10)
            return
        if item.method != "session.text":
            return
        if data.get("type") == "start":
            attempt_id = data.get("attemptId")
            stream = ProtectedTextStream()
            answer = ""
        elif data.get("attemptId") != attempt_id:
            return
        elif data.get("type") == "delta" and isinstance(data.get("text"), str):
            answer = stream.feed(data["text"])
        elif data.get("type") == "end":
            answer = stream.finish() if data.get("committed") else ""
        else:
            return
        if answer == run.answer:
            return
        # 回调运行在 SDK 工作线程；Redis 由事件循环串行保存，不透传原始帧。
        asyncio.run_coroutine_threadsafe(publish(answer), loop).result(timeout=10)

    turn = asyncio.create_task(asyncio.to_thread(worker.run, run.question, session_id=runtime_id, on_notification=notification))
    try:
        result = await asyncio.wait_for(asyncio.shield(turn), get_settings().server_assistant_turn_timeout_seconds)
        run.answer = protected_text(result.final_response)
        run.finish_reason = result.finish_reason
        if result.finish_reason == "completed":
            run.status = "completed"
        else:
            run.status, run.error_code = "failed", "MODEL_RUN_FAILED"
            run.message = "本轮未完成，请重试；若回答被截断，可发送继续"
    except (TimeoutError, asyncio.CancelledError):
        run.status, run.message, run.error_code = "interrupted", "任务超时或服务重启，请重新发送问题", "RUN_INTERRUPTED"
    except Exception as error:
        run.error_code, run.message = diagnostics.log_failure(logger, error,
            run_id=run.run_id, phase=getattr(worker, "phase", "unknown"))
        run.status = "failed"
    finally:
        try:
            await asyncio.to_thread(worker.close)
            await asyncio.gather(turn, return_exceptions=True)
        finally:
            try:
                progress.finish()
                await repository.save_run(user, run, revision)
            finally:
                try:
                    await gateway_repository.revoke_credential(token)
                finally:
                    slots.release()
                    await write_approval.forget_secret(user, run.session_id, run.run_id)
                    await repository.release_run(user, run.session_id, run.run_id)


async def shutdown():
    global _stopping
    _stopping = True
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
